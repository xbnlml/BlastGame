#!/usr/bin/env python3
"""自动设计探针配置。

逻辑: 遍历 phase2 候选，逐一加入 bot400 池，看哪个对整体 5 档结构提升最大。
不盯档位，只看池子整体。phase2 无候选时查经验知识库 (param_knowledge)。

用法:
  python design_probes.py 77
  python design_probes.py 77 --write
"""
import json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
PROBE_CFG = os.path.join(TOOLS_DIR, 'probe_configs.json')

# ── 安静模式 ──
_QUIET = os.environ.get('DESIGN_PROBES_QUIET') == '1'

def _print(*a, **kw):
    if not _QUIET:
        print(*a, **kw)


from tools.data import pool
from tools.data.adapters import excel_target as et


def _load_rules():
    """从 rules.json 读 judge_rules（单一真源，代码独立实现，不 import 其他模块）。"""
    _rules_path = os.path.join(os.path.dirname(TOOLS_DIR), 'project-state', 'rules.json')
    try:
        with open(_rules_path, encoding='utf-8') as f:
            return json.load(f).get('judge_rules', {})
    except Exception:
        return {}


def _band_for(hi_wr, targets, i, j, rules):
    """按较高档 WR 分档得 (ok_lo, near_lo)；目标档位差冲突时目标优先（与判定标准同源）。"""
    gb = rules.get('gap_bands', {'wr_ge_70': 20, 'wr_ge_50': 15, 'wr_ge_30': 10, 'wr_lt_30': 6})
    nb = rules.get('near_bands', {'wr_ge_70': 15, 'wr_ge_50': 10, 'wr_ge_30': 7, 'wr_lt_30': 4})
    ok_lo, near_lo = 6, 4
    if hi_wr >= 70:
        ok_lo, near_lo = gb['wr_ge_70'], nb['wr_ge_70']
    elif hi_wr >= 50:
        ok_lo, near_lo = gb['wr_ge_50'], nb['wr_ge_50']
    elif hi_wr >= 30:
        ok_lo, near_lo = gb['wr_ge_30'], nb['wr_ge_30']
    if targets is not None:
        ok_target = targets[i] - targets[j]
        if ok_target != ok_lo:  # 冲突 → 目标档位差优先（×0.7 接近）
            ok_lo = ok_target
            near_lo = int(ok_target * 0.7)
    return ok_lo, near_lo


def analyze_gaps(base_wrs, targets, diff):
    """缺口分析：每个判定对 gap vs 合格线，gap 优先（设计阶段无容差，理想化）。

    返回 (gaps, hard_specs)：
      gaps: [{pair, gap, ok_lo, near_lo, severity(fail/near/ok), shortfall}]
      hard_specs: 硬违规转的缺口 [{tier, direction, need}]
    """
    rules = _load_rules().get(diff, {})
    pairs = [(0, 2), (2, 4)] if diff == 'normal' else [(i, i + 1) for i in range(4)]
    gaps = []
    for i, j in pairs:
        g = base_wrs[i] - base_wrs[j]
        ok_lo, near_lo = _band_for(base_wrs[i], targets, i, j, rules)
        if g < near_lo:  # 不合格（缺口硬）
            sev, shortfall = 'fail', ok_lo - g  # 设计阶段理想化：修就修到合格线 ok_lo
        elif g < ok_lo:  # 接近（缺口软）
            sev, shortfall = 'near', ok_lo - g
        else:
            sev, shortfall = 'ok', 0
        gaps.append({'pair': (i, j), 'gap': g, 'ok_lo': ok_lo, 'near_lo': near_lo,
                     'severity': sev, 'shortfall': shortfall})

    # 硬违规 → 缺口规格（优先级最高）
    hard_specs = []
    for i in range(5):
        if base_wrs[i] < 5:
            hard_specs.append({'tier': i, 'direction': 'raise', 'need': 5.0})
    if diff == 'normal' and base_wrs[2] < 60:  # Normal T3<60
        hard_specs.append({'tier': 2, 'direction': 'raise', 'need': 60.0})
    if diff in ('hard', 'superhard'):
        for i in range(4):
            g = base_wrs[i] - base_wrs[i + 1]
            if g > 40:
                hard_specs.append({'tier': i, 'direction': 'lower',
                                   'need': base_wrs[i] - (g - 40)})
    low = [i for i in range(5) if base_wrs[i] < 10]
    if len(low) > 1:
        for i in low[1:]:
            hard_specs.append({'tier': i, 'direction': 'raise', 'need': 10.0})
    return gaps, hard_specs


def _simulate_gap_status(wrs, targets, diff):
    """模拟一组 WR 的判定对状态（gap 优先，无容差）。返回每对 (severity, ok_lo)。"""
    rules = _load_rules().get(diff, {})
    pairs = [(0, 2), (2, 4)] if diff == 'normal' else [(i, i + 1) for i in range(4)]
    status = []
    for i, j in pairs:
        g = wrs[i] - wrs[j]
        ok_lo, near_lo = _band_for(wrs[i], targets, i, j, rules)
        if g < near_lo:
            sev = 'fail'
        elif g < ok_lo:
            sev = 'near'
        else:
            sev = 'ok'
        status.append({'pair': (i, j), 'gap': g, 'ok_lo': ok_lo, 'severity': sev})
    return status


def _fix_ok(new_wrs, targets, diff, target_pair):
    """检查模拟修复：目标判定对已达标，且无其他判定对从 ok 变 fail/near。
    返回 (ok, 说明)。"""
    status = _simulate_gap_status(new_wrs, targets, diff)
    target_ok = False
    for st in status:
        if st['pair'] == target_pair:
            target_ok = st['severity'] == 'ok'
            if not target_ok:
                return False, f'目标对仍 {st["severity"]} gap={st["gap"]:.1f}<{st["ok_lo"]}'
    for st in status:
        if st['pair'] != target_pair and st['severity'] in ('fail', 'near'):
            return False, f'破坏相邻对 {st["pair"]} -> {st["severity"]} gap={st["gap"]:.1f}'
    return True, ''


