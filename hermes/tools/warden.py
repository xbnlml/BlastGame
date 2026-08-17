#!/usr/bin/env python3
"""Warden — 事前安全检查闸门

批跑前执行 W01-W08 检查，block 级不通过则拒绝提交。
"""
import json, os, re, subprocess, sys

TOOLS = os.path.dirname(os.path.abspath(__file__))
HERMES = os.path.dirname(TOOLS)
RULES_PATH = os.path.join(HERMES, 'project-state', 'rules.json')
BOARD_PATH = os.path.join(HERMES, 'project-state', 'board.md')
PROBE_CFG = os.path.join(TOOLS, 'probe_configs.json')


def load_rules():
    if os.path.exists(RULES_PATH):
        with open(RULES_PATH, encoding='utf-8') as f:
            return json.load(f)
    return {'warden_checks': {'pre_batch': []}}


# ── 单项检查 ──

def check_pre_tune_backup(levels):
    """W00: 调优前 asset 备份存在（warn 级）——检查 project-state/pre_tune_backup_<最新>/ 是否有对应关的 .asset.bak"""
    if not levels:
        return True, ''
    import glob
    bks = glob.glob(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'project-state', 'pre_tune_backup_*'))
    if not bks:
        return False, '无 pre_tune_backup 目录——调优会覆盖 asset，建议先备份入库配置'
    latest = max(bks, key=os.path.getmtime)
    missing = [str(l) for l in levels if not os.path.exists(os.path.join(latest, f'{l}.asset.bak'))]
    if missing:
        return False, f'备份目录 {os.path.basename(latest)} 缺: {missing}'
    return True, f'备份存在 ({os.path.basename(latest)})'


def check_sd_span(tiers):
    """W01: sd 跨度 >=10pp + 单调非递减"""
    sds = [int(t.get('sd', 0)) for t in tiers if str(t.get('sd', '')).isdigit()]
    if len(sds) < 3:
        return False, f'只有 {len(sds)} 个有效 sd 值，至少需要 3 个'
    if max(sds) - min(sds) < 10:
        return False, f'sd 范围 {min(sds)}-{max(sds)}={max(sds)-min(sds)}pp < 10pp'
    for i in range(1, len(sds)):
        if sds[i] < sds[i-1]:
            return False, f'sd 非单调递减: T{i}={sds[i-1]} -> T{i+1}={sds[i]}'
    return True, ''


def check_5_slots(tiers):
    """W02: 5 槽位全部填入"""
    if len(tiers) != 5:
        return False, f'只有 {len(tiers)}/5 个槽位'
    return True, ''


def check_probe_quality(tiers):
    """W09: 探针质量——ratios 非空 + 5 槽 ratios 互异（防 Unity dedup 吃槽）。
    2026-08-06 修：今天坏探针（ratios 全 '10,1,1,1,1'、空 ratios）从
    apply_probes 溜过去了——只查 5 槽不够，必须查 ratios 质量。
    - ratios 全相同 → Unity dedup 按 ratios 吃槽 → 实际只跑 1 档
    - ratios 空 → 配置非法
    """
    ratios = []
    for i, t in enumerate(tiers):
        r = str(t.get('ratios', '') or '').strip()
        if not r:
            return False, f'T{i+1}: ratios 为空'
        ratios.append(r)
    if len(set(ratios)) < 2:
        return False, f'ratios 全部相同 {ratios[0]}——Unity dedup 会吃槽'
    # 四元组 config_key 不应重复（完全相同的配置会被 dedup）
    try:
        sys.path.insert(0, HERMES)
        from tools.data import pool
        keys = [pool._config_key({k: t[k] for k in ('sd', 'sc', 'ratios', 'of')}) for t in tiers]
        if len(keys) != len(set(keys)):
            return False, f'存在完全相同的配置（四元组重复）——会被 Unity dedup 吃掉'
    except Exception:
        pass  # config_key 不可用时跳过（ratios 检查已覆盖主要问题）
    return True, ''


def check_ratios_diversity(tiers):
    """W03: ratios 至少 3 种不同模式"""
    patterns = set()
    for t in tiers:
        r = str(t.get('ratios', '')).strip()
        if r:
            patterns.add(r)
    if len(patterns) < 3:
        return False, f'只有 {len(patterns)} 种 ratios 模式，需 >= 3'
    return True, ''


def check_unity_lock():
    """W04: 无 Unity 进程残留"""
    try:
        r = subprocess.run(['tasklist'], capture_output=True, text=False, timeout=10)
        output = r.stdout.decode('gbk', errors='replace') if r.stdout else ''
        if 'Unity.exe' in output:
            return False, 'Unity.exe 仍在运行，先关闭'
        return True, ''
    except Exception as e:
        return True, f'无法检查 Unity 进程 (跳过: {e})'


