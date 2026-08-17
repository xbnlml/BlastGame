#!/usr/bin/env python3
"""批后自动分析 — 读取最新 batch 结果，对比池子，输出格式化的变化表格。

用法:
  python tools/post_batch_review.py
  python tools/post_batch_review.py 82,98
  python tools/post_batch_review.py --levels 82,98 --full
"""
import os, sys, json, csv, glob
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

REPO = os.environ.get('BLASTGAME_REPO', r'C:\Users\Administrator\Documents\BlastGame')
BOT_DIR = os.path.join(REPO, 'telemetry', 'bot')
TOOL_DIR = os.path.dirname(os.path.abspath(__file__))
TARGETS = {
    'normal': [90, 90, 75, 60, 60],
    'hard': [90, 75, 60, 45, 30],
    'superhard': [60, 45, 30, 20, 10],
}


def get_latest_batch_dir():
    """找到最新 batch 目录（bot 根下的目录，含水平线分隔的日期）"""
    dirs = [d for d in os.listdir(BOT_DIR) if not d.startswith('_') and os.path.isdir(os.path.join(BOT_DIR, d))]
    if not dirs:
        return None
    return sorted(dirs)[-1]


def parse_fbd(fbd_str):
    if not fbd_str:
        return None
    try:
        buckets = [float(x) for x in fbd_str.split(',')]
        if len(buckets) < 10:
            return None
        return {
            'early': round(sum(buckets[0:2]), 4),
            'transition': round(buckets[2], 4),
            'mid': round(sum(buckets[3:6]), 4),
            'late': round(sum(buckets[6:10]), 4),
        }
    except (ValueError, TypeError):
        return None


def read_latest_pool(lv):
    """从池子读该关所有 bot400 数据"""
    from tools.data import pool as pool_mod
    recs = pool_mod.dedup_records(pool_mod.get_preferred_records(str(lv)))
    return [r for r in recs if r.get('source') == 'bot' and r.get('totalGames', 0) >= 400]


def read_best_prev(lv):
    """从池子读之前的 best combo"""
    try:
        from tools.data import pool as pool_mod
        from tools.data.adapters import excel_target as et
        t = et.get_target(lv)
        if not t:
            return None, None
        recs = pool_mod.dedup_records(pool_mod.get_preferred_records(str(lv)))
        r = pool_mod.find_best_monotonic(recs, t['tiers'], top_n=1, difficulty=t['diff'])
        if r:
            return r[0][2], t['diff']
        return None, None
    except Exception:
        return None, None


def read_probe_configs():
    pc_path = os.path.join(TOOL_DIR, 'probe_configs.json')
    if not os.path.exists(pc_path):
        return {}
    with open(pc_path) as f:
        return json.load(f)