def _derive_needs(targets, diff, rules, pool_records, tol=5):
    """反推每档需求胜率（2026-08-06 用户定稿：反推不穷举）。

    从低档往高档推，每档需求 = max(目标, 硬违规下限, 低档可用值+gap合格线)。
    低档可用值 = 池子里覆盖低档需求段的配置 wr（配置自由流动，不绑定档位）。
    normal：T1=T2、T4=T5 共享配置，按组推导（组内共享同一需求/覆盖）。
    返回 needs[5]（每档需求胜率）与 covered[5]（池子是否覆盖该需求段）。
    """
    is_normal = diff == 'normal'
    # 判定对：normal (T1,T3)/(T3,T5)；其他 (T1,T2)(T2,T3)(T3,T4)(T4,T5)
    pairs = [(0, 2), (2, 4)] if is_normal else [(i, i + 1) for i in range(4)]
    # 推导组（共享档位合并）：normal [T4/T5, T3, T1/T2]；其他 [T5, T4, T3, T2, T1]
    if is_normal:
        groups = [(4, 3), (2,), (1, 0)]  # (低档成员, 高档成员)
    else:
        groups = [(4,), (3,), (2,), (1,), (0,)]
    needs = list(targets)
    covered = [False] * 5
    # 每组的"该档位实际可用值"（覆盖配置 wr 或需求值）
    group_val = {}

    def _pool_best_in(lo, hi, exclude=None):
        """池子里 wr∈[lo,hi] 且未用过的配置——选**最接近需求段中点**的
        （verified 优先）。2026-08-06：不选最高——低档值虚高会连带抬高
        高档需求（L102：T3 段选 70.6 而非 63.2 → T1 需求被抬到 90）。
        2026-08-06 用户纠正：局数下限 ≥10（只挡测试残留级如 L102 的 2 局；
        bot/summary/phase0 可靠数据不限局数——贝叶斯提前停的 summary
        如 L128 9.3/150局、L154 8.6/140局 要保留）。"""
        best = None
        mid = (lo + hi) / 2
        for r in pool_records:
            if exclude is not None and pool._config_key(r) in exclude:
                continue
            if lo <= r['wr'] <= hi and r.get('totalGames', 0) >= 10:
                rank = 0 if r.get('source') in ('bot', 'summary', 'phase0') else 1
                dist = abs(r['wr'] - mid)
                if best is None:
                    best = r
                else:
                    brank = 0 if best.get('source') in ('bot', 'summary', 'phase0') else 1
                    if rank < brank or (rank == brank and dist < abs(best['wr'] - mid)):
                        best = r
        return best

    used = set()
    # ── 阶段 1：推导所有组的需求（不含覆盖检查，保证 gap 链完整）──
    for gidx, group in enumerate(groups):
        lo_member, hi_member = group[0], group[-1]
        # 组目标 = 组内各档目标的最大值（共享配置要满足所有共享档）
        need = max(targets[m] for m in group)
        # 硬违规下限
        if is_normal and 2 in group:
            need = max(need, 60.0)  # Normal T3≥60
        if need < 5:
            need = 5.0  # wr<5 硬违规
        # gap 约束：该组是某判定对的高档时，需求 ≥ 低档组值 + ok_lo
        for (a, b) in pairs:
            if a in group and b not in group:
                # 该组是高档 (a)，低档 b 在更低的组（已推导）
                b_val = group_val.get(b, needs[b])
                ok_lo, _ = _band_for(need, targets, a, b, rules)
                need = max(need, b_val + ok_lo)
        needs[lo_member] = need
        needs[hi_member] = need if hi_member != lo_member else needs[lo_member]
        group_val[lo_member] = need
        group_val[hi_member] = need if hi_member != lo_member else group_val[lo_member]

    # ── 阶段 2：统一覆盖检查（所有组值已定，gap 可行性判断完整）──
    for gidx, group in enumerate(groups):
        lo_member, hi_member = group[0], group[-1]
        need = needs[lo_member]
        lo_win, hi_win = need - tol, need + tol
        r = _pool_best_in(lo_win, hi_win, used)
        # 2026-08-10 修复：覆盖检查必须验证"组合可行性"——候选不仅要落在
        # 需求段内，还要能与相邻档组成合法组合（gap 约束）。
        # L163 教训：T4 段有 58/56 候选（bot），但 T3 组值=65 → gap=7<15pp
        # 组合不可行 → 实际只能用 39.5。段内候选被 gap 排除 = 未覆盖（需探针）。
        if r is not None and len(groups) > 1:
            feasible = True
            for (a, b) in pairs:
                # 本组是高档 (a)：候选必须 ≥ 低档组值 + ok_lo
                if a in group and b not in group and b in group_val:
                    ok_lo, _ = _band_for(need, targets, a, b, rules)
                    if r['wr'] < group_val[b] + ok_lo - 0.5:
                        feasible = False
                        break
                # 本组是低档 (b)：候选必须 ≤ 高档组值 - ok_lo
                if b in group and a not in group and a in group_val:
                    ok_lo, _ = _band_for(group_val[a], targets, a, b, rules)
                    if r['wr'] > group_val[a] - ok_lo + 0.5:
                        feasible = False
                        break
            if not feasible:
                r = None
        if r is not None:
            group_val[lo_member] = r['wr']
            used.add(pool._config_key(r))
            # 2026-08-06：只有 verified（bot/summary/phase0）算"已覆盖"——
            # phase1/2 配置必须验证才能用，它们本身就是探针候选（不覆盖）。
            is_verified = r.get('source') in ('bot', 'summary', 'phase0')
            covered[lo_member] = is_verified
            covered[hi_member] = is_verified if hi_member != lo_member else covered[lo_member]
        else:
            group_val[lo_member] = need
            covered[lo_member] = False
            covered[hi_member] = False if hi_member != lo_member else covered[lo_member]
    return needs, covered