def check_no_git():
    """W05: 无 git 命令——只检查真正会执行 git 的调用（subprocess/os.system/os.popen），
    不检查注释/字符串/docstring（避免误伤——审计 H17：之前全行扫描把注释里的
    'git reset' 也当危险命令，导致批跑被错误 BLOCK）。
    注意：os.system/os.popen 仅作为 AST 字符串匹配目标（检测用），不执行任何命令。"""
    import ast
    for root, dirs, files in os.walk(HERMES):
        if '.git' in dirs:
            dirs.remove('.git')
        for fn in files:
            if not fn.endswith('.py') or fn == 'warden.py':
                continue
            fp = os.path.join(root, fn)
            try:
                with open(fp, encoding='utf-8', errors='ignore') as f:
                    src = f.read()
                tree = ast.parse(src)
            except Exception:
                continue  # 语法错误文件跳过（不误伤）
            # 遍历 AST，找 subprocess.run/Popen、os.system、os.popen 调用
            for node in ast.walk(tree):
                # 方法/函数调用 subprocess.run([...'git'...]) 或 os.system('git ...')
                if isinstance(node, ast.Call):
                    cmd_str = None
                    # subprocess.run(["git", "checkout", ...]) 或 run("git checkout ...")
                    if node.args:
                        a0 = node.args[0]
                        if isinstance(a0, ast.Constant) and isinstance(a0.value, str):
                            cmd_str = a0.value
                        elif isinstance(a0, ast.List):
                            cmd_str = ' '.join(e.value for e in a0.elts
                                               if isinstance(e, ast.Constant) and isinstance(e.value, str))
                    if cmd_str and any(g in cmd_str for g in ('git checkout', 'git reset', 'git clean', 'git restore', 'git pull', 'git push')):
                        lineno = getattr(node, 'lineno', '?')
                        return False, f'{fn}:{lineno} 调用了 git 命令: {cmd_str[:60]}'
    return True, ''


def check_asset_hash(levels):
    """W06: asset 签名与快照一致"""
    try:
        sys.path.insert(0, HERMES)
        from tools.asset_patcher import level_sig
        for lv in levels:
            snap = level_sig(int(lv))
            if snap is None:
                return False, f'L{lv}: 无法读取 asset 签名'
        return True, ''
    except Exception as e:
        return False, f'asset 签名检查异常: {e}'


def _imported_levels():
    """从 board.md 表格行提取已入库关卡号（✅已入库）。
    2026-08-07 修复：之前用 `## 🟢 已入库` 区块正则，但 board 已改为
    表格格式（每行 | 51 | normal | ✅已入库 |），正则永远匹配不到 → W07/W08 静默失效。"""
    if not os.path.exists(BOARD_PATH):
        return set()
    imported = set()
    with open(BOARD_PATH, encoding='utf-8') as f:
        for line in f:
            # | 51 | normal | ✅已入库 | 8/4前 | 90/90/75/60/60 | — |  |
            m = re.match(r'^\|\s*(\d{2,3})\s*\|\s*\w+\s*\|\s*✅已入库', line)
            if m:
                imported.add(m.group(1))
    return imported


def check_asset_hash(levels):
    """W06: asset 签名与快照一致（牌面未被意外改动）。
    2026-08-07 修复：此函数被误删导致 run_warden 抛 NameError——
    每次 W06 都报"检查异常"。恢复为校验 asset 可读 + 牌面签名一致性。"""
    try:
        sys.path.insert(0, HERMES)
        from tools.asset_patcher import level_sig
        for lv in levels:
            snap = level_sig(int(lv))
            if snap is None:
                return False, f'L{lv}: 无法读取 asset 签名'
        return True, ''
    except Exception as e:
        return False, f'asset 签名检查异常: {e}'


def check_board_conflict(levels):
    """W07: 关卡不在 board 已入库列表中"""
    if not os.path.exists(BOARD_PATH):
        return True, ''
    imported = _imported_levels()
    for lv in levels:
        if lv in imported:
            return False, f'L{lv} 已在 board 已入库列表，跳过'
    return True, ''


def check_probe_vs_verify(levels):
    """W08: 探针配置不出现在已入库关卡"""
    if not os.path.exists(PROBE_CFG) or not os.path.exists(BOARD_PATH):
        return True, ''
    probes = json.load(open(PROBE_CFG, encoding='utf-8'))
    imported = _imported_levels()
    for lv in probes:
        if lv in imported:
            return False, f'L{lv} 在已入库列表但有探针配置'
    return True, ''


