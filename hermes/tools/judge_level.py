#!/usr/bin/env python3
"""评判关卡现有数据能否满足档位差要求。

标准: blastgame-judgment skill (judgment-rules.md)
  - ② 合格判定表按 WR 分档
  - ③ 硬性违规清单
  - ⑤ 结果三分级 + 6轮上限
"""
import os, sys, json

ROOT = os.environ.get('BLASTGAME_REPO', r'C:\Users\Administrator\Documents\BlastGame')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(sys.path[0]))

from tools.data.adapters import excel_target as et

# ── 加载判定规则 ──
_rules_cache = None

def _load_rules():
    global _rules_cache
    if _rules_cache is None:
        rules_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..',
                                  'project-state', 'rules.json')
        if os.path.exists(rules_path):
            with open(rules_path) as f:
                _rules_cache = json.load(f)
        else:
            _rules_cache = {}
    return _rules_cache.get('judge_rules', {})

ROUNDS_FILE = os.path.join(os.path.dirname(__file__), '..', 'project-state', '_rounds.json')
MAX_ROUNDS = 6


def _load_rounds():
    if os.path.isfile(ROUNDS_FILE):
        with open(ROUNDS_FILE) as f: return json.load(f)
    return {}


def _save_rounds(d):
    os.makedirs(os.path.dirname(ROUNDS_FILE), exist_ok=True)
    with open(ROUNDS_FILE, 'w') as f: json.dump(d, f, indent=2)


def get_round(lv): return _load_rounds().get(str(lv), 0)


def inc_round(lv):
    d = _load_rounds()
    d[str(lv)] = d.get(str(lv), 0) + 1
    _save_rounds(d)
    return d[str(lv)]


def reset_round(lv):
    d = _load_rounds(); d.pop(str(lv), None); _save_rounds(d)


def get_difficulty(lv):
    info = et.get_target(lv); return info['diff'] if info else 'unknown'


def load_stage_data(levels):
    stage = {}
    from tools.data import pool
    for lv in levels:
        recs = pool.get_all_records(lv)
        if recs: stage[lv] = recs
    return stage