def plan_specs(gaps, hard_specs, targets, base_wrs, diff, pool_records=None):
    """定探针目标胜率：反推法（2026-08-06 用户定稿 v3）。

    反推每档需求 → 池子覆盖检查 → 未覆盖的档位 = 探针目标段。
    覆盖的档位不探（配置自由流动，组合时直接用）。
    """
    RED = 10  # 2026-08-10：判定收紧（target_deviation.max 15→10），探针红区同步 15→10，防白打黄区
    specs = []

    def _add(tier, direction, probe_wr, need):
        for s in specs:
            if s['tier'] == tier and s['direction'] == direction and abs(s['probe_wr'] - probe_wr) < 1:
                return  # 同档同方向同目标已存在
        specs.append({'tier': tier, 'probe_wr': probe_wr, 'direction': direction, 'need': need})

    # 反推需求 + 覆盖检查
    rules = _load_rules().get(diff, {})
    pool_records = pool_records or []
    needs, covered = _derive_needs(targets, diff, rules, pool_records)

    # 硬违规 → 强制探针（即使目标段被覆盖，硬违规档位必须验证）
    for hs in hard_specs:
        tier = hs['tier']
        if hs['direction'] == 'raise':
            need = hs['need']
            probe_wr = max(needs[tier], need) if needs[tier] else need
            probe_wr = min(probe_wr, targets[tier] + RED)
            _add(tier, 'raise', probe_wr, need)
        else:
            need = hs['need']
            probe_wr = min(needs[tier], need) if needs[tier] else need
            probe_wr = max(probe_wr, targets[tier] - RED)
            _add(tier, 'lower', probe_wr, need)

    # 2026-08-17 新增：gap 缺口 → 探针打能拉开档位差的档（L158 根因：
    # 目标段都"有 verified"但 T1→T3 gap 不够，被旧逻辑判 covered 全跳过 → 5 槽浪费）。
    # gap 缺口 = 判定对 (hi档, lo档) 的 gap 低于合格线（含接近带）→ 该对必须拉开。
    # 用 gaps 输入直接处理（gaps = 判定对缺口列表）
    for g in gaps:
        if g['severity'] == 'ok':
            continue
        a, b = g['pair']
        shortfall = g['shortfall']
        # 该对缺口：拉高 hi 档 或 拉低 lo 档（探针方向：hi 档 raise / lo 档 lower）
        # 优先探 hi 档 raise（拉大 gap 最直接）；若 hi 档已接近上限则探 lo 档 lower
        hi_wr = base_wrs[a] if base_wrs else targets[a]
        if hi_wr + 5 <= targets[a] + RED:
            _add(a, 'raise', min(base_wrs[a] if base_wrs else targets[a], targets[a] + RED) + min(shortfall, 5), targets[a])
        # lo 档也补一个 lower（若还有槽位，_expand_gradients 会处理梯度）

    # 未满足的档位 → 探针目标段（2026-08-17 重构：covered = "已满足" 而非 "有记录"）
    # 规则：离目标 >5pp 或 gap 有缺口的档位才是缺口 → 探针；已满足（≤5pp 且 gap 达标）不探。
    # phase1/2 候选本身就是探针（验证次数少，用 bot 补验证），不占"已满足"。
    for i, need in enumerate(needs):
        if covered[i]:
            # covered=True 只表示池子有 verified 记录在该段，还需确认是否真"满足"
            # （离目标 ≤5pp）。若 verified 最优离目标仍 >5pp，仍是缺口 → 探针。
            cur = base_wrs[i] if base_wrs else None
            if cur is not None and abs(cur - targets[i]) <= 5:
                continue  # 已满足，不浪费槽位
        # 缺口档：方向 = 需求 vs 当前最优
        cur = base_wrs[i] if base_wrs else targets[i]
        direction = 'raise' if need >= cur else 'lower'
        probe_wr = min(need, targets[i] + RED) if direction == 'raise' else max(need, targets[i] - RED)
        _add(i, direction, probe_wr, need)

    # 全 ok 无缺口 → 目标带覆盖探针（5 槽按目标档位）
    if not specs:
        for i, t in enumerate(targets):
            if len(specs) >= 5:
                break
            _add(i, 'verify', t, None)
        return specs[:5]

    return _expand_gradients(specs, targets)

def _expand_gradients(specs, targets, RED=10):
    """槽位分配：5 槽全打选中的目标段（每段多配置），不分散。
    2026-08-06：提取公共函数——no_combo 分支也用它（L154 之前只有
    2 个 spec 没扩展，fill_remaining 把 T5@10 填了 4 槽、50+ 段只剩 1 槽）。"""
    segs = []
    for s in specs:
        key = (s['tier'], s['direction'])
        if key not in [x for x in segs]:
            segs.append(key)
    guard = 0  # 防死循环：一轮无新增就退出
    while len(specs) < 5 and guard < 20:
        guard += 1
        added_any = False
        for (tier, direction) in segs:
            if len(specs) >= 5:
                break
            base_spec = next(s for s in specs if s['tier'] == tier and s['direction'] == direction)
            if direction == 'raise':
                grad = base_spec['probe_wr'] + 5
                if grad <= targets[tier] + RED and not any(
                        s['tier'] == tier and abs(s['probe_wr'] - grad) < 1 for s in specs):
                    specs.append({'tier': tier, 'probe_wr': grad, 'direction': 'raise', 'need': None})
                    added_any = True
            else:
                grad = base_spec['probe_wr'] - 5
                if grad >= targets[tier] - RED and not any(
                        s['tier'] == tier and abs(s['probe_wr'] - grad) < 1 for s in specs):
                    specs.append({'tier': tier, 'probe_wr': grad, 'direction': 'lower', 'need': None})
                    added_any = True
        if not added_any:
            break
    return specs[:5]