def review_batch(batch_name, levels=None, full=False):
    """分析一个 batch 的结果"""
    batch_path = os.path.join(BOT_DIR, batch_name)
    if not os.path.isdir(batch_path):
        print(f'❌ batch 不存在: {batch_name}')
        return

    # 找所有 summary CSV
    summary_files = glob.glob(os.path.join(batch_path, '**', 'campaign-summary-*.csv'), recursive=True)
    summary_files += glob.glob(os.path.join(batch_path, '**', 'cs-*.csv'), recursive=True)

    if not summary_files:
        print(f'❌ {batch_name} 中无 summary CSV')
        return

    # 按 tier 分组
    tiers_data = defaultdict(list)
    for fp in sorted(summary_files):
        # 从父目录名取 tier（L82_98-T1-...）
        parent = os.path.basename(os.path.dirname(fp))
        tier = ''
        for t_key in ['T1-', 'T2-', 'T3-', 'T4-', 'T5-']:
            if t_key in parent:
                tier = t_key.replace('-', '')
                break
        if not tier:
            continue
        with open(fp, encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                lv = row.get('level', '').strip()
                if levels and lv not in levels:
                    continue
                sd = row.get('startDifficulty', '').strip()
                ratio_s = row.get('shuffleSplitRatios', '').strip()
                of_val = row.get('shuffleOverflowFactor', '').strip()
                fbd = parse_fbd(row.get('failBucketDistribution', ''))
                winkate = float(row.get('winkate', 0))
                tiers_data[lv].append({
                    'tier': tier,
                    'sd': sd,
                    'ratios': ratio_s,
                    'of': of_val,
                    'wr': round(winkate * 100, 1),
                    'fbd': fbd,
                })

    if not tiers_data:
        print(f'❌ 未找到数据（过滤后）')
        return

    # 加载 probe_configs 对比
    pc = read_probe_configs()

    print(f'\n📊 批跑分析: {batch_name}')
    print('=' * 80)

    for lv in sorted(tiers_data.keys()):
        batch_recs = tiers_data[lv]

        # 读该关的 difficulty 和 targets
        from tools.data.adapters import excel_target as et
        t = et.get_target(int(lv))
        if not t:
            print(f'\nL{lv}: 无目标配置，跳过')
            continue
        targets = t['tiers']
        diff = t['diff']
        diff_label = {0: 'Normal', 1: 'Hard', 2: 'SuperHard'}.get(t.get('diff_type', diff), 'Normal')
        expected_label = TARGETS.get(diff.lower(), targets)

        # 读 pool 里之前最佳
        prev_recs, _ = read_best_prev(int(lv))

        print(f'\nL{lv} ({diff_label}) — 目标 {targets[0]:.0f}/{targets[1]:.0f}/{targets[2]:.0f}/{targets[3]:.0f}/{targets[4]:.0f}')
        print(f'  批次数据:')
        print(f'  {"档":>4} {"WR":>6} {"sd":>4} {"ratios":<20} {"of":>6} {"来源"}', end='')
        if full:
            print(f' {"死亡(初/过/中/后)"}', end='')
        print()

        for rec in sorted(batch_recs, key=lambda x: int((x.get('source_tier', x.get('tier','T0'))[1:])) if (x.get('source_tier', x.get('tier','')).startswith('T')) else 0):
            r_tier = rec.get('source_tier', rec.get('tier',''))
            t_idx = int(r_tier[1:]) - 1
            target = targets[t_idx] if t_idx < len(targets) else 0
            diff_wr = rec['wr'] - target
            arrow = '↑' if diff_wr > 0 else '↓'
            death_str = ''
            if full and rec['fbd']:
                dp = rec['fbd']
                death_str = f' {dp["early"]*100:.0f}/{dp["transition"]*100:.0f}/{dp["mid"]*100:.0f}/{dp["late"]*100:.0f}%'
            print(f'  {r_tier:>4} {rec["wr"]:>5.1f}%{arrow}{abs(diff_wr):>+5.1f} {rec["sd"]:>4} {rec["ratios"]:<20} {rec["of"]:>6}', end='')
            # 对比预期
            expected_str = ''
            slv = str(lv)
            if slv in pc and r_tier in pc[slv]:
                pe = pc[slv][r_tier]
                if str(pe.get('sd')) != rec['sd'] or str(pe.get('ratios')) != rec['ratios'] or str(pe.get('of')) != rec['of']:
                    expected_str = f' ⚠️ 预期是 sd={pe["sd"]} ratios={pe["ratios"]} of={pe["of"]}'
            print(f' {"bot"}{death_str}{expected_str}')

        # 对比上次 best
        if prev_recs:
            print(f'  之前 best:')
            for r in prev_recs:
                dp_str = ''
                dp = r.get('deathProfile')
                if dp:
                    dp_str = f' 死亡:{dp["early"]*100:.0f}/{dp["transition"]*100:.0f}/{dp["mid"]*100:.0f}/{dp["late"]*100:.0f}%'
                print(f'    T{prev_recs.index(r)+1}: WR={r["wr"]:.1f}% sd={r["sd"]} ratios={r["ratios"]} of={r["of"]}{dp_str}')

    print()


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser(description='批跑结果自动分析')
    ap.add_argument('levels', nargs='?', help='关卡列表（可选，默认最新 batch 的所有）')
    ap.add_argument('--batch', help='指定 batch 目录名（默认最新）')
    ap.add_argument('--full', action='store_true', help='显示死亡分布')
    args = ap.parse_args()

    levels = None
    if args.levels:
        levels = set()
        for part in args.levels.replace(',', ' ').split():
            if '-' in part:
                a, b = part.split('-')
                levels.update(str(x) for x in range(int(a), int(b) + 1))
            else:
                levels.add(part.strip())

    batch = args.batch or get_latest_batch_dir()
    if not batch:
        print('❌ 无 batch 目录')
        sys.exit(1)

    review_batch(batch, levels, full=args.full)