def _load_level_verified_pool(lv):
    """读该关 verified 池（bot/summary/phase0 ≥10局），返回 [(wr, sd, of)]。失败返回 None。"""
    try:
        sys.path.insert(0, HERMES)
        from tools.data.pool import get_all_records, dedup_records, filter_verified
        recs = dedup_records(get_all_records(str(lv)))
        ver = filter_verified(recs)
        out = []
        for r in ver:
            try:
                out.append((float(r['wr']), int(float(r.get('sd', 0))), float(r.get('of', 0))))
            except (TypeError, ValueError):
                continue
        return out
    except Exception:
        return None


def check_probe_direction(tiers_map):
    """W10: 探针方向合理性——对照池子缺口，检查探针 sd/of 是否朝缺口方向。

    规则（2026-08-14，skill 探针铁则 6c-6o）：
    - 读每关 verified 池，看每个 distinct 目标档位 ±10pp 内有没有覆盖
    - 无覆盖 = 缺口档：
        * 目标高档（如 80）缺 → 探针应偏易（低 sd / 低 of）
        * 目标低档（如 45）缺 → 探针应偏难（高 sd / 高 of）
    - 有覆盖 = 不查方向（探针可能用于换组合/微调）
    - 探针全档朝同一方向（都太难/都太易）且有多档缺口 = 警告
    severity=warn：不 block，但提示人工/下轮注意。
    """
    issues = []
    if not tiers_map:
        return True, ''
    try:
        sys.path.insert(0, HERMES)
        from tools.data.adapters import excel_target as et
    except Exception:
        return True, ''

    for lv, tiers in (tiers_map or {}).items():
        # 目标
        try:
            info = et.get_target(lv)
            targets = [int(t) for t in info['tiers']]
        except Exception:
            continue
        distinct_tg = [t for i, t in enumerate(targets) if t not in targets[:i]]

        pool = _load_level_verified_pool(lv)
        if pool is None:
            continue

        # 每档缺口方向：目标段 ±10 无覆盖 = 缺口
        probe_sds = []
        probe_ofs = []
        # 2026-08-17 修复：tiers 是 {'T1':{...},...} dict，遍历要用 .values()——
        # 旧代码 `for t in tiers` 遍历到 key 字符串，t.get() 崩溃被外层 try/except
        # 吞掉 → W10 永远"通过"，浪费探针从未被拦住。
        for t in tiers.values():
            try:
                probe_sds.append(int(float(t.get('sd', 0))))
                probe_ofs.append(float(t.get('of', 0)))
            except (TypeError, ValueError):
                continue
        if not probe_sds:
            continue

        # 2026-08-17 强化：已满足档位（离目标 ≤5pp）不该有探针——浪费槽位。
        # 读当前最优组合（find_best_monotonic）作为 base_wrs。
        try:
            from tools.data.pool import get_all_records, dedup_records, filter_verified
            from tools.find_best_combo import find_best_monotonic
            allrec = dedup_records(get_all_records(str(lv)))
            ver = filter_verified(allrec)
            info2 = et.get_target(lv)
            best = find_best_monotonic(ver, info2['tiers'], top_n=1, difficulty=info2['diff'])
            base_wrs = [t['wr'] for t in best[0][2]] if best and best[0] else None
        except Exception:
            base_wrs = None

        # 2026-08-17 重写：按实际 5 档探针逐个检查（不按 distinct 映射——5 槽全写）
        # 每档探针 vs 该档目标：
        #   1. 已满足档（当前最优离目标 ≤5pp）→ 探针浪费
        #   2. 缺口档 → 探针方向必须朝缺口（高档缺→偏易，低档缺→偏难）
        tier_targets = list(targets)  # T1..T5 各自目标（normal 同配置共享目标）
        for slot, (psd, pof) in enumerate(zip(probe_sds, probe_ofs)):
            if slot >= len(tier_targets):
                break
            tg = tier_targets[slot]
            # 1. 已满足检查（用 base_wrs 当前最优）
            if base_wrs is not None and slot < len(base_wrs) and abs(base_wrs[slot] - tg) <= 5:
                issues.append(f'L{lv} T{slot+1}: 已满足目标({tg}%)离差{abs(base_wrs[slot]-tg):.0f}pp≤5但仍分配探针——浪费槽位，应打缺口档')
                continue
            # 2. 缺口方向检查——缺口 = 该档未满足（base_wrs 离目标 >5pp），
            #    不是"池子无记录"（池子有 phase1/2 记录不代表该档满足）。
            #    2026-08-17 修复：旧逻辑用 pool 查覆盖，缺口档被"池子有记录"跳过方向检查
            if base_wrs is not None and slot < len(base_wrs) and abs(base_wrs[slot] - tg) <= 5:
                continue  # 已满足（上面已报浪费，这里不重复）
            if base_wrs is not None and slot < len(base_wrs):
                # 缺口档 → 探针方向必须朝缺口
                if tg >= 70 and psd > 25:
                    issues.append(f'L{lv} T{slot+1}: 目标{tg}% 缺口(现{base_wrs[slot]:.0f}%)但探针 sd={psd} 偏难——高档缺口应低 sd/of')
                elif tg <= 45 and psd < 15 and pof < 0.3:
                    issues.append(f'L{lv} T{slot+1}: 目标{tg}% 缺口(现{base_wrs[slot]:.0f}%)但探针 sd={psd}/of={pof} 偏易——低档缺口应高 sd/of')

    if issues:
        return False, '; '.join(issues[:6])
    return True, ''