def _tune_from_nearest(spec, verified_pool, used_keys):
    """2026-08-17 邻近微调：缺口段无直接候选时，找已验证池里离缺口最近的配置，
    在其基础上微调 sd/of（保持 ratios），生成探针。

    目标比最近配置高 → 降 sd/of（更易）；目标低 → 升 sd/of（更难）。
    步进 = min(3, |目标差|/10)。返回探针 dict 或 None（无近邻/没变化/已用）。
    """
    if not verified_pool:
        return None
    np_wr = spec['probe_wr']
    nearest = None
    for r in verified_pool:
        if r.get('wr', 0) < 5:
            continue
        if pool._config_key(r) in used_keys:
            continue
        if nearest is None or abs(r['wr'] - np_wr) < abs(nearest['wr'] - np_wr):
            nearest = r
    if nearest is None:
        return None
    nr = nearest['wr']
    if abs(nr - np_wr) <= 5:
        return None  # 近邻已满足，不该探
    sd = int(nearest.get('sd', 0) or 0)
    of = float(nearest.get('of', 0.5) or 0)
    ratios = str(nearest.get('ratios', '1,1,1,1,1') or '').strip()
    if not ratios:
        return None
    step = min(3, max(1, round(abs(np_wr - nr) / 10)))
    if np_wr > nr:
        sd = max(0, sd - step)
        of = max(0.0, of - 0.1 * step)
    else:
        sd = sd + step
        of = min(1.0, of + 0.1 * step)
    probe = {'sd': sd,
             'sc': len(ratios.split(',')),
             'ratios': ratios,
             'of': round(of, 2),
             '_probe_wr': np_wr, '_base_wr': nr}
    if probe['sd'] == int(nearest.get('sd', 0) or 0) and abs(probe['of'] - float(nearest.get('of', 0.5) or 0)) < 0.01:
        return None  # 没实际变化
    if pool._config_key(probe) in used_keys:
        return None
    used_keys.add(pool._config_key(probe))
    return probe


def find_candidates(specs, phase12, verified_keys, verified_pool=None):
    """全池子找候选（含 phase1/phase2）：按缺口 band 找，找到的 phase1/2 配置直接作探针。

    返回 probes 列表：每个 spec 至少 1 个候选；specs 不足 5 时对已有 spec
    循环取更多候选（不同 ratios）补到 5 槽（多槽打同段提高命中率）。

    2026-08-17 用户要求：基于现有数据调整是主要途径——缺口段无 phase1/2 候选时，
    优先用已验证配置（bot/summary/phase0）邻近微调，而不是全新自设计。
    """
    probes = []
    used_keys = set(verified_keys)
    # 第一轮：每个 spec 各占 1 槽（2026-08-06 planner 审查修复——无候选
    # 的 spec 之前被跳过导致槽位错位：L154 (0,50.5) 无候选被跳过，
    # (4,10) 的候选被反复填充 → 50+ 段 0 槽、10 段 5 槽）
    for spec in specs:
        if len(probes) >= 5:
            break
        # 2026-08-17 修正 band：phase1/2 候选"验证后可能到目标段"，band 从 ±5 放宽到 ±10
        # （目标 45 → 候选 35-55）。之前 ±5 太窄，L158 T4/T5 目标 45 时 phase1/2 的
        # 36-38% 配置被漏掉 → 直接自设计，违反"优先验证、没有合适的再自设计"铁则。
        # 仍守住 ±15 段外硬凑铁则（L153：wr=75 不可能到 87.5）。
        lo = spec['probe_wr'] - 10
        hi = spec['probe_wr'] + 10
        cands = [r for r in phase12 if lo <= r['wr'] <= hi
                 and pool._config_key(r) not in used_keys and r.get('wr', 0) >= 5]
        # 2026-08-06 用户铁则：段内（±5）无候选 → 该槽交 fill_remaining 自设计，
        # **绝不放宽 ±15 段外硬凑**（L153：需求 87.5 拿 phase1 wr=75 的配置标 87.5
        # 被用户否决——75 的配置验证后也不可能到 87.5）。
        if cands:
            pick = min(cands, key=lambda r: abs(r['wr'] - spec['probe_wr']))
            sc = len(str(pick.get('ratios', '')).split(','))
            # 2026-08-06 效率原则：phase12 现成配置一律保留原参数验证——
            # 它是已验证过的数据点（虽然不可直接入库），验证成本低、命中率高；
            # 重压 sd/of 只在完全没有候选时的自设计（fill_remaining）里做。
            probe = {'sd': int(pick['sd']), 'sc': sc,
                     'ratios': str(pick.get('ratios', '')),
                     'of': float(pick.get('of', 0.5)),
                     '_probe_wr': spec['probe_wr']}
            probe_key = pool._config_key(probe)
            if probe_key not in used_keys:
                probes.append(probe)
                used_keys.add(pool._config_key(pick))
                used_keys.add(probe_key)
            else:
                # 撞 verified → 基于 verified 邻近微调（2026-08-17）
                tuned = _tune_from_nearest(spec, verified_pool, used_keys)
                probes.append(tuned if tuned is not None else None)
        else:
            # 无 phase1/2 候选 → 基于 verified 邻近微调（2026-08-17 主要途径）
            tuned = _tune_from_nearest(spec, verified_pool, used_keys)
            if tuned is not None:
                probes.append(tuned)
            else:
                probes.append(None)  # 无候选也无近邻 → 占位交自设计
    # 第二轮起：按 spec 顺序循环取更多候选（不同 ratios）补到 5 槽
    # 2026-08-06 修复：只在"该 spec 第一轮有候选"时追加（None 占位不追加），
    # 且追加前先检查 len<5——L154 曾因 (4,10) 第二轮追加挤掉 (0,55.5) 的占位
    idx = 0
    while len(probes) < 5 and idx < len(specs) * 5:
        spec = specs[idx % len(specs)]
        idx += 1
        lo = spec['probe_wr'] - 10
        hi = spec['probe_wr'] + 10
        cands = [r for r in phase12 if lo <= r['wr'] <= hi
                 and pool._config_key(r) not in used_keys and r.get('wr', 0) >= 5]
        if not cands:
            continue
        pick = min(cands, key=lambda r: abs(r['wr'] - spec['probe_wr']))
        sc = len(str(pick.get('ratios', '')).split(','))
        probe = {'sd': int(pick['sd']), 'sc': sc,
                 'ratios': str(pick.get('ratios', '')),
                 'of': float(pick.get('of', 0.5)),
                 '_probe_wr': spec['probe_wr']}
        probe_key = pool._config_key(probe)
        if probe_key not in used_keys:
            probes.append(probe)
            used_keys.add(pool._config_key(pick))
            used_keys.add(probe_key)
    return probes


