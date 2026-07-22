#!/usr/bin/env python3
"""从数据池中找最佳单调五档组合。

不依赖 tier 标签，全量枚举所有满足 T1≥T2≥T3≥T4≥T5 的组合。
按品质总分（各档离目标绝对值之和 + 来源罚分 + 档差罚分）排序取最优。

用法:
  python tools/find_best_combo.py 72
  python tools/find_best_combo.py 72 --targets 80,65,50,40,30
  python tools/find_best_combo.py 72 --targets 80,65,50,40,30 --top 3
  python tools/find_best_combo.py 72,87,92
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tools.data import pool
from tools.data.adapters import excel_target as et


def parse_levels(spec):
    levels = set()
    for part in spec.split(','):
        part = part.strip()
        if '-' in part:
            a, b = part.split('-')
            levels.update(range(int(a), int(b) + 1))
        else:
            levels.add(int(part))
    return sorted(levels)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    spec = sys.argv[1]
    top_n = 1
    custom_targets = None
    diff_map = {}
    try:
        targets_all = et.read_targets(set(range(51, 101)))
        for lv_i, t in targets_all.items():
            diff_map[str(lv_i)] = t.get('diff', 'hard')
    except:
        pass

    for arg in sys.argv[2:]:
        if arg.startswith('--targets='):
            custom_targets = [float(x) for x in arg.split('=', 1)[1].split(',')]
        elif arg.startswith('--top='):
            top_n = int(arg.split('=', 1)[1])

    levels = parse_levels(spec)

    for lv in levels:
        lv_s = str(lv)
        targets = custom_targets
        if not targets:
            t = et.get_target(lv)
            if not t or not t.get('tiers'):
                print(f'L{lv}: 在 lv_win_config_test.xlsx 中找不到')
                continue
            targets = t['tiers']

        recs = pool.get_preferred_records(lv_s)
        uniq = pool.dedup_records(recs)
        if len(uniq) < 5:
            print(f'L{lv}: 只有 {len(uniq)} 条有效数据，无法组成五档')
            continue

        difficulty = diff_map.get(str(lv), 'hard')
        results = pool.find_best_monotonic(uniq, targets, top_n=top_n, difficulty=difficulty)
        if not results:
            print(f'L{lv}: 无满足单调条件的组合')
            continue

        print(f'\nL{lv} — 目标 {targets[0]:.0f}/{targets[1]:.0f}/{targets[2]:.0f}/{targets[3]:.0f}/{targets[4]:.0f}')
        print('  档     WR      目标差   sd   sc               ratios     of    局数       来源')
        print('-' * 75)

        for rank, (q, gs, recs) in enumerate(results):
            if top_n > 1:
                print(f'  ── #{rank+1} 品质总分 {q:.1f} ──')
            for i, (r, t) in enumerate(zip(recs, targets)):
                label = 'T%d' % (i+1)
                diff = r['wr'] - t
                print('  %s %5.1f%% %+7.1fpp %4s %4s %20s %6s %5d %8s' % (
                    label, r['wr'], diff,
                    r.get('sd',''), r.get('sc',''),
                    str(r.get('ratios','')), str(r.get('of','')),
                    r.get('totalGames',0), r.get('source','')))
            print(f'  gaps: {gs[0]:.1f}/{gs[1]:.1f}/{gs[2]:.1f}/{gs[3]:.1f} 品质={q:.1f}')

            # 死亡分布分析 + 改关卡预判（只看 T1）
            t1_rec = recs[0]
            dp = t1_rec.get('deathProfile')
            if dp and targets[0] >= 60:
                early_d = dp['early'] * 100
                trans_d = dp['transition'] * 100
                mid_d = dp['mid'] * 100
                late_d = dp['late'] * 100
                threshold = (1 - targets[0] / 100) * 0.8 * 100
                print(f'  \u2695 死亡: 初期{early_d:.0f}% 过渡{trans_d:.0f}% 中期{mid_d:.0f}% 后期{late_d:.0f}%')
                print(f'  \u2695 T1 目标WR={targets[0]:.0f}% 允许失败={(1-targets[0]/100)*100:.0f}% 改关卡阈值={threshold:.0f}%', end='')
                if dp['early'] > threshold / 100:
                    print(f'  \u26d4 初期死亡{early_d:.0f}%>阈值，建议改关卡')
                else:
                    print(f'  \u2705 初期死亡{early_d:.0f}%<阈值，可继续调参')
                # 调参方向提示
                if dp['transition'] > 0.5:
                    print(f'  \u26a1 过渡段死亡{trans_d:.0f}% \u2192 优先降 ratios 前段权重或降 sd')
                elif dp['mid'] > 0.6:
                    print(f'  \u26a1 中期死亡{mid_d:.0f}% \u2192 优先调 of 或换 ratios 分布')
                elif dp['late'] > 0.6:
                    print(f'  \u26a1 后期死亡{late_d:.0f}% \u2192 优先降 of 或后段 ratios 放轻')
            print()


if __name__ == '__main__':
    main()
