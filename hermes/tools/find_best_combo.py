#!/usr/bin/env python3
"""从数据池中找最佳单调五档组合（算法本体 + CLI 入口）。

本模块承载「找最优档位」的全部算法逻辑（2026-08-05 从 pool.py 拆分）：
  - find_best_monotonic      主入口：Normal 3-tier / Hard·SuperHard 5-tier
  - _gap_score               目标体验档差距离（gap 是主要考量）
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
import sys, os, json, math
from functools import lru_cache
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tools.data import pool
from tools.data.adapters import excel_target as et

# 共用辅助函数（数据层与算法层共用，保留在 pool.py，这里导入）
_config_key = pool._config_key
_source_penalty = pool._source_penalty
_norm_of = pool._norm_of

# Backward-compatible export for agent_analyze and external callers. The new
# banded selector does not use this scalar weight for ranking.
QUALITY_TARGET_WEIGHT = 0.5


def _effective_pairs(difficulty):
    """返回实际参与质量评价的档差对。

    Normal 只有 T1/T3/T5 三个有效配置；Hard/SuperHard 使用四个相邻档差。
    """
    if difficulty == 'normal':
        return [(0, 2), (2, 4)]
    return [(i, i + 1) for i in range(4)]


def _effective_indices(difficulty):
    """返回实际配置索引，避免 Normal 的重复槽位重复计权。"""
    if difficulty == 'normal':
        return [0, 2, 4]
    return list(range(5))


def _target_penalty_value(distance, g=1.0, y=3.0, r=8.0):
    """单档目标偏差罚分；q 中始终为非负距离。"""
    if distance <= 10:
        return g * distance
    if distance <= 15:
        return g * 10 + y * (distance - 10)
    return g * 10 + y * 5 + r * (distance - 15)


def _experience_gap_error(wr_hi, wr_lo, target_hi, target_lo):
    """实际/目标体验档差的距离。

    以 log2(预期尝试次数比)表达档差：
      log2(E_low / E_high) = log2(wr_high / wr_low)
    返回绝对误差，避免 gap 超过目标时继续获得奖励。
    结果乘 100 与 pp 罚分保持同一数量级，仍由 q 的 gap 项主导。
    """
    floor = 5.0  # wr<5 是 Judge 硬违规；这里仅防止日志数值异常
    actual_ratio = max(float(wr_hi), floor) / max(float(wr_lo), floor)
    target_ratio = max(float(target_hi), floor) / max(float(target_lo), floor)
    return abs(math.log2(actual_ratio / target_ratio)) * 100.0


def _gap_score(wrs, difficulty='hard', targets=None):
    """目标体验档差距离：越低越好，且始终非负。

    旧实现会奖励超过目标的 gap，导致「离目标更远」的组合可能 q 更低。
    新实现比较实际档差与 Excel 目标档差的 log2 尝试次数比例：gap 不足和
    gap 过大都产生距离，不再奖励过大的 gap。Judge 的 gap 硬/软边界仍由
    judge_level.py 独立负责。
    """
    pairs = _effective_pairs(difficulty)
    if targets is None:
        # 兼容旧的直接调用：没有 Excel 目标时只返回 0，正式选档入口要求 targets。
        return 0.0
    return sum(
        _experience_gap_error(wrs[i], wrs[j], targets[i], targets[j])
        for i, j in pairs
    )


def target_pen_seg(wrs, targets, g=1.0, y=3.0, r=8.0):
    """目标偏差分段罚分（绿1/黄3/红8），越低越好。

    d = |wr - target|（pp），连续分段线性，处处正斜率，不硬淘汰、不封顶。
    该函数只表示目标偏差距离；档差质量由 `_gap_score` 单独计算。
    """
    return sum(
        _target_penalty_value(abs(w - t), g=g, y=y, r=r)
        for w, t in zip(wrs, targets)
    )


def _quality_target_score(wrs, targets, difficulty):
    """目标偏差质量分；Normal 按三个有效配置计权。"""
    indices = _effective_indices(difficulty)
    return sum(
        _target_penalty_value(abs(wrs[i] - targets[i]))
        for i in indices
    )


def _quality_score(wrs, targets, difficulty):
    """分层质量分，越低越好。

    Priority is deliberate rather than one tunable global weight:
      1. keep every effective gap inside ``target_gap - slack``;
      2. prefer DB-green target deviations (strictly <10pp);
      3. prefer smaller target deviation;
      4. finally prefer gaps nearer the Excel target gap, with no surplus bonus.

    Slack is proportional to the target gap: 20→5, 15→4, 10→3, 6→2.
    The existing 2pp measurement tolerance is applied only to the selection
    band; Judge admission rules remain separate.
    """
    pairs = _effective_pairs(difficulty)
    tolerance_pp, db_green_max = _selection_limits()
    band_deficit = 0.0
    gap_distance = 0.0
    for i, j in pairs:
        standard_gap = _standard_gap_target(wrs[i], difficulty)
        actual_gap = float(wrs[i]) - float(wrs[j])
        slack = max(2, min(5, math.ceil(max(0.0, standard_gap) * 0.25)))
        lower = standard_gap - slack
        band_deficit += max(0.0, lower - tolerance_pp - actual_gap)
        # Once inside the acceptable band, compare closeness to the Excel
        # target-gap difference; do not add a separate strict-gap penalty.
        target_gap = float(targets[i]) - float(targets[j])
        gap_distance += abs(actual_gap - target_gap)

    non_green_count = sum(
        1 for wr, target in zip(wrs, targets)
        if abs(float(wr) - float(target)) >= db_green_max
    )
    target_penalty = _quality_target_score(wrs, targets, difficulty)
    # Lexicographic bands encoded as a scalar: acceptable-band failure dominates
    # color; non-green dominates target distance; gap closeness only breaks ties.
    return (
        band_deficit * 10000.0
        + non_green_count * 1000.0
        + target_penalty
        + gap_distance * 0.01
    )


def _legacy_quality_score(wrs, targets, difficulty):
    """Pre-banded score used only as a non-regression fallback."""
    return _gap_score(wrs, difficulty, targets) + 0.5 * _quality_target_score(
        wrs, targets, difficulty
    )


def _judgment_rank(records, targets, difficulty):
    """Return Judge rank for candidate records without changing round state."""
    try:
        from tools.judge_level import check_judgment
        wrs = [float(record['wr']) for record in records]
        result, _ = check_judgment(
            {f'T{i + 1}': wrs[i] for i in range(5)},
            difficulty,
            targets,
        )
        return {'合格': 3, '接近': 2, '不合格': 1}.get(result, 0)
    except Exception:
        return 0


def _finalize_candidates(candidates, targets, difficulty, top_n):
    """Apply new ranking, then prevent a selection-quality regression."""
    candidates.sort(key=lambda item: item[0])
    new_best = candidates[0]
    legacy_best = min(candidates, key=lambda item: item[1])
    if _judgment_rank(new_best[3], targets, difficulty) < _judgment_rank(
        legacy_best[3], targets, difficulty
    ):
        ordered = [legacy_best] + [item for item in candidates if item is not legacy_best]
    else:
        ordered = candidates
    return [(item[0], item[2], item[3]) for item in ordered[:top_n]]


@lru_cache(maxsize=1)
def _selection_limits():
    """Read selection tolerances from the single project rules source."""
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        'project-state', 'rules.json')
    try:
        with open(path, encoding='utf-8') as fh:
            rules = json.load(fh).get('judge_rules', {})
        return (
            float(rules.get('tolerance_pp', 2)),
            float(rules.get('target_deviation', {}).get('db_green_max', 10)),
        )
    except Exception as exc:
        raise RuntimeError(f'cannot load selection rules: {path}: {exc}') from exc


@lru_cache(maxsize=8)
def _standard_gap_target(wr_hi, difficulty):
    """Return the WR-band gap standard (20/15/10/6) from rules.json."""
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        'project-state', 'rules.json')
    try:
        with open(path, encoding='utf-8') as fh:
            rules = json.load(fh).get('judge_rules', {})
        bands = rules.get(difficulty, {}).get('gap_bands', {})
        if float(wr_hi) >= 70:
            return float(bands.get('wr_ge_70', 20))
        if float(wr_hi) >= 50:
            return float(bands.get('wr_ge_50', 15))
        if float(wr_hi) >= 30:
            return float(bands.get('wr_ge_30', 10))
        return float(bands.get('wr_lt_30', 6))
    except Exception as exc:
        raise RuntimeError(f'cannot load gap bands: {path}: {exc}') from exc


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
                        # q 只表示档位质量：gap 主项 + 目标偏差次项。
                        # 来源和死亡分布属于置信度/诊断信息，不污染质量排序。
                        q = _quality_score(wrs, targets, difficulty)
                        legacy_q = _legacy_quality_score(wrs, targets, difficulty)
                        gs = [g12, g23, g34, g45]
                        candidates.append((q, legacy_q, gs, recs5))
    if candidates:
        return _finalize_candidates(candidates, targets, difficulty, top_n)
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
                # Normal 只按 T1/T3/T5 三个有效配置计算质量分。
                q = _quality_score(wrs, targets, 'normal')
                legacy_q = _legacy_quality_score(wrs, targets, 'normal')
                candidates.append((q, legacy_q, [g13, g35, 0, 0], recs5))
    if candidates:
        return _finalize_candidates(candidates, targets, 'normal', top_n)
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
                print(f'  ── #{rank+1} 品质总分 {q:.2f} ──')
            for i, (r, t) in enumerate(zip(recs, targets)):
                label = 'T%d' % (i+1)
                diff = r['wr'] - t
                # 2026-08-18：sc 与 ratios 数量一致性告警（L70/103/115/137 抄配置踩坑根因）
                sc_val = str(r.get('sc',''))
                ratios_str = str(r.get('ratios',''))
                n_ratios = len([x for x in ratios_str.split(',') if x.strip()]) if ratios_str else 0
                n_sc = int(sc_val) if str(sc_val).isdigit() else 0
                if n_ratios and n_sc and n_ratios != n_sc:
                    print(f'  ⚠️  {label}: sc={sc_val} 但 ratios 有 {n_ratios} 个值 ({ratios_str})——配置不合法，抄写时注意!')
                print('  %s %5.1f%% %+7.1fpp %4s %4s %20s %6s %5d %8s' % (
                    label, r['wr'], diff,
                    r.get('sd',''), r.get('sc',''),
                    ratios_str, str(r.get('of','')),
                    r.get('totalGames',0), r.get('source','')))
            print(f'  gaps: {gs[0]:.1f}/{gs[1]:.1f}/{gs[2]:.1f}/{gs[3]:.1f} 品质={q:.2f}')

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