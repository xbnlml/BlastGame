#!/usr/bin/env python3
"""参数经验知识库 — 从所有关完整数据（含 phase1/phase2）学习参数→WR 规律。

用法:
  python tools/param_knowledge.py                  # 输出完整经验表
  python tools/param_knowledge.py 153              # 输出某关的参考 + 建议
  python tools/param_knowledge.py --ratios-pool    # 输出所有出现过的 ratios 值

原理:
  1. 遍历所有关的完整数据（dedup_records，含 phase1/phase2/reference）
  2. 按 (难度, ratios_pattern, sd_档次) 分组统计 WR 分布
  3. 产出经验表：每种 ratios × sd 在 Normal/Hard/SuperHard 下通常出多少 WR
  4. 设计 agent 查表反推：要 X% WR → 推荐 ratios + sd 范围

  2026-08-03 新增：全部 ratios 实际值分析（不限于 10/1）
"""

import sys, os
import json
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from data.pool import get_all_records, dedup_records
from data.adapters import excel_target as et

# ===== 配置 =====
SD_BINS = [(0, 5), (5, 10), (10, 15), (15, 20), (20, 25),
           (25, 30), (30, 35), (35, 40), (40, 45), (45, 50)]
SD_BIN_LABELS = [f'{lo}-{hi}' for lo, hi in SD_BINS]

# 排除 wr=0 的垃圾数据
def _valid(r):
    try:
        return float(r.get('wr', 0)) > 0 and r.get('sd', '') != '' and r.get('ratios', '') != ''
    except:
        return False


def _normalize_ratios(ratios_str):
    """归一化 ratios：排序后去重，便于分组"""
    parts = [int(x) for x in str(ratios_str).replace(' ', '').split(',') if x]
    # 去掉末尾的 0（sc 长度 > 实际 ratios 长度时补0）
    while parts and parts[-1] == 0:
        parts.pop()
    return ','.join(str(x) for x in parts)


def _sd_bin(sd):
    for i, (lo, hi) in enumerate(SD_BINS):
        if lo <= int(sd) < hi:
            return SD_BIN_LABELS[i]
    return '50+'


def _load_all_data():
    """从所有关加载完整数据（含 phase1/phase2）"""
    all_records = defaultdict(list)
    for lv in range(51, 201):
        lv_s = str(lv)
        recs = dedup_records(get_all_records(lv_s))
        for r in recs:
            if _valid(r):
                r['_lv'] = lv_s
                try:
                    t = et.get_target(lv)
                    r['_diff'] = t['diff']
                except:
                    r['_diff'] = 'unknown'
                all_records[lv_s].append(r)
    return all_records


def analyze_ratios_pool(all_records):
    """分析所有出现过的 ratios 值分布"""
    values = defaultdict(int)  # 值 -> 出现次数
    patterns = defaultdict(int)  # 完整 pattern -> 出现次数
    for lv, recs in all_records.items():
        for r in recs:
            for v in str(r.get('ratios', '')).replace(' ', '').split(','):
                if v:
                    values[int(v)] += 1
            patterns[_normalize_ratios(r.get('ratios', ''))] += 1
    return values, patterns