_KB_CACHE = None

def _get_kb():
    """知识库懒加载缓存（2026-08-06: 全量统计 ~135s，每次重建会拖垮流程）。"""
    global _KB_CACHE
    if _KB_CACHE is None:
        from tools.param_knowledge import _load_all_data, build_knowledge_base
        _KB_CACHE = build_knowledge_base(_load_all_data())
    return _KB_CACHE


def _infer_sd_from_pool(probe_wr, pool_records):
    """关卡自适应 sd 估计：用该关池子数据里 wr 最接近 probe_wr 的记录的实际 sd。

    2026-08-10 修复：_estimate_sd 是全局假设（sd10=75%），但关与关之间
    sd↔wr 关系不同（L57 sd10 实际=48-50%），导致探针自设计打偏。
    有该关数据时用真实关系，无数据时 fallback 全局假设。
    """
    if not pool_records:
        return None
    best = None
    for r in pool_records:
        wr = r.get('wr', 0)
        if wr <= 0:
            continue
        dist = abs(wr - probe_wr)
        if best is None or dist < best[0]:
            best = (dist, r)
    if best is None:
        return None
    sd = best[1].get('sd')
    try:
        return int(sd) if sd is not None else None
    except (ValueError, TypeError):
        return None


def fill_remaining(specs, probes, phase12, verified_keys, lv, diff, pool_records=None):
    """槽位不足 5 或 None → 自设计（_estimate_sd/_estimate_of + knowledge ratios 推荐）。

    2026-08-06 planner 审查重写：probes[i] 与 specs[i] 按索引对齐
    （find_candidates 第一轮保证每 spec 1 槽，None=无候选）——
    旧实现先 extend 非 None 再补，导致 L154 (0,50.5) 的 None 占位
    被 (4,10) 的第二候选挤掉、50+ 段只剩 1 槽。"""
    kb = None
    try:
        kb = _get_kb()
    except Exception:
        kb = None

    def _make_design(spec, used_ratios, vi):
        """自设计一槽（_estimate_sd/_estimate_of + knowledge ratios，ratios 去重）。"""
        ratios = ratios_variants[vi % len(ratios_variants)]
        vi += 1
        if kb:
            try:
                from tools.param_knowledge import query_for_target
                recs = query_for_target(diff, spec['probe_wr'], kb, top_n=3)
                if recs:
                    for r in recs:
                        # 2026-08-06 修复：knowledge 可能返回空 ratios（L132 T5
                        # 曾拿到 ''+sc=1 导致 apply_probes 校验失败）——空值不采用；
                        # strip 尾空格（phase12 记录 '1,1,10,1,1 ' 类格式）
                        rv = str(r.get('ratios', '') or '').strip()
                        if rv and rv not in used_ratios:
                            ratios = rv
                            break
            except Exception:
                pass
        guard = 0
        while (not ratios or ratios in used_ratios) and guard < len(ratios_variants):
            ratios = ratios_variants[vi % len(ratios_variants)]
            vi += 1
            guard += 1
        # 2026-08-06 最终兜底：knowledge 返回的 ratios 可能有类型/格式差异
        # （L132 T5 曾拿到 ''+sc=1，修复后又与 T1 重复 '10,1,1,1,1'×2
        # 会被 Unity dedup 吃掉一槽）——强制非空且未用
        if not ratios or ratios in used_ratios:
            for rv in ratios_variants:
                if rv not in used_ratios:
                    ratios = rv
                    break
        used_ratios.add(str(ratios))
        # 2026-08-10：优先用该关实际 sd↔wr 关系（池子数据反推），无数据 fallback 全局假设
        sd = _infer_sd_from_pool(spec['probe_wr'], pool_records)
        if sd is None:
            sd = _estimate_sd(spec['probe_wr'])
        return {'sd': sd,
                'sc': len(str(ratios).split(',')),
                'ratios': ratios,
                'of': _estimate_of(spec['probe_wr']),
                '_probe_wr': spec['probe_wr']}, vi

    def _try_nearby_tune(spec, pool_records, used_ratios):
        """2026-08-17 邻近微调：缺口段无候选时，找已验证池里离缺口最近的配置，
        在其基础上微调 sd/of（保持 ratios——已证明该牌面有效），生成探针。

        目标比最近配置高 → 降 sd/of（更易）；目标低 → 升 sd/of（更难）。
        步进 = min(3, |目标差|/10)（每档不超 3 步，避免跳太远）。
        无已验证近邻 → 返回 None（交自设计）。
        """
        if not pool_records:
            return None
        np_wr = spec['probe_wr']
        # 找离缺口段最近的已验证配置（bot/summary/phase0）
        nearest = None
        for r in pool_records:
            if r.get('source') not in ('bot', 'summary', 'phase0'):
                continue
            if r.get('wr', 0) < 5:
                continue
            if nearest is None or abs(r['wr'] - np_wr) < abs(nearest['wr'] - np_wr):
                nearest = r
        if nearest is None:
            return None
        nr = nearest['wr']
        # 近邻已离目标 ≤5pp → 不该探（已满足），交自设计
        if abs(nr - np_wr) <= 5:
            return None
        sd = int(nearest.get('sd', 0) or 0)
        of = float(nearest.get('of', 0.5) or 0)
        ratios = str(nearest.get('ratios', '1,1,1,1,1') or '').strip()
        if not ratios:
            return None
        step = min(3, max(1, round(abs(np_wr - nr) / 10)))
        if np_wr > nr:  # 目标更高 → 降难度
            sd = max(0, sd - step)
            of = max(0.0, of - 0.1 * step)
        else:  # 目标更低 → 升难度
            sd = sd + step
            of = min(1.0, of + 0.1 * step)
        probe = {'sd': sd,
                 'sc': len(ratios.split(',')),
                 'ratios': ratios,
                 'of': round(of, 2),
                 '_probe_wr': np_wr, '_base_wr': nr}
        # 去重：已跑过或 ratios 已用 → 放弃微调交自设计
        if probe['sd'] == int(nearest.get('sd', 0) or 0) and abs(probe['of'] - float(nearest.get('of', 0.5) or 0)) < 0.01:
            return None  # 没实际变化
        pr = str(probe.get('ratios', '') or '').strip()
        if pr and pr in used_ratios:
            return None
        if pr:
            used_ratios.add(pr)
        return probe

    ratios_variants = ['1,1,1,1,1', '10,1,1,1,1', '1,10,1,1,1', '1,1,10,1,1', '1,1,1,10,1']
    out = []
    used_ratios = set()
    vi = 0
    # 第一轮：按 specs 索引对齐（probes[i] 有候选直接用，None → 自设计）
    for i, spec in enumerate(specs):
        if len(out) >= 5:
            break
        p = probes[i] if i < len(probes) else None
        if p is not None:
            # 2026-08-06 修复：候选也查 ratios 重复——phase12 里多个 sd 不同
            # 但 ratios 相同的配置（sd20/10,1,1,1,1 与 sd19/10,1,1,1,1）会同时
            # 入选，四元组不同但 Unity dedup 按 ratios 吃槽——重复则改自设计
            # ⚠️ ratios 必须 strip（phase12 记录可能带尾空格，'1,1,10,1,1 '
            # 与 '1,1,10,1,1' 不相等导致去重失效——L130 T4/T5 案例）
            pr = str(p.get('ratios', '') or '').strip()
            if pr and pr in used_ratios:
                design, vi = _make_design(spec, used_ratios, vi)
                out.append(design)
            else:
                out.append(p)
                if pr:
                    used_ratios.add(pr)
        else:
            # 2026-08-17 用户要求：设计探针应基于现有数据调整（邻近微调是主要途径之一）——
            # 缺口段无候选时，找已验证池里离缺口最近的配置，在其基础上微调
            # （目标更高→降 sd/of；目标更低→升 sd/of），而不是每次全新自设计。
            adjusted = _try_nearby_tune(spec, pool_records, used_ratios)
            if adjusted is not None:
                out.append(adjusted)
            else:
                design, vi = _make_design(spec, used_ratios, vi)
                out.append(design)
    # 第二轮起：同段多槽（不同 ratios 自设计）补到 5 槽
    idx = 0
    while len(out) < 5 and specs:
        spec = specs[idx % len(specs)]
        idx += 1
        design, vi = _make_design(spec, used_ratios, vi)
        out.append(design)
    return out