def check_judgment(combo, diff, targets=None):
    """按 rules.json（judgment-rules）判定。返回 (result, reasons)。

    阈值从 rules.json 读取，缺失时用内置默认（保持向后兼容）。
    targets 可选：传入时启用目标偏差软约束（target_deviation）。
    """
    rules = _load_rules().get(diff, {})
    # 2026-08-05：tolerance_pp 在 judge_rules 顶层（所有难度生效），不是难度层
    _jr_all = _load_rules()
    tolerance_pp = float(_jr_all.get('tolerance_pp', 0))
    near_tolerance_pp = float(_jr_all.get('near_tolerance_pp', 0))
    # 新分档标准（2026-07-31）：按较高档 WR 分档 20/15/10/6
    gap_bands = rules.get('gap_bands', {'wr_ge_70': 20, 'wr_ge_50': 15, 'wr_ge_30': 10, 'wr_lt_30': 6})
    near_bands = rules.get('near_bands', {'wr_ge_70': 15, 'wr_ge_50': 10, 'wr_ge_30': 7, 'wr_lt_30': 4})
    anchor = rules.get('anchor', {})
    t3_min = anchor.get('t3_min', 60)
    t3_range = anchor.get('t3_range', [30, 60])
    t3_max = anchor.get('t3_max', 50)

    wrs = [combo[f'T{i}'] for i in range(1, 6)]
    gaps = [wrs[i] - wrs[i+1] for i in range(4)]
    reasons = []

    def _band(hi_wr):
        """按较高档 WR 返回 (合格线, 接近线)"""
        if hi_wr >= 70:
            return gap_bands['wr_ge_70'], near_bands['wr_ge_70']
        if hi_wr >= 50:
            return gap_bands['wr_ge_50'], near_bands['wr_ge_50']
        if hi_wr >= 30:
            return gap_bands['wr_ge_30'], near_bands['wr_ge_30']
        return gap_bands['wr_lt_30'], near_bands['wr_lt_30']

    # ③ 硬性违规（gap 红线由分档标准覆盖：<30% 段接近带下限 4，故这里只保留倒挂）
    for i in range(4):
        if diff == 'normal' and i in (0, 3): continue
        if gaps[i] < -1:
            reasons.append('硬性违规: 倒挂 T%d>T%d=%.1f%%' % (i+2, i+1, abs(gaps[i])))
    for i in range(5):
        if wrs[i] < 5:
            reasons.append(f'硬性违规: T{i+1}={wrs[i]:.1f}<5%')
    # <10% 档 > 1 个
    low_count = sum(1 for w in wrs if w < 10)
    if low_count > 1:
        reasons.append(f'硬性违规: <10%档{low_count}个 > 1')
    # gap > 40% (仅 Hard/SuperHard)
    if diff in ('hard', 'superhard'):
        for i in range(4):
            if gaps[i] > 40:
                reasons.append(f'硬性违规: T{i+1}-T{i+2} gap={gaps[i]:.1f}>40%')
    if diff == 'normal' and wrs[2] < t3_min:
        reasons.append(f'硬性违规: Normal T3={wrs[2]:.1f}<{t3_min}%')

    # ② 合格判定（2026-07-31 用户定）
    # 默认按较高档 WR 分档（20/15/10/6）；仅当目标档位差与分档标准冲突时，按目标档位差
    if diff == 'normal':
        # Normal 查 T1→T3、T3→T5
        pairs = [(0, 2), (2, 4)]
    else:
        pairs = [(i, i+1) for i in range(4)]
    for i, j in pairs:
        gap = wrs[i] - wrs[j]
        ok_lo, near_lo = _band(wrs[i])          # 分档标准
        if targets is not None:
            ok_target = targets[i] - targets[j]  # 目标档位差
            if ok_target != ok_lo:               # 冲突 → 目标优先
                ok_lo = ok_target
                near_lo = int(ok_target * 0.7)   # 接近下限 = 0.7×目标档位差
        if gap < near_lo - near_tolerance_pp:
            # 2026-08-05：接近带下限容差——gap 在接近线下方 near_tolerance_pp 内也算接近
            # （L152 案例：T3→T5 gap=9.99 < 10 差 0.01pp 被判不合格，用户裁定接近带加 1% 容差）
            reasons.append(f'T{i+1}→T{j+1} gap={gap:.1f}<{near_lo}pp')
        elif gap < ok_lo:
            # 2026-08-05：容差——gap 在合格线下 tolerance_pp 内也算合格
            if gap >= ok_lo - tolerance_pp:
                pass  # 合格（容差内）
            else:
                reasons.append(f'T{i+1}→T{j+1} gap={gap:.1f}<{ok_lo}pp (接近)')
    if diff == 'hard' and not (t3_range[0] <= wrs[2] <= t3_range[1]):
        reasons.append(f'T3={wrs[2]:.1f} not in [{t3_range[0]},{t3_range[1]}]')
    if diff == 'superhard' and wrs[2] > t3_max:
        reasons.append(f'T3={wrs[2]:.1f}>{t3_max}')

    # ── 目标偏差软约束（rules.json target_deviation）──
    # 2026-08-17 用户定稿分级：dev<=5 完全接受（合格）；5<dev<=10 接近（继续调优）；
    # dev>10 不合格（硬违规）。注意：dev=10 贴线算接近，不算合格（用户纠正 L158/L188 漏报贴线黄）。
    # 仅当调用方传入 targets 时启用（正常流程 judge_with_rounds/planner 均传）
    if targets is not None:
        td = _load_rules().get('target_deviation', {'max': 5, 'near': 10, 'severity': 'hard'})
        td_ok = float(td.get('max', 5))      # 完全接受线（<=5 合格）
        td_near = float(td.get('near', 10))  # 接近线（<=10 接近，>10 不合格）
        dev_tiers = []
        near_tiers = []
        for i in range(5):
            dev = abs(wrs[i] - targets[i])
            if dev > td_near:
                dev_tiers.append(f'T{i+1}={wrs[i]:.1f}% 离目标{targets[i]}%偏差{dev:.1f}pp>{td_near}pp')
            elif dev > td_ok:
                near_tiers.append(f'T{i+1}={wrs[i]:.1f}% 离目标{targets[i]}%偏差{dev:.1f}pp>{td_ok}pp')
        if dev_tiers:
            reasons.append('硬性违规: 目标偏差超标 — ' + '; '.join(dev_tiers))
        if near_tiers:
            reasons.append('(接近) 目标偏差: ' + '; '.join(near_tiers))

    # 三态归类（2026-07-31：不再有"偏离≤2pp直接合格"豁免——
    # 新分档标准下接近带 [near, ok) 就是"勉强合格"，gap 距临界点差一点 → 接近）
    hard_violations = [r for r in reasons if '硬性违规' in r or '倒挂' in r]
    near_only = [r for r in reasons if '(接近)' in r and '硬性违规' not in r]

    failed = [r for r in reasons if r not in near_only and r not in hard_violations]

    if hard_violations:
        return '不合格', reasons
    if failed:
        return '不合格', reasons
    if near_only:
        return '接近', reasons
    return '合格', reasons