def build_knowledge_base(all_records):
    """按 (难度, ratios_pattern, sd_bin) 分组统计 WR"""
    groups = defaultdict(list)
    for lv, recs in all_records.items():
        for r in recs:
            key = (r['_diff'], _normalize_ratios(r.get('ratios', '')), _sd_bin(r.get('sd', 0)))
            groups[key].append(float(r['wr']))
    # 统计
    knowledge = {}
    for key, wrs in groups.items():
        wrs = sorted(wrs)
        n = len(wrs)
        knowledge[key] = {
            'n': n,
            'min': round(wrs[0], 1),
            'max': round(wrs[-1], 1),
            'median': round(wrs[n // 2], 1),
            'q25': round(wrs[n // 4], 1),
            'q75': round(wrs[n * 3 // 4], 1),
        }
    return knowledge


def query_for_target(diff, target_wr, knowledge, top_n=5):
    """查表：给定难度和目标 WR，推荐 ratios + sd 范围"""
    candidates = []
    for (d, ratios, sbin), stats in knowledge.items():
        if d != diff:
            continue
        if stats['n'] < 3:
            continue
        if stats['min'] <= target_wr <= stats['max']:
            candidates.append({
                'ratios': ratios,
                'sd_bin': sbin,
                'n': stats['n'],
                'median': stats['median'],
                'q25': stats['q25'],
                'q75': stats['q75'],
            })
    candidates.sort(key=lambda x: (abs(x['median'] - target_wr), -x['n']))
    return candidates[:top_n]


def print_level_trends(lv, all_records, knowledge):
    """输出某关的趋势分析 + 跨关参考"""
    recs = all_records.get(str(lv), [])
    if not recs:
        print(f'L{lv}: 无数据')
        return
    t = et.get_target(lv)
    diff = t['diff']
    targets = t['tiers']
    targets_str = '/'.join(str(int(x)) for x in targets)
    print(f'= L{lv} [{diff}] 目标: {targets_str} =')
    # 本关 verified 数据分 ratios 展示
    from data.pool import filter_verified
    from data.pool import get_all_records as ga
    verified = filter_verified(dedup_records(ga(str(lv))))
    if verified:
        print(f'\n本关 verified 数据 ({len(verified)} 条):')
        # 按 ratios pattern 分组
        by_pattern = defaultdict(list)
        for r in verified:
            by_pattern[_normalize_ratios(r.get('ratios', ''))].append(r)
        for pat, recs in sorted(by_pattern.items()):
            print(f'  ratios={pat}')
            for r in sorted(recs, key=lambda x: -x['wr']):
                print(f'    sd={str(r.get("sd")):>3} -> WR={r["wr"]:5.1f}%  of={r.get("of")}')
    # 缺口分析
    wrs = sorted(r['wr'] for r in recs if int(r.get('wr', 0)) > 0)
    if wrs:
        print(f'\n池子全部数据覆盖: {wrs[0]:.0f}~{wrs[-1]:.0f}%')
        print(f'目标范围: {targets[0]}~{targets[-1]}%')
        if wrs[-1] < targets[0] - 2:
            print(f'⚠ 缺口: 高段 {wrs[-1]:.0f}~{targets[0]}% 空白')
        if wrs[0] > targets[-1] + 2:
            print(f'⚠ 缺口: 低段 {targets[-1]}~{wrs[0]:.0f}% 空白')
    # 推荐探针方向
    print(f'\n推荐探针方向（按目标 WR 查经验表）:')
    needed = []
    for i, target in enumerate(targets):
        # 看池子里有没有接近这个目标的配置
        close = [r for r in wrs if abs(r - target) < 5] if wrs else []
        if not close:
            needed.append((f'T{i+1}={target}', target))
    for tier, target in needed[:3]:
        recs2 = query_for_target(diff, target, knowledge, top_n=3)
        if recs2:
            print(f'  {tier}: 推荐')
            for r in recs2:
                print(f'    ratios={r["ratios"]}  sd={r["sd_bin"]}  '
                      f'WR中位数={r["median"]}%  q25-q75={r["q25"]}~{r["q75"]}%  (n={r["n"]}条)')


def main():
    import argparse
    ap = argparse.ArgumentParser(description='参数经验知识库')
    ap.add_argument('level', nargs='?', help='关卡号（可选）')
    ap.add_argument('--ratios-pool', action='store_true', help='输出所有 ratios 值分布')
    ap.add_argument('--top-ratios', type=int, default=10, help='显示最常用的 ratios (默认10)')
    args = ap.parse_args()

    print('加载所有关数据...', file=sys.stderr)
    all_records = _load_all_data()
    print(f'共 {sum(len(v) for v in all_records.values())} 条记录', file=sys.stderr)
    knowledge = build_knowledge_base(all_records)
    print(f'经验表: {len(knowledge)} 个 (难度, ratios, sd) 组合', file=sys.stderr)

    if args.ratios_pool:
        values, patterns = analyze_ratios_pool(all_records)
        print(f'= 所有出现的 ratios 值 =')
        for v, cnt in sorted(values.items()):
            print(f'  {v}: {cnt} 次')
        print(f'\n= 最常见的 ratios 组合 (前{args.top_ratios}) =')
        for pat, cnt in sorted(patterns.items(), key=lambda x: -x[1])[:args.top_ratios]:
            print(f'  {pat}: {cnt} 次')
        return

    if args.level:
        print_level_trends(args.level, all_records, knowledge)
        return

    # 默认输出完整经验表摘要
    print(f'\n= 经验表摘要 (按难度 + ratios 分组) =')
    for diff in ['normal', 'hard', 'superhard']:
        print(f'\n--- {diff} ---')
        items = [(k, v) for k, v in knowledge.items() if k[0] == diff]
        # 按样本量排序
        items.sort(key=lambda x: -x[1]['n'])
        for (d, ratios, sbin), stats in items[:15]:
            print(f'  {ratios:<20} sd={sbin:<6} n={stats["n"]:>3}  '
                  f'WR={stats["median"]:5.1f}% [{stats["q25"]:.1f}~{stats["q75"]:.1f}]')


if __name__ == '__main__':
    main()