def finalize(probes, phase12, verified_keys, targets):
    """组装 5 槽 + 去重（已跑配置不重探）+ 槽位完整（W02）。
    2026-08-06: 不补通用模板阶梯——不足时按目标档位自设计（面向缺口）。"""
    # 防御：fill_remaining 后仍不足 5 → 按目标档位自设计（不是模板阶梯）
    while len(probes) < 5:
        t = targets[len(probes)] if len(probes) < len(targets) else 50
        probes.append({'sd': _estimate_sd(t), 'sc': 5, 'ratios': '1,1,1,1,1',
                       'of': _estimate_of(t)})
    # 去重：任一槽 config_key ∈ verified_keys → 换 ratios 变体（保留 sd/of）
    # 2026-08-06 修复：换变体时跳过"其他槽已用"的 ratios——旧逻辑多个槽
    # 撞 verified 时都换成 '10,1,1,1,1'（第一个变体）导致互相重复
    # （L130/L132/L153/L154 探针 T1/T2 等全变 10,1,1,1,1）
    keys = [pool._config_key({k: p[k] for k in ('sd', 'sc', 'ratios', 'of')}) for p in probes]
    used_ratios = {str(p.get('ratios', '') or '').strip() for p in probes}
    variants = ('10,1,1,1,1', '1,1,10,1,1', '1,1,1,1,10', '1,1,1,1,1', '1,10,1,1,1')
    for idx, k in enumerate(keys):
        if k in verified_keys:
            orig_ratios = str(probes[idx].get('ratios', '') or '').strip()
            used_ratios.discard(orig_ratios)
            swapped = False
            for r in variants:
                if r != orig_ratios and r not in used_ratios:
                    probes[idx]['ratios'] = r
                    probes[idx]['sc'] = len(r.split(','))
                    used_ratios.add(r)
                    swapped = True
                    break
            # 2026-08-06 修复：variants 全被占用时保持原 ratios，
            # 但必须加回 used_ratios——否则后续槽把已占用的 ratios
            # 当可用（L130 T4 discard 后 T5 换到 T4 的 1,1,10,1,1）
            if not swapped:
                used_ratios.add(orig_ratios)
    out = {}
    for i, p in enumerate(probes[:5]):
        # 2026-08-06 planner 审查：保留 _probe_wr 为 probe_wr（槽位目标胜率回显）
        clean = {k: v for k, v in p.items() if not k.startswith('_')}
        if '_probe_wr' in p:
            clean['probe_wr'] = p['_probe_wr']
        out[f'T{i + 1}'] = clean
    return out