def find_best_combo(data_records, diff, targets=None):
    from tools.data import pool as db
    # 2026-08-06：来源过滤（bot/summary/phase0）+ 排除测试残留（<10局，
    # L102 wr=100 2局手动验证残留曾混入判"合格"）。200局限定只用于
    # phase1/2（必须验证后才有资格入库），不是给可靠数据的。
    verified = [r for r in db.filter_verified(db.dedup_records(data_records))
                if r.get('totalGames', 0) >= 10]
    if not verified:
        return None, '不合格', ['无 verified 数据']
    # 2026-08-06：targets 由调用方传入（judge_with_rounds 从 Excel 读）；
    # 兜底用 diff 默认（superhard 之前拿错 [70,55,40,30,20] 已修）
    if targets is None:
        targets = {'normal': [85, 85, 65, 50, 50],
                   'hard': [70, 55, 40, 30, 20],
                   'superhard': [50, 40, 30, 20, 10]}.get(diff, [50, 40, 30, 20, 10])
    res = db.find_best_monotonic(verified, targets, top_n=1, difficulty=diff)
    if not res:
        return None, '不合格', ['无法拼出单调递减组合']
    q, gs, best = res[0]
    combo = {f'T{i+1}': best[i]['wr'] for i in range(5)}
    result, reasons = check_judgment(combo, diff, targets)
    return combo, result, reasons


def judge_with_rounds(lv):
    records = load_stage_data([str(lv)]).get(str(lv), [])
    if not records:
        return None, '无数据', ['stage-data空'], {'round': 0, 'max': MAX_ROUNDS}

    diff = get_difficulty(lv)
    # 2026-08-06：targets 从 Excel 读真实值（superhard 不再是 70/55/40/30/20）
    from tools.data.adapters import excel_target as et
    info = et.get_target(lv)
    tg = info['tiers'] if info else None
    combo, result, reasons = find_best_combo(records, diff, targets=tg)

    rnd = get_round(lv)
    if result == '合格':
        reset_round(lv)
        action = '入库'
    elif result == '接近':
        # 2026-08-17 用户定稿：接近 = 继续调优，不入库（L158 T4/T5 差 10pp 贴线被误判入库教训）
        action = '继续调优(接近)'
        # 接近不 reset 轮数，继续下一轮
    elif result == '不合格':
        if rnd >= MAX_ROUNDS - 1:
            rnd = inc_round(lv)  # 2026-08-08 修复：返回值必须赋给 rnd，否则返回旧轮数导致 MAX ROUNDS 检查失效
            action = '改关卡'
        else:
            rnd = inc_round(lv)
            action = f'下一轮({rnd}/{MAX_ROUNDS})'

    return combo, result, reasons, {'round': rnd, 'max': MAX_ROUNDS, 'action': action}


def scan_mode(levels):
    print("=" * 75)
    print(" Level Status Scan (judgment-rules.md)")
    print("=" * 75)
    for lv_s in levels:
        combo, result, reasons, ri = judge_with_rounds(int(lv_s))
        diff = get_difficulty(lv_s)
        w = '->'.join(f"{combo[f'T{i}']:.1f}%" for i in range(1, 6)) if combo else '-'
        print(f"L{lv_s:>3} {diff:<10} {result:<6} r{ri['round']}/{ri['max']} {ri['action']:<12} {w}")
        for r in reasons[:3]: print(f"    {r}")
    print('-' * 75)


def parse_levels(spec):
    levels = set()
    for part in spec.split(','):
        part = part.strip()
        if '-' in part:
            a, b = part.split('-')
            for lv in range(int(a), int(b) + 1): levels.add(str(lv))
        else:
            levels.add(part)
    return sorted(levels, key=int)


def main():
    if len(sys.argv) < 2:
        print("用法: python judge_level.py <levels>")
        print("       python judge_level.py --scan <range>")
        print("       python judge_level.py --rounds-reset <lv>")
        sys.exit(1)

    if sys.argv[1] == '--scan':
        lvls = parse_levels(sys.argv[2]) if len(sys.argv) > 2 else [str(i) for i in range(51, 201)]
        scan_mode(lvls)
        return
    if sys.argv[1] == '--rounds-reset':
        reset_round(int(sys.argv[2]))
        print(f"L{sys.argv[2]} 轮次已重置")
        return

    levels = parse_levels(sys.argv[1])
    print("=" * 70)
    print(" 多档位判定 (judgment-rules.md)")
    print("=" * 70)
    for lv_s in levels:
        combo, result, reasons, ri = judge_with_rounds(int(lv_s))
        diff = get_difficulty(lv_s)
        print(f"\n--- L{lv_s} ({diff}) r{ri['round']}/{ri['max']} ---")
        if combo:
            wrs_s = '->'.join(f"{combo[f'T{i}']:.1f}%" for i in range(1, 6))
            print(f"  >> {result}  T1->T5: {wrs_s}")
        else:
            print(f"  !! {result}")
        print(f"  操作: {ri['action']}")
        for r in reasons[:5]: print(f"    {r}")


if __name__ == '__main__':
    main()