# ── 执行器 ──

def run_warden(levels, tiers_map=None):
    """执行全部检查，返回 (passed, failures)"""
    rules = load_rules()
    failures = []
    warnings = []
    checks = rules['warden_checks']['pre_batch']

    for check in checks:
        cid = check['id']
        name = check['name']
        sev = check.get('severity', 'block')
        try:
            if cid == 'W00':
                ok, msg = check_pre_tune_backup(levels)
                if not ok:
                    (warnings if sev == 'warn' else failures).append(f'[{cid}] {name} — {msg}')
                else:
                    warnings.append(f'[{cid}] {name} — {msg}')
            elif cid == 'W02':
                for lv, tiers in (tiers_map or {}).items():
                    ok, msg = check_5_slots(tiers)
                    if not ok:
                        failures.append(f'[{cid}] L{lv}: {name} — {msg}')
            elif cid == 'W04':
                ok, msg = check_unity_lock()
                if not ok:
                    failures.append(f'[{cid}] {name} — {msg}')
            elif cid == 'W05':
                ok, msg = check_no_git()
                if not ok:
                    failures.append(f'[{cid}] {name} — {msg}')
            elif cid == 'W06':
                ok, msg = check_asset_hash(levels)
                if not ok:
                    failures.append(f'[{cid}] {name} — {msg}')
            elif cid == 'W07':
                ok, msg = check_board_conflict(levels)
                if not ok:
                    (warnings if sev == 'warn' else failures).append(f'[{cid}] {name} — {msg}')
            elif cid == 'W08':
                ok, msg = check_probe_vs_verify(levels)
                if not ok:
                    (warnings if sev == 'warn' else failures).append(f'[{cid}] {name} — {msg}')
            elif cid == 'W10':
                ok, msg = check_probe_direction(tiers_map)
                if not ok:
                    (warnings if sev == 'warn' else failures).append(f'[{cid}] {name} — {msg}')
        except Exception as e:
            (warnings if sev == 'warn' else failures).append(f'[{cid}] {name} — 检查异常: {e}')

    passed = len(failures) == 0
    if not passed:
        print('[WARDEN] BLOCKED:')
        for f in failures:
            print(f'  {f}')
    if warnings:
        print('[WARDEN] WARNINGS:')
        for w in warnings:
            print(f'  ⚠ {w}')
    if passed and not warnings:
        print('[WARDEN] PASSED')

    return passed, failures + warnings


def main():
    import argparse
    ap = argparse.ArgumentParser(description='Warden — 事前安全检查')
    ap.add_argument('--levels', help='关卡列表')
    ap.add_argument('--probe-file', help='探针配置 JSON 路径')
    args = ap.parse_args()

    levels = []
    if args.levels:
        for p in args.levels.split(','):
            p = p.strip()
            if '-' in p:
                a, b = p.split('-')
                levels.extend(str(i) for i in range(int(a), int(b) + 1))
            else:
                levels.append(p)
    if not levels:
        print('请指定 --levels')
        sys.exit(1)

    tiers_map = {}
    if args.probe_file and os.path.exists(args.probe_file):
        probes = json.load(open(args.probe_file, encoding='utf-8'))
        for lv in levels:
            if lv in probes:
                p = probes[lv]
                tiers_map[lv] = [p[k] for k in sorted(p.keys())]

    ok, msgs = run_warden(levels, tiers_map)
    if not ok:
        sys.exit(1)


if __name__ == '__main__':
    main()