def design(lv, force_unreachable=False):
    """主流程（2026-08-06 重写：缺口驱动，gap 优先，目标胜率个数从少到多）。

    ① 当前最优档位 → ② 缺口分析 → ③ 定目标胜率 → ④ 全池子找（含 phase1/2）
    → ⑤ 自设计 → ⑥ finalize（W02 合规 + 去重）
    2026-08-10 P1：force_unreachable=True 时跳过可达性阻断（返回 None 的场景）。
    """
    targets = et.get_target(lv)
    if not targets:
        _print(f'L{lv}: no targets')
        return None
    diff = targets['diff']
    targets = targets['tiers']

    recs = pool.get_preferred_records(str(lv))
    uniq = pool.dedup_records(recs)
    # 2026-08-06：verified 过滤 = 来源过滤（bot/summary/phase0 可靠，不限局数——
    # 贝叶斯提前停的数据也有可靠性）+ 单独排除测试残留级（<10 局，
    # L102 wr=100.0 只有 2 局 bot 手动验证残留）。与 pool.filter_verified 同语义。
    # 200 局限定只用于 phase1/2（它们必须验证后才能用），不是给可靠数据的。
    verified = [r for r in uniq
                if r.get('source') in ('bot', 'summary', 'phase0')
                and r.get('wr', 0) >= 5
                and r.get('totalGames', 0) >= 10]
    phase12 = [r for r in uniq if r.get('source') in ('phase1', 'phase2') and r.get('wr', 0) >= 5]
    verified_keys = {pool._config_key(r) for r in verified}

    # 2026-08-10 可达性预检：verified 天花板 vs 目标——目标远超天花板（>15pp）直接标记建议改关卡
    # （L85/L119 教训：目标 90/85 但 verified 最高 72.5/61.8，6 轮探针全白跑）
    # 仅在 verified 数据足够（>=5 条）时判断——数据太少说明采样不足而非关卡不可达
    # 2026-08-10 P1 修复：默认阻断（返回 None 标记 unreachable），--force 参数可绕过
    unreachable_info = None
    if len(verified) >= 5:
        ceiling = max(r['wr'] for r in verified)
        unreachable = [i + 1 for i, tg in enumerate(targets) if tg - ceiling > 15]
        if unreachable:
            _print(f'L{lv}: ⚠ 可达性预检——verified 天花板 {ceiling:.1f}%，'
                   f'目标档位 {unreachable} 距天花板 >15pp，探针大概率无效，建议改关卡')
            unreachable_info = {'ceiling': ceiling, 'unreachable_tiers': unreachable}
            if not force_unreachable:
                return None

    # ① 当前最优档位（基线池 = bot400，不足降级全部 verified；修 G5 传 diff）
    bot400 = [r for r in verified if r.get('source') == 'bot' and r.get('totalGames', 0) >= 400]
    baseline = bot400 if len(bot400) >= 3 else verified
    base_results = pool.find_best_monotonic(baseline, targets, difficulty=diff)
    if base_results and base_results[0]:
        base_wrs = [r['wr'] for r in base_results[0][2]]
        _print(f'L{lv} [{diff}] ① 当前最优: {[round(w, 1) for w in base_wrs]}')
    else:
        base_wrs = None
        _print(f'L{lv} [{diff}] ① 当前最优: 无合格组合（数据不足）')

    # ② 缺口分析
    if base_wrs:
        gaps, hard_specs = analyze_gaps(base_wrs, targets, diff)
        _print(f'  ② 缺口: {[(g["pair"], g["severity"], round(g["shortfall"], 1)) for g in gaps if g["severity"] != "ok"]}'
               + (f' 硬违规: {hard_specs}' if hard_specs else ''))
        # ③ 定目标胜率（反推法：需求推导 + 池子覆盖检查）
        specs = plan_specs(gaps, hard_specs, targets, base_wrs, diff,
                           pool_records=uniq)
    else:
        # no_combo：也走反推法（2026-08-06 planner 审查：跳过反推导致
        # L128/L130/L154 探针段与真实需求脱节——L154 完全没探 50+ 段）
        rules = _load_rules().get(diff, {})
        needs, covered = _derive_needs(targets, diff, rules, uniq)
        specs = []
        for i, need in enumerate(needs):
            if not covered[i]:
                specs.append({'tier': i, 'probe_wr': need, 'direction': 'raise' if need >= targets[i] else 'lower',
                              'need': need})
        if not specs:
            # 全部覆盖但无组合（数据矛盾）→ 目标带覆盖
            specs = [{'tier': i, 'probe_wr': targets[i], 'direction': 'verify', 'need': None}
                     for i in range(5)]
        else:
            # 梯度扩展补满 5 槽（2026-08-06 planner 审查：no_combo 之前
            # 不扩展——L154 只有 2 个 spec，fill_remaining 把 T5@10 填了 4 槽、
            # 50+ 段只剩 1 槽，违背用户"探出 50+ 就解决"的核心诉求）
            specs = _expand_gradients(specs, targets)
        _print(f'  ② 无组合 → 反推需求 {[round(n,1) for n in needs]}，未覆盖 {[i for i,c in enumerate(covered) if not c]}')

    _print(f'  ③ 探针目标: {[(s["tier"], s["direction"], s["probe_wr"]) for s in specs]}')

    # ④ 全池子找（含 phase1/2 作探针）
    probes = find_candidates(specs, phase12, verified_keys, verified_pool=verified)
    _print(f'  ④ 池子候选: {sum(1 for p in probes if p is not None)}/5 槽')

    # ⑤ 自设计补齐（2026-08-10：传 uniq 供关卡自适应 sd 估计）
    probes = fill_remaining(specs, probes, phase12, verified_keys, lv, diff, pool_records=uniq)
    _print(f'  ⑤ 组装: {len(probes)} 槽')

    # ⑥ finalize（W02 合规 + 去重；槽位按缺口优先级排布——探针是探索点，
    #     Unity 按索引独立跑 400 局，槽位顺序不影响数据正确性）
    out = finalize(probes, phase12, verified_keys, targets)
    _print(f'  ⑥ 最终: {[(k, v["sd"], v["ratios"]) for k, v in out.items()]}')
    return out


def _design_gap_focused(bot_min, bot_max):
    """缺口感知探针：5 槽全打池子未覆盖的低 WR 段。"""
    ratios_pool = [
        '10,1,1,1,1',   # 前段重
        '1,1,1,1,10',   # 后段重
        '10,1,1,1,10',  # 两头重
        '1,1,10,1,1',   # 单点爆
        '1,1,1,1,1',    # 均匀
    ]
    sds = [30, 35, 40, 45, 50]
    out = {}
    for i in range(5):
        out[f'T{i+1}'] = {
            'sd': max(0, min(50, sds[i])),
            'sc': 5,
            'ratios': ratios_pool[i % len(ratios_pool)],
            'of': 0.5 if i < 3 else 0.7,
        }
    return out


