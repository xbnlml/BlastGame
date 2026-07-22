#!/usr/bin/env python3
"""判定五档组合是否合格。

输入五档组合 + 目标胜率 + 难度，按标准判定。

用法:
  python tools/validate_combo.py 72                           # 自动读池子+目标
  python tools/validate_combo.py 72 --targets 80,65,50,40,30  # 指定目标
  python tools/validate_combo.py 72 --targets 80,65,50,40,30 --diff Hard
  python tools/validate_combo.py 72 --show                     # 显示详细判定
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tools.data import pool
from tools.data.adapters import excel_target as et


def validate(recs, targets, diff='Normal'):
    """判定五档组合

    返回: (结果, [违规原因])   结果: '合格' | '接近' | '不合格'
    """
    reasons = []
    warnings = []
    wrs = [r['wr'] for r in recs]
    gaps = [wrs[i] - wrs[i+1] for i in range(4)]
    is_normal = diff.lower() == 'normal'

    # 1. 单调性
    for i in range(4):
        if wrs[i] < wrs[i+1]:
            reasons.append(f'T{i+1}({wrs[i]:.1f}) < T{i+2}({wrs[i+1]:.1f}) 倒挂')

    # 2. 档差底线
    min_gap = 5
    for i, g in enumerate(gaps):
        if g < min_gap:
            reasons.append(f'T{i+1}→T{i+2} gap={g:.1f}pp < 底线 {min_gap}pp')
        elif g < 10:
            warnings.append(f'T{i+1}→T{i+2} gap={g:.1f}pp < 推荐 10pp')

    # 3. Normal 3档 (T1=T2, T4=T5)
    if is_normal:
        if len(set((r.get('sd'),r.get('sc')) for r in recs)) != 3:
            reasons.append('Normal 需要 T1=T2, T4=T5 (3组独立配置)')

    # 4. 品质线（各档离目标 ≤10pp）
    quality = [abs(wr - t) for wr, t in zip(wrs, targets)]
    for i, q in enumerate(quality):
        if q > 15:
            reasons.append(f'T{i+1} 离目标 {q:.1f}pp > 15pp')
        elif q > 10:
            warnings.append(f'T{i+1} 离目标 {q:.1f}pp > 10pp（品质线）')

    total_q = sum(quality)

    # 判定
    if reasons:
        result = '不合格'
    elif warnings:
        result = '接近'
    else:
        result = '合格'

    return result, reasons, warnings, gaps, quality, total_q


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    spec = sys.argv[1]
    custom_targets = None
    custom_diff = None
    show_detail = '--show' in sys.argv

    for arg in sys.argv[2:]:
        if arg.startswith('--targets='):
            custom_targets = [float(x) for x in arg.split('=', 1)[1].split(',')]
        elif arg.startswith('--diff='):
            custom_diff = arg.split('=', 1)[1]
        elif arg == '--show':
            pass

    lv = int(spec)
    lv_s = str(lv)

    targets = custom_targets
    diff = custom_diff
    if not targets or not diff:
        t = et.get_target(lv)
        if t:
            if not targets:
                targets = t['tiers']
            if not diff:
                diff = t['diff']

    if not targets or len(targets) < 5:
        print(f'❌ L{lv}: 无法获取目标胜率')
        sys.exit(1)

    recs = pool.get_preferred_records(lv_s)
    uniq = pool.dedup_records(recs)
    if len(uniq) < 5:
        print(f'❌ L{lv}: 只有 {len(uniq)} 条数据')
        sys.exit(1)

    results = pool.find_best_monotonic(uniq, targets, difficulty=diff)
    if not results:
        print(f'❌ L{lv}: 无单调组合')
        sys.exit(1)

    combo = results[0][2]  # [(score, gaps, [recs]), ...]

    result, reasons, warnings, gaps, quality, total_q = validate(combo, targets, diff)

    print(f'\nL{lv} ({diff}) {"─" * 40}')
    for i, (r, t) in enumerate(zip(combo, targets)):
        print(f'  T{i+1}: {r["wr"]:.1f}% 目标{t:.0f}% 差{r["wr"]-t:+.1f}pp  sd={r.get("sd")} sc={r.get("sc")} ratios={r.get("ratios")} of={r.get("of")}')
    print(f'  gaps: {" / ".join(f"{g:.1f}" for g in gaps)}')
    print(f'  品质总分: {total_q:.1f}pp')
    print(f'  判定: {result}')
    for w in warnings:
        print(f'  ⚠️  {w}')
    for r in reasons:
        print(f'  ❌ {r}')


if __name__ == '__main__':
    main()
