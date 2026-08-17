#!/usr/bin/env python3
"""从数据池中找最佳单调五档组合（算法本体 + CLI 入口）。

本模块承载「找最优档位」的全部算法逻辑（2026-08-05 从 pool.py 拆分）：
  - find_best_monotonic      主入口：Normal 3-tier / Hard·SuperHard 5-tier
  - _gap_score               档位差分段罚分（gap 达标是主要考量）
  - target_pen_seg           目标偏差分段罚分（绿1/黄3/红8，防离目标离谱）
  - _bucket                  目标窗口取候选
  - _find_monotonic_3tier    Normal 3-tier 枚举
  - _config_key / _source_penalty / _norm_of  共用辅助（从 pool 导入）

数据层（get_all_records/dedup_records/filter_verified）在 tools/data/pool.py。

用法:
  python tools/find_best_combo.py 200
  python tools/find_best_combo.py 200 --targets 50,40,30,20,10
  python tools/find_best_combo.py 200 --targets 50,40,30,20,10 --top 3
  python tools/find_best_combo.py 151,162,165
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tools.data import pool
from tools.data.adapters import excel_target as et

# 共用辅助函数（数据层与算法层共用，保留在 pool.py，这里导入）
_config_key = pool._config_key
_source_penalty = pool._source_penalty
_norm_of = pool._norm_of


def _load_bands(difficulty):
    """从 rules.json 读档位差分档（单一真源），缺失用默认分档。"""
    _bands = {'gap_bands': {'wr_ge_70': 20, 'wr_ge_50': 15, 'wr_ge_30': 10, 'wr_lt_30': 6},
              'near_bands': {'wr_ge_70': 15, 'wr_ge_50': 10, 'wr_ge_30': 7, 'wr_lt_30': 4}}
    _rules_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                               'project-state', 'rules.json')
    if os.path.exists(_rules_path):
        try:
            _rules = json.load(open(_rules_path, encoding='utf-8'))
            _jr = _rules.get('judge_rules', {}).get(difficulty, {})
            if _jr:
                _bands = _jr
        except Exception:
            pass
    return _bands


def _load_tolerances():
    """读 rules.json 的 tolerance_pp / near_tolerance_pp（顶层，所有难度生效）。"""
    tolerance, near_tolerance = 0, 0
    _rules_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                               'project-state', 'rules.json')
    try:
        _rules = json.load(open(_rules_path, encoding='utf-8'))
        tolerance = float(_rules.get('judge_rules', {}).get('tolerance_pp', 0))
        near_tolerance = float(_rules.get('judge_rules', {}).get('near_tolerance_pp', 0))
    except Exception:
        pass
    return tolerance, near_tolerance


def _gap_score(wrs, difficulty='hard', targets=None):
    """档差品质分：越低越好。

    标准从 rules.json 读取（单一真源），消除与 judge_level 的漂移。
    2026-08-03 修复：从 rules.json 动态读分档值，不再硬编码。
    """
    score = 0
    is_normal = difficulty == 'normal'
    if is_normal:
        gaps = [(0, 2, wrs[0] - wrs[2]), (2, 4, wrs[2] - wrs[4])]
    else:
        gaps = [(i, i+1, wrs[i] - wrs[i+1]) for i in range(4)]

    _bands = _load_bands(difficulty)
    tolerance, near_tolerance = _load_tolerances()

    for i, j, g in gaps:
        hi = wrs[i]
        # 硬违规：<5% 重罚
        if g < 5:
            score += (5 - g) * 20
        if not is_normal and g > 40:
            score += (g - 40) * 10

        ok_lo, near_lo = 6, 4
        gb = _bands.get('gap_bands', {})
        nb = _bands.get('near_bands', {})
        if hi >= 70:
            ok_lo = gb.get('wr_ge_70', 20)
            near_lo = nb.get('wr_ge_70', 15)
        elif hi >= 50:
            ok_lo = gb.get('wr_ge_50', 15)
            near_lo = nb.get('wr_ge_50', 10)
        elif hi >= 30:
            ok_lo = gb.get('wr_ge_30', 10)
            near_lo = nb.get('wr_ge_30', 7)
        else:
            ok_lo = gb.get('wr_lt_30', 6)
            near_lo = nb.get('wr_lt_30', 4)

        if targets is not None:
            ok_target = targets[i] - targets[j]
            if ok_target != ok_lo:
                ok_lo = ok_target
                near_lo = int(ok_target * 0.7)

        if g < near_lo - near_tolerance:
            score += (ok_lo - g) * 5 + (near_lo - g) * 10
        elif g < ok_lo:
            if g < ok_lo - tolerance:  # 容差内不罚
                score += (ok_lo - g) * 5
        else:
            # 档位差富余奖励——gap 超出合格线越多越优。
            surplus = min(g - ok_lo, 35 - ok_lo)
            if surplus > 0:
                score -= surplus * 0.5

        if g > 35:
            score += (g - 35) * 3

    return score


def target_pen_seg(wrs, targets, g=1.0, y=3.0, r=8.0):
    """目标偏差分段罚分（2026-08-05 定稿：绿1/黄3/红8）。

    d = |wr - target|（pp），连续分段线性，处处正斜率，不硬淘汰不封顶：
      🟢 绿  d≤10        : 1.0·d           （斜率 1）
      🟡 黄  10<d≤15     : 10 + 3.0·(d-10)  （斜率 3）
      🔴 红  d>15        : 25 + 8.0·(d-15)  （斜率 8）

    关键：绿区斜率必须 >0（=1）——若为 0，gap 富余奖励(0.5/pp)会支配，
    算法重新选出「gap 大但离目标」的组合。红区 8/pp 与 gap 惩罚同量级，
    保证红档组合(>15pp)明显劣于绿/黄组合，但不硬淘汰。
    """
    total = 0.0
    for w, t in zip(wrs, targets):
        d = abs(w - t)
        if d <= 10:
            total += g * d
        elif d <= 15:
            total += g * 10 + y * (d - 10)
        else:
            total += g * 10 + y * 5 + r * (d - 15)
    return total


def _bucket(records, target, window=50, size=60):
    """取目标窗口内的记录，按距离排序取前 size 条。

    2026-07-31：bot/summary/phase0 同级，同级时新数据优先。
    2026-08-05：硬性过滤 wr<5（选最优档位不能出现 0 胜率 + <5% 是硬性违规线）。
    """
    bucket = [r for r in records if abs(r['wr'] - target) <= window and r['wr'] >= 5]
    if not bucket:
        return []
    bucket.sort(key=lambda r: r.get('created_at', ''), reverse=True)
    bucket.sort(key=lambda r: (abs(r['wr'] - target), _source_penalty(r.get('source',''), r.get('totalGames',0))))
    return bucket[:size]


def find_best_monotonic(records, targets, top_n=1, difficulty='hard'):
    """找最佳单调组合。

    Normal: 3-tier 窗口剪枝 O(k^3)
    Hard/SuperHard: 5-tier 窗口剪枝 + 内层gap预剪 O(k^5)
    """
    if len(records) < 3:
        return []

    if difficulty == 'normal':
        return _find_monotonic_3tier(records, targets, top_n)

    sorted_recs = sorted(records, key=lambda x: -x['wr'])
    WINDOW = 50

    buckets = [_bucket(sorted_recs, t, WINDOW) for t in targets]
    if any(not b for b in buckets):
        return []

    candidates = []
    for r1 in buckets[0]:
        for r2 in buckets[1]:
            if r2['wr'] > r1['wr']: continue
            g12 = r1['wr'] - r2['wr']
            if g12 < 4 or g12 > 40: continue
            for r3 in buckets[2]:
                if r3['wr'] > r2['wr']: continue
                g23 = r2['wr'] - r3['wr']
                if g23 < 4 or g23 > 40: continue
                for r4 in buckets[3]:
                    if r4['wr'] > r3['wr']: continue
                    g34 = r3['wr'] - r4['wr']
                    if g34 < 4 or g34 > 40: continue
                    for r5 in buckets[4]:
                        if r5['wr'] > r4['wr']: continue
                        g45 = r4['wr'] - r5['wr']
                        if g45 < 4 or g45 > 40: continue
                        recs5 = [r1, r2, r3, r4, r5]
                        keys = [_config_key(r) for r in recs5]
                        if len(set(keys)) < 5: continue
                        wrs = [r['wr'] for r in recs5]
                        target_score = target_pen_seg(wrs, targets)
                        source_score = sum(_source_penalty(r.get('source',''), r.get('totalGames',0)) for r in recs5) * 0.3
                        gap_score = _gap_score(wrs, difficulty, targets)
                        # 死亡分布分散度
                        dp = recs5[0].get('deathProfile')
                        death_score = 0
                        if dp:
                            worst = max(dp['early'], dp['transition'], dp['mid'], dp['late'])
                            if worst < 0.5:
                                death_score = -2
                            elif worst > 0.8:
                                death_score = 3
                        q = target_score + source_score + gap_score + death_score
                        gs = [g12, g23, g34, g45]
                        candidates.append((q, gs, recs5))
    if candidates:
        candidates.sort(key=lambda x: x[0])
        return candidates[:top_n]
    return []


def _find_monotonic_3tier(records, targets, top_n=1):
    """Normal 难度专用：T1=T2, T4=T5，窗口剪枝 O(k^3)。"""
    sorted_recs = sorted(records, key=lambda x: -x['wr'])
    t1, t3, t5 = targets[0], targets[2], targets[4]
    WINDOW = 50

    b1 = _bucket(sorted_recs, t1, WINDOW)
    b3 = _bucket(sorted_recs, t3, WINDOW)
    b5 = _bucket(sorted_recs, t5, WINDOW)
    if not (b1 and b3 and b5):
        return []

    candidates = []
    for r1 in b1:
        for r3 in b3:
            if r3['wr'] > r1['wr']: continue
            g13 = r1['wr'] - r3['wr']
            if g13 < 4: continue
            for r5 in b5:
                if r5['wr'] > r3['wr']: continue
                g35 = r3['wr'] - r5['wr']
                if g35 < 4: continue
                recs5 = [r1, r1, r3, r5, r5]
                wrs = [r1['wr'], r1['wr'], r3['wr'], r5['wr'], r5['wr']]
                target_score = target_pen_seg(wrs, targets)
                source_score = sum(_source_penalty(r.get('source',''), r.get('totalGames',0)) for r in [r1, r3, r5]) * 0.3
                gap_score = _gap_score(wrs, 'normal', targets)
                q = target_score + source_score + gap_score
                candidates.append((q, [g13, g35, 0, 0], recs5))
    if candidates:
        candidates.sort(key=lambda x: x[0])
        return candidates[:top_n]
    return []


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
        targets_all = et.read_targets(set(range(51, 201)))
        for lv_i, t in targets_all.items():
            diff_map[str(lv_i)] = t.get('diff', 'hard')
    except Exception:
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

        # 铁则（坑 2）：必须 filter_verified，phase1/phase2 不能参与选组合。
        # 用 get_all_records + filter_verified（bot/summary/phase0），
        # 不用 get_preferred_records（含 phase1/phase2，会让枚举 O(k^5) 爆炸
        # 且违反"phase1/2 不能用于入库决策"）。
        recs = pool.get_all_records(lv_s)
        recs = pool.filter_verified(recs)
        uniq = pool.dedup_records(recs)
        difficulty = diff_map.get(str(lv), 'hard')
        # 2026-08-06 修复：normal 关 3-tier 只需 3 条数据（T1/T3/T5），
        # 不应硬性要求 5 条（之前 <5 拦截导致 normal 关 3 条数据误报"无法组成五档"，
        # 如 L110/L122/L136）。hard/superhard 才需 5 条。
        min_recs = 3 if difficulty == 'normal' else 5
        if len(uniq) < min_recs:
            print(f'L{lv}: 只有 {len(uniq)} 条有效数据(verified)，{"无法组成三档(normal)" if difficulty=="normal" else "无法组成五档"}')
            continue

        results = find_best_monotonic(uniq, targets, top_n=top_n, difficulty=difficulty)
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
                if dp['transition'] > 0.5:
                    print(f'  \u26a1 过渡段死亡{trans_d:.0f}% \u2192 优先降 ratios 前段权重或降 sd')
                elif dp['mid'] > 0.6:
                    print(f'  \u26a1 中期死亡{mid_d:.0f}% \u2192 优先调 of 或换 ratios 分布')
                elif dp['late'] > 0.6:
                    print(f'  \u26a1 后期死亡{late_d:.0f}% \u2192 优先降 of 或后段 ratios 放轻')
            print()


if __name__ == '__main__':
    main()