def _design_from_knowledge(targets, bot_min, bot_max, lv=None):
    """从经验知识库查表设计探针：根据目标 WR 反推推荐参数范围。

    对每个目标档位，查 param_knowledge 经验表，找到最合适的 ratios+sd 组合。
    """
    try:
        from tools.param_knowledge import _load_all_data, build_knowledge_base, query_for_target
        _all_data = _load_all_data()
        _kb = build_knowledge_base(_all_data)
        # 确定难度：优先从关卡号查，其次从 targets 范围推算
        diff = 'normal'
        if lv:
            try:
                from tools.data.adapters import excel_target as et
                t = et.get_target(lv)
                if t:
                    diff = t['diff']
            except:
                pass
        if diff == 'normal':
            if targets[0] <= 70:
                diff = 'hard'
            if targets[0] <= 50:
                diff = 'superhard'
    except Exception as ex:
        _print(f'  knowledge 加载失败: {ex}，回退通用模板')
        return _design_gap_focused(bot_min, bot_max)

    # 确定难度
    try:
        t = et.get_target(targets[0] if isinstance(targets[0], int) else 0)
        if t:
            diff = t['diff']
    except:
        pass

    # 找出缺口档位（池子覆盖不到的目标 WR）
    needed = []
    for target in targets:
        # 查经验表推荐
        recs = query_for_target(diff, target, _kb, top_n=3)
        if recs:
            needed.append((target, recs))

    _print(f'  knowledge: 查 {len(needed)} 个目标, 难度={diff}')

    # 从推荐中选 5 个不同配置
    result = []
    used_keys = set()
    for target, recs_obj in needed:
        for r in recs_obj:
            # 解析 sd 范围中间值
            bin_str = r['sd_bin']
            parts = bin_str.split('-')
            sd_mid = (int(parts[0]) + int(parts[1])) // 2 if len(parts) == 2 else int(parts[0])
            key = (r['ratios'], sd_mid // 5)
            if key not in used_keys:
                result.append({
                    'sd': sd_mid,
                    'sc': len(str(r['ratios']).split(',')),  # 2026-08-05 修复: sc 必须=ratios 段数（knowledge 库 ratios 可能是 3/4 段）
                    'ratios': r['ratios'],
                    'of': _estimate_of(target),  # 2026-08-05: 高胜率目标大幅降 of（可到 0）
                })
                used_keys.add(key)
                if len(result) >= 10:
                    break
        if len(result) >= 10:
            break

    # 不足 5 槽用通用模板补齐
    if len(result) < 5:
        _print(f'  knowledge: 不足 5 槽 ({len(result)})，补齐')
        gap = _design_gap_focused(bot_min, bot_max)
        for i in range(5):
            t_key = f'T{i+1}'
            if t_key in gap and len(result) < 5:
                result.append(gap[t_key])

    # 输出前 5 个
    result = result[:5]
    # 2026-08-06: W01 已移除——不再按 sd 排序（槽位按缺口优先级排布）
    _print(f'  knowledge 探针: {[(r["sd"], r["ratios"]) for r in result]}')

    out = {}
    for i, r in enumerate(result):
        out[f'T{i+1}'] = r
    return out


def _design_probe(wr, bot_min, bot_max):
    in_range = bot_min <= wr <= bot_max
    if in_range:
        sd = 35 - int(wr * 0.4)
    else:
        sd = 5 if wr > bot_max else 40
    sd = max(0, min(45, sd))
    # 2026-08-05：需要高胜率配置时 of 也大幅降（甚至 0），不固定 0.5
    return {'sd': sd, 'sc': 5, 'ratios': '1,1,1,1,1', 'of': _estimate_of(wr)}


def _estimate_sd(wr_target):
    # 2026-08-05：高胜率大幅降 sd（可到 0），别微调
    if wr_target >= 90: return 0
    if wr_target >= 85: return 2
    if wr_target >= 80: return 5
    if wr_target >= 70: return 10
    if wr_target >= 60: return 15
    if wr_target >= 50: return 20
    if wr_target >= 40: return 30
    if wr_target >= 30: return 35
    return 40


def _estimate_of(wr_target):
    """2026-08-05：需要高胜率配置时 of 大幅降（甚至 0）。
    高 WR 目标 = 更简单的配置 = 更低的 of。"""
    if wr_target >= 90: return 0.0
    if wr_target >= 80: return 0.1
    if wr_target >= 70: return 0.25
    if wr_target >= 60: return 0.35
    if wr_target >= 50: return 0.45
    return 0.5


def _design_placeholder(gap_wr, bot_min, bot_max):
    sd = _estimate_sd(gap_wr)
    return {'sd': sd, 'sc': 5, 'ratios': '1,1,1,1,1', 'of': _estimate_of(gap_wr)}


def _make_config(probes, targets, bot_min, bot_max):
    result = []
    for p in probes:
        result.append({'sd': int(p['sd']), 'sc': int(p.get('sc', 5)),
                       'ratios': p['ratios'], 'of': float(p.get('of', 0.5))})
    while len(result) < 5:
        gap_wr = (bot_max - bot_min) * (1 - len(result) / 5) + bot_min
        result.append(_design_probe(gap_wr, bot_min, bot_max))
    # 2026-08-06: W01(sd单调/跨度) 已移除——不再按 sd 排序/扩展跨度，
    # 探针槽位按设计缺口优先级排布（sd 只是探索手段之一）。
    out = {}
    for i, r in enumerate(result[:5]):
        out[f'T{i+1}'] = r
    return out


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('spec')
    parser.add_argument('--write', action='store_true')
    parser.add_argument('--force', action='store_true',
                        help='2026-08-10 P1：跳过可达性预检阻断（目标远超 verified 天花板时仍设计探针）')
    args = parser.parse_args()

    levels = set()
    for part in args.spec.split(','):
        if '-' in part:
            a, b = part.split('-')
            levels.update(str(i) for i in range(int(a), int(b) + 1))
        else:
            levels.add(part)

    for lv in sorted(levels, key=int):
        probes = design(str(lv), force_unreachable=args.force)
        if probes is not None and len(probes) > 0 and args.write:
            cfg = json.load(open(PROBE_CFG)) if os.path.exists(PROBE_CFG) else {}
            cfg[str(lv)] = probes
            json.dump(cfg, open(PROBE_CFG, 'w'), indent=2, ensure_ascii=False)
            print(f'  -> written')


if __name__ == '__main__':
    main()