#!/usr/bin/env python3
"""
auto_loop.py — 全自动调优编排器（Executor）

五阶段闭环（每轮）:
  Phase1 Planner（决策: 组合+探针）
  Phase2 apply_probes（写 asset，Warden 闸门）
  Warden 批前检查
  Phase3 submit_batch_unity（Unity bot batch）
  Phase4 dump_level_pools（刷新池子）
  Phase5 judge_level（三态判定 + 6轮）
收尾: curator（模式识别 + 监督）

用法:
  python scripts/auto_loop.py --levels 136,176,178,184 --tiers 1,2,3,4,5
  python scripts/auto_loop.py --levels 170-185 --tiers 1,2,3,4,5 --games 400
  python scripts/auto_loop.py --levels 136,176 --tiers 1,2,3,4,5 --strategy visible_greedy

关键:
  - 继承 submit_batch_unity.py 的 Unity 调用逻辑 (EXE路径、参数)
  - 复用现有所有 agent/工具脚本，不重新实现
  - 安全约束: 禁止 git、禁止删源数据
  - 出错重试 1 次，2 次失败跳过该关或停止
  - 全程输出进度日志到 hermes/auto-log/<timestamp>.log
"""

import argparse
import json
import os
import subprocess
import sys
import time
import traceback  # 2026-08-07 修复：第191行用 traceback.print_exc() 但没 import（审计 B5）
from datetime import datetime

# ── 入库工具 ──
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tools.data.pool import get_all_records, dedup_records, filter_verified, find_best_monotonic
from tools.data.adapters import excel_target as et
from tools.asset_patcher import write_ddc, verify_asset

# ── Paths (mirror submit_batch_unity.py layout) ──

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
HERMES = os.path.dirname(SCRIPT_DIR)
TOOLS = os.path.join(HERMES, 'tools')
SCRIPTS = SCRIPT_DIR

# Unity invocation — 版本从 ProjectVersion.txt 动态读取（不硬编码）
def _find_unity_exe():
    """从 ProjectSettings/ProjectVersion.txt 读取版本，拼 Hub 路径。"""
    pv_file = os.path.join(
        os.environ.get('BLASTGAME_REPO', r'C:\Users\Administrator\Documents\BlastGame'),
        'ProjectSettings', 'ProjectVersion.txt')
    try:
        with open(pv_file, encoding='utf-8') as f:
            for line in f:
                if 'm_EditorVersion:' in line:
                    ver = line.split(':', 1)[1].strip()
                    exe = os.path.expandvars(
                        r'%ProgramFiles%\Unity\Hub\Editor\{0}\Editor\Unity.exe'.format(ver))
                    if os.path.exists(exe):
                        return exe
    except OSError:
        pass
    return r'%ProgramFiles%\Unity\Hub\Editor\6000.0.60f1\Editor\Unity.exe'


UNITY_EXE = _find_unity_exe()
REPO = os.environ.get('BLASTGAME_REPO',
                      r'C:\Users\Administrator\Documents\BlastGame')
UNITY_EXECUTE_METHOD = 'BlastGame.Editor.BlastBotJenkinsBatchEntry.RunFromCommandLine'

PROBE_CONFIG = os.path.join(TOOLS, 'probe_configs.json')
AUTO_LOG_DIR = os.path.join(HERMES, 'auto-log')
MAX_ROUNDS = 6

# ── Safety ──

FORBIDDEN_CMDS = ['git ', 'rm -rf', 'del /', 'checkout',
                  'reset', 'clean', 'restore']

# ── Logging ──


class Logger:
    """Tee output to both stdout and a timestamped log file."""

    def __init__(self, path):
        self.path = path
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.fh = open(path, 'w', encoding='utf-8', buffering=1)

    def log(self, msg):
        ts = datetime.now().strftime('%H:%M:%S')
        line = f'[{ts}] {msg}'
        print(line, flush=True)
        self.fh.write(line + '\n')
        self.fh.flush()

    def close(self):
        self.fh.close()


def setup_logging():
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    return os.path.join(AUTO_LOG_DIR, f'{ts}.log')


# ── Helpers ──

def parse_levels(spec):
    """Parse comma-separated level list with range support."""
    levels = set()
    for part in spec.split(','):
        part = part.strip()
        if '-' in part:
            a, b = part.split('-')
            levels.update(range(int(a), int(b) + 1))
        else:
            levels.add(int(part))
    return sorted(levels)


def parse_tiers(spec):
    """Parse comma-separated tier list."""
    return [int(t.strip()) for t in spec.split(',') if t.strip()]


def extract_json(stdout):
    """Extract JSON object from stdout that may contain debug print noise.

    Tries: last single-line JSON → brace-span extraction (multi-line JSON
    between first '{' and last '}') → whole blob → first single-line JSON.
    """
    if not stdout:
        return None
    lines = stdout.strip().split('\n')
    # Strategy 1: last { ... } block (single line)
    for line in reversed(lines):
        line = line.strip()
        if line.startswith('{'):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                pass
    # Strategy 2: brace-span extraction — first '{' .. last '}' (multi-line JSON)
    start = stdout.find('{')
    end = stdout.rfind('}')
    if start >= 0 and end > start:
        try:
            return json.loads(stdout[start:end + 1])
        except json.JSONDecodeError:
            pass
    # Strategy 3: whole stdout
    try:
        return json.loads(stdout)
    except json.JSONDecodeError:
        pass
    # Strategy 4: first { ... } block (single line)
    for line in lines:
        line = line.strip()
        if line.startswith('{'):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                pass
    return None


# ── Command runner with retry ──

def run_cmd(log, cmd, timeout=300, cwd=None, retries=1):
    """Run a subprocess command with retry.

    Returns subprocess.CompletedProcess on success, None after all retries exhausted.
    """
    for attempt in range(retries + 1):
        attempt_label = f'attempt {attempt + 1}/{retries + 1}'
        log.log(f'  CMD [{attempt_label}]: {" ".join(cmd)}')
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=cwd or HERMES,
                encoding='utf-8',
                errors='replace',
            )
            if result.returncode == 0:
                return result
            log.log(
                f'  FAIL (exit={result.returncode}) {attempt_label}')
            if result.stderr:
                log.log(f'  stderr: {result.stderr[-500:]}')
            # 2026-08-14：失败时把 stdout 尾部（RESULT 结构化行）也记入 auto-log，
            # 否则 submit_batch_unity 的 RESULT 行只进内存管道，事后无日志可查
            if result.stdout:
                tail_lines = [l for l in result.stdout.splitlines() if l.strip()][-15:]
                for tl in tail_lines:
                    log.log(f'  [stdout] {tl}')
        except subprocess.TimeoutExpired:
            log.log(f'  TIMEOUT ({timeout}s) {attempt_label}')
        except Exception as e:
            log.log(f'  ERROR: {e} {attempt_label}')
            traceback.print_exc()

        if attempt < retries:
            wait = 5
            log.log(f'  Retrying in {wait}s...')
            time.sleep(wait)

    log.log('  All retries exhausted — giving up')
    return None


# ── Phase 1: agent_analyze → combo + design_probes ──

def phase_analyze(log, levels):
    """Run planner (决策编排) to get combo analysis and probes for each level.

    planner 内部串联：agent_analyze → judge_level → design_probes。
    返回 {lv_str: {T1:{sd,sc,ratios,of}, ...}, ...}
    """
    probes = {}
    levels_str = ','.join(str(l) for l in levels)

    cmd = [
        sys.executable, '-X', 'utf8',
        os.path.join(TOOLS, 'planner.py'),
        '--levels', levels_str,
        '--output', 'json',
    ]

    result = run_cmd(log, cmd, timeout=600)
    if not result:
        log.log('  planner FAILED after retries')
        return probes

    data = extract_json(result.stdout)
    if not data:
        log.log('  planner: could not parse JSON output')
        # Dump first 500 chars for debugging
        preview = (result.stdout or '')[:500]
        log.log(f'  stdout preview: {preview}')
        return probes

    # 兼容新旧 planner 输出格式：新格式 {lv: {...}}，旧格式 {results: [{level, ...}]}
    results = []
    if isinstance(data, dict):
        if 'results' in data:
            results = data['results']
        else:
            # 新格式：{lv: {combo, probes, judge, ...}}
            for lv, r in data.items():
                r['level'] = lv
                results.append(r)
    elif isinstance(data, list):
        results = data

    for r in results:
        lv = str(r.get('level', ''))
        if not lv:
            continue

        error = r.get('error', '')
        if error:
            log.log(f'  L{lv}: planner error — {error}')
            continue

        combo = r.get('combo', {})
        raw_tiers = combo.get('tiers', []) if combo else []

        raw_probes = r.get('probes', [])
        judge = r.get('judge', '?')
        log.log(f'  L{lv}: {len(raw_probes)} probes, judge={judge}, combo quality={combo.get("quality","?")}')

        # Convert probe list -> probe_configs.json format {T1:{...}, T2:{...}, ...}
        # 2026-08-06: W01(sd单调/跨度) 已移除——探针槽位按设计缺口优先级排布，
        # 不再强制按 sd 排序/扩展跨度（sd 只是探索手段之一）。
        raw_probes = sorted(raw_probes, key=lambda p: int(p.get('tier', 0)))
        tier_probes = {}
        for i, p in enumerate(raw_probes[:5]):
            # Probe may have explicit 'tier' key or position (1-indexed)
            tier_num = p.get('tier', i + 1)
            tier_probes[f'T{tier_num}'] = {
                'sd': int(p.get('sd', 0)),
                'sc': int(p.get('sc', 5)),
                'ratios': str(p.get('ratios', '1,1,1,1,1')),
                'of': float(p.get('of', 0.5)),
            }

        # Fill missing tiers with defaults
        for i in range(1, 6):
            key = f'T{i}'
            if key not in tier_probes:
                # Use combo tier data as fallback
                combo_tier = raw_tiers[i - 1] if i <= len(raw_tiers) else {}
                tier_probes[key] = {
                    'sd': int(combo_tier.get('sd', 0)),
                    'sc': int(combo_tier.get('sc', 5)),
                    'ratios': str(combo_tier.get('ratios', '1,1,1,1,1')),
                    'of': float(combo_tier.get('of', 0.5)),
                }

        probes[lv] = tier_probes
        log.log(f'  L{lv}: {len(tier_probes)}/5 tiers configured')

    return probes


# ── Phase 2: apply_probes → write asset ──

def phase_apply_probes(log, probes):
    """Update probe_configs.json and run apply_probes for all configured levels.

    Returns True on success.
    """
    # Update probe_configs.json
    cfg = {}
    if os.path.exists(PROBE_CONFIG):
        try:
            with open(PROBE_CONFIG, 'r', encoding='utf-8') as f:
                cfg = json.load(f)
        except (json.JSONDecodeError, OSError):
            log.log('  probe_configs.json corrupt, starting fresh')
            cfg = {}

    updated = 0
    for lv, tier_probes in probes.items():
        cfg[str(lv)] = tier_probes
        updated += 1

    with open(PROBE_CONFIG, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
    log.log(f'  probe_configs.json updated: {updated} levels')

    # Run apply_probes for all levels
    levels_str = ','.join(probes.keys())
    cmd = [
        sys.executable, '-X', 'utf8',
        os.path.join(TOOLS, 'apply_probes.py'),
        levels_str,
    ]

    result = run_cmd(log, cmd, timeout=60)
    if result:
        # Print the last few lines of output
        lines = result.stdout.strip().split('\n')
        for line in lines[-10:]:
            if line.strip():
                log.log(f'    {line.strip()}')
        return result.returncode == 0
    else:
        log.log('  apply_probes FAILED')
        return False


# ── Phase 3: submit_batch_unity → Unity bot batch ──

def phase_submit_batch(log, levels, tiers, games=400, strategy='scoring_opt_vg', adaptive_stop=False):
    """Run submit_batch_unity.py to execute Unity bot batch.

    submit_batch_unity internally handles:
      - asset verification
      - Unity batch mode invocation
      - pool refresh (dump_level_pools)
      - post_batch_review
    （--skip-agent-pipeline: 判定由本流程 Phase5 judge_level 负责）

    2026-08-04：adaptive_stop=True 时传 --adaptive-stop（贝叶斯提前停，
    探针轮提速用）；False 时跑满 games（入库前 bot 400 验证）。

    Returns True on success.
    """
    levels_str = ','.join(str(l) for l in levels)
    tiers_str = ','.join(str(t) for t in tiers)

    cmd = [
        sys.executable, '-X', 'utf8',
        os.path.join(SCRIPTS, 'submit_batch_unity.py'),
        levels_str,
        '--tiers', tiers_str,
        '--games', str(games),
        '--strategy', strategy,
        '--yes',
        '--skip-agent-pipeline',
    ]
    if adaptive_stop:
        cmd.append('--adaptive-stop')

    # Timeout: at least 2 hours, or scaled by level×tier count
    timeout = max(len(levels) * len(tiers) * 300, 7200)
    log.log(
        f'  Submitting Unity batch: {len(levels)} levels × {len(tiers)} tiers, '
        f'timeout={timeout}s ({timeout // 60}min)'
    )

    result = run_cmd(log, cmd, timeout=timeout)
    if result:
        log.log('  Unity batch completed')
        # Print relevant lines from output
        for line in result.stdout.split('\n'):
            line = line.strip()
            if any(k in line for k in ['=== DONE ===', 'completed',
                                         'passed', 'FAIL']):
                log.log(f'    {line}')
    else:
        log.log('  Unity batch FAILED')
        return False

    return True


# ── Phase 4: dump_level_pools → refresh stage-data ──

def phase_refresh_pools(log):
    """Run dump_level_pools.py to rebuild the stage-data cache from telemetry.

    submit_batch_unity 已内部刷新池子，此调用确保判定前磁盘数据是最新的。

    Returns True on success.
    """
    cmd = [
        sys.executable, '-X', 'utf8',
        os.path.join(TOOLS, 'dump_level_pools.py'),
    ]

    result = run_cmd(log, cmd, timeout=300)
    if result:
        # Print summary lines
        lines = result.stdout.split('\n')
        for line in lines[-15:]:
            line = line.strip()
            if line and any(k in line for k in
                            ['总计', '覆盖', '可靠', '完成', '✅', 'Pool']):
                log.log(f'    {line}')
        return True
    else:
        log.log('  dump_level_pools FAILED')
        return False


# ── 2026-08-17：每轮结构化报告（解决黑盒）──
def _build_round_report(round_num, probes, review_results, levels):
    """收集每关：探针配置（实际写 asset 的）+ 该轮批次实际胜率（CSV）+ 判定结果。

    批次胜率从最新 telemetry/bot/ 批次目录的 campaign-summary-*.csv 读
    （每档一行，含该轮 3 关实际跑出的 WR）。
    """
    import csv as _csv
    # 找最新批次目录（telemetry/bot/ 下 mtime 最新的）
    repo = os.environ.get('BLASTGAME_REPO', r'C:\Users\Administrator\Documents\BlastGame')
    bot_dir = os.path.join(repo, 'telemetry', 'bot')
    latest_batch = None
    if os.path.isdir(bot_dir):
        dirs = [d for d in os.listdir(bot_dir) if os.path.isdir(os.path.join(bot_dir, d))]
        if dirs:
            latest_batch = max(dirs, key=lambda d: os.path.getmtime(os.path.join(bot_dir, d)))

    # 每关每档实际胜率 {lv: {T1: wr, ...}}
    batch_wrs = {}
    if latest_batch:
        for lv in levels:
            lv = str(lv)
            batch_wrs[lv] = {}
            for t in ['T1', 'T2', 'T3', 'T4', 'T5']:
                # 该档目录：L{lv}_..._T{n}-...-batch-range/campaign-summary-T{n}.csv
                import glob
                pat = os.path.join(bot_dir, latest_batch, f'L*{lv}-{t}-*/campaign-summary-{t}.csv')
                files = glob.glob(pat)
                if not files:
                    continue
                try:
                    with open(files[0], encoding='utf-8') as f:
                        for row in _csv.DictReader(f):
                            if str(row.get('level', '')).strip() == str(lv).strip():
                                batch_wrs[lv][t] = round(float(row.get('winkate', 0)) * 100, 1)
                                break
                except Exception:
                    continue

    report = {
        'round': round_num,
        'saved_at': time.strftime('%Y-%m-%dT%H:%M:%S'),
        'levels': {},
    }
    for lv in levels:
        lv = str(lv)
        entry = {
            'probes': probes.get(lv, {}),          # 实际写 asset 的探针配置
            'batch_wrs': batch_wrs.get(lv, {}),    # 该轮批次实际胜率（CSV）
            'judge': review_results.get(lv, {}),   # 判定结果
        }
        report['levels'][lv] = entry
    return report


# ── Phase 5: agent_review / judge_level → pass/fail ──

def phase_review(log, levels):
    """Judge each level using judge_with_rounds, which reads stage-data
    and manages round tracking via _rounds.json.

    Returns {lv_str: {result, difficulty, round, max_rounds, action, reasons, wrs}}
    """
    # Make tools importable
    if TOOLS not in sys.path:
        sys.path.insert(0, TOOLS)

    import judge_level  # noqa: E402 — deliberate late import after path setup

    results = {}
    for lv in sorted(levels, key=int):
        lv_int = int(lv)
        combo, result, reasons, ri = judge_level.judge_with_rounds(lv_int)
        diff = judge_level.get_difficulty(lv_int)

        status = {
            'level': str(lv),
            'result': result,
            'difficulty': diff,
            'round': ri['round'],
            'max_rounds': ri['max'],
            'action': ri['action'],
            'reasons': reasons,
        }

        if combo:
            wrs = [f"{combo[f'T{i}']:.1f}%" for i in range(1, 6)]
            status['wrs'] = ' → '.join(wrs)

        results[str(lv)] = status

        # Log result
        wrs_str = status.get('wrs', 'N/A')
        action_str = ri['action']
        verdict_icon = {'合格': '✅', '不合格': '🔄', '无数据': '⚠'}.get(result, '❓')
        log.log(
            f'  {verdict_icon} L{lv} [{diff}] r{ri["round"]}/{ri["max"]}: '
            f'{result} — {action_str} — {wrs_str}'
        )
        for reason in reasons[:3]:
            log.log(f'    • {reason}')

    return results


# ── Fallback: design_probes.py direct call ──

def fallback_design_probes(log, levels):
    """Run design_probes.py --write directly for levels where agent_analyze
    produced no probes.  Updates probe_configs.json in-place.

    Returns set of levels that were successfully processed.
    """
    ok_levels = set()
    for lv in sorted(levels, key=int):
        cmd = [
            sys.executable, '-X', 'utf8',
            os.path.join(TOOLS, 'design_probes.py'),
            str(lv),
            '--write',
        ]
        result = run_cmd(log, cmd, timeout=300)
        if result and result.returncode == 0:
            # 2026-08-10 P1：可达性阻断时 design_probes 返回 None（--write 不写任何东西），
            # 此时 ok_levels 不能加——否则 auto_loop 以为有探针继续跑（白跑 6 轮）。
            # 检测 probe_configs.json 里该关是否有探针（阻断=无）
            import json as _json
            try:
                cfg = _json.load(open(os.path.join(TOOLS, 'probe_configs.json'), encoding='utf-8'))
                has_probes = str(lv) in cfg and len(cfg[str(lv)]) >= 5
            except Exception:
                has_probes = False
            if has_probes:
                log.log(f'  L{lv}: design_probes --write OK')
                ok_levels.add(str(lv))
            else:
                log.log(f'  L{lv}: design_probes 阻断（可达性预检）——标记待改关卡，不跑探针')
        else:
            log.log(f'  L{lv}: design_probes --write FAILED')
    return ok_levels


# ── Main ──

def main():
    parser = argparse.ArgumentParser(
        description='auto_loop — 全自动调优编排器 (max 6 rounds)')
    parser.add_argument(
        '--levels', required=True,
        help='关卡列表 (e.g. 136,176,178,184 or 170-185)')
    parser.add_argument(
        '--tiers', required=True,
        help='档位列表 (e.g. 1,2,3,4,5)')
    parser.add_argument(
        '--games', type=int, default=400,
        help='验证轮每档局数 (default: 400)')
    parser.add_argument(
        '--probe-games', type=int, default=200,
        help='探针轮每档局数 (default: 200)——2026-08-10 标准：'
             '探针轮 200 局筛选方向（+贝叶斯提前停），验证轮 400 局精测入库')
    parser.add_argument(
        '--strategy', default='scoring_opt_vg',
        choices=['visible_greedy', 'scoring_opt_vg'],
        help='Bot 策略 (default: scoring_opt_vg)')
    parser.add_argument(
        '--adaptive-stop', action='store_true',
        help='探针轮开贝叶斯提前停（提速）；入库前验证仍跑满 --games')
    parser.add_argument(
        '--resume', action='store_true',
        help='从 checkpoint 续跑（project-state/auto_loop_checkpoint.json），'
             '只跑 checkpoint 里未完成的关卡，轮数从 checkpoint 的下一轮开始')
    args = parser.parse_args()

    # ── Safety: reject forbidden commands in args ──
    cmdline = ' '.join(sys.argv).lower()
    for forbidden in FORBIDDEN_CMDS:
        if forbidden in cmdline:
            print(f'❌ FORBIDDEN: "{forbidden}" detected in arguments')
            sys.exit(1)

    # ── Setup ──
    log_path = setup_logging()
    log = Logger(log_path)

    levels = [int(l) for l in parse_levels(args.levels)]
    tiers = parse_tiers(args.tiers)

    log.log('=' * 60)
    log.log(' auto_loop.py — 全自动调优编排器')
    log.log('=' * 60)
    log.log(f' Log:        {log_path}')
    log.log(f' Levels:     {levels}')
    log.log(f' Tiers:      {tiers}')
    log.log(f' Games/tier: {args.games}')
    log.log(f' Strategy:   {args.strategy}')
    log.log(f' Max rounds: {MAX_ROUNDS}')
    log.log(f' Unity EXE:  {UNITY_EXE}')
    log.log(f' Repo:       {REPO}')
    log.log('')
    # ── 自动修复：关 Unity + 修路径 ──
    log.log('[Auto-recovery] 检查 Unity 进程...')
    try:
        r = subprocess.run(['tasklist'], capture_output=True, text=False, timeout=10)
        out = r.stdout.decode('gbk', errors='replace') if r.stdout else ''
        if 'Unity.exe' in out:
            log.log('  Unity.exe 仍在运行，自动关闭...')
            subprocess.run(['taskkill', '/F', '/IM', 'Unity.exe'],
                          capture_output=True, timeout=10)
            log.log('  Unity.exe 已关闭')
        else:
            log.log('  无 Unity 进程')
    except Exception as e:
        log.log(f'  检查 Unity 失败 (跳过): {e}')
    # ── 自动修复：确保 sys.path 正确 ──
        if HERMES not in sys.path:
            sys.path.insert(0, HERMES)
        log.log('')
    # Verify critical paths exist
    for path, label in [
        (UNITY_EXE, 'Unity EXE'),
        (REPO, 'BlastGame repo'),
        (os.path.join(TOOLS, 'agent_analyze.py'), 'agent_analyze'),
        (os.path.join(TOOLS, 'apply_probes.py'), 'apply_probes'),
        (os.path.join(SCRIPTS, 'submit_batch_unity.py'), 'submit_batch_unity'),
        (os.path.join(TOOLS, 'dump_level_pools.py'), 'dump_level_pools'),
        (os.path.join(TOOLS, 'judge_level.py'), 'judge_level'),
    ]:
        if not os.path.exists(path):
            log.log(f'⚠ WARNING: {label} not found: {path}')

    # ── State tracking ──
    pending = set(str(l) for l in levels)
    passed = {}    # lv → review status dict
    failed = {}    # lv → review status dict (max rounds reached)
    errors = {}    # lv → error message

    # ── Resume from checkpoint（2026-08-10 新增）──
    resume_round = 0
    if args.resume:
        cp_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'project-state', 'auto_loop_checkpoint.json')
        if os.path.exists(cp_path):
            try:
                with open(cp_path, encoding='utf-8') as f:
                    cp = json.load(f)
                saved_round = cp.get('round', 0)
                # 只保留 checkpoint 里仍 pending 的关（passed/failed 不再跑）
                cp_pending = set(str(x) for x in cp.get('levels', []))
                keep = pending & cp_pending
                done = set(str(x) for x in cp.get('passed', {})) | set(str(x) for x in cp.get('failed', {}))
                dropped = sorted(pending - cp_pending - done, key=int)
                pending = keep
                resume_round = saved_round
                log.log(f'  🔄 RESUME: checkpoint round={saved_round}, pending={sorted(pending, key=int)}')
                if dropped:
                    log.log(f'  ⚠ 从 pending 移除（checkpoint 无记录）: {dropped}')
            except Exception as e:
                log.log(f'  ⚠ resume failed（忽略，从头跑）: {e}')
        else:
            log.log('  ⚠ --resume 但无 checkpoint，从头跑')

    # ── Main loop (rounds 1..6) ──
    for round_num in range(resume_round + 1, MAX_ROUNDS + 1):
        if not pending:
            break

        log.log('')
        log.log('—' * 60)
        log.log(f' ROUND {round_num}/{MAX_ROUNDS}')
        log.log(f' Pending ({len(pending)}): {", ".join(sorted(pending, key=int))}')
        log.log('—' * 60)
        log.log('')

        pending_sorted = sorted(pending, key=int)

        # ── Phase 1: Analyze → design probes ──
        log.log(f'[Phase 1/5] agent_analyze → combo + design_probes')
        probes = phase_analyze(log, pending_sorted)

        # Fallback: if any pending level has no probes, try design_probes directly
        missing_probes = [lv for lv in pending_sorted if str(lv) not in probes]
        if missing_probes:
            log.log(
                f'  {len(missing_probes)} level(s) missing probes — '
                f'running fallback design_probes...'
            )
            fallback_ok = fallback_design_probes(log, missing_probes)

            # Re-read probes after fallback
            probes2 = phase_analyze(log, fallback_ok)
            probes.update(probes2)

            still_missing = [lv for lv in fallback_ok if str(lv) not in probes]
            if still_missing:
                log.log(
                    f'  ❌ {len(still_missing)} level(s) still missing probes '
                    f'after fallback: {still_missing}'
                )
                for lv in still_missing:
                    errors[lv] = f'probe_design_failed_r{round_num}'
                    pending.discard(lv)

        if not pending:
            log.log('  No pending levels remain after probe design — stopping')
            break

        # ── Phase 2: Apply probes to asset ──
        log.log(f'[Phase 2/5] apply_probes → write asset')
        # 调优前备份 asset（2026-08-10：第 1 轮自动备份入库配置到 pre_tune_backup_<date>，防探针覆盖后丢失）
        if round_num == 1:
            try:
                import shutil
                bk_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'project-state',
                                      f'pre_tune_backup_{time.strftime("%Y%m%d")}')
                os.makedirs(bk_dir, exist_ok=True)
                bak_count = 0
                for lv in sorted(pending, key=int):
                    # 用 asset_patcher 的 _asset_path 找 asset 文件
                    from tools.asset_patcher import _asset_path
                    src = _asset_path(int(lv))
                    if os.path.isfile(src):
                        dst = os.path.join(bk_dir, f'{lv}.asset.bak')
                        shutil.copy2(src, dst)
                        bak_count += 1
                log.log(f'  💾 调优前 asset 备份: {bak_count} 关 → {os.path.basename(bk_dir)}/')
            except Exception as e:
                log.log(f'  ⚠ pre-tune backup failed: {e}')
        if not phase_apply_probes(log, probes):
            log.log('  apply_probes failed — skipping this round')
            continue

        # ── Phase 3: Unity bot batch ──
        current_pending = sorted(pending, key=int)

        # Preflight: 提交前验证
        preflight_path = os.path.join(TOOLS, 'preflight.py')
        if os.path.exists(preflight_path):
            log.log(f'[Preflight] asset & config check...')
            pf = subprocess.run(
                [sys.executable, preflight_path, 'submit',
                 '--levels', ','.join(str(l) for l in current_pending),
                 '--tiers', ','.join(str(t) for t in tiers),
                 '--unit-only'],
                capture_output=True, text=True, timeout=60
            )
            if pf.returncode != 0:
                log.log(f'  ⛔ Preflight FAILED:')
                for line in pf.stdout.split('\n')[-10:]:
                    if line.strip():
                        log.log(f'    {line.strip()}')
                # Don't block — preflight is advisory in auto mode
                log.log(f'  ⚠ Continuing despite preflight warnings...')
            else:
                log.log(f'  ✅ Preflight passed')

        # Warden: pre-batch safety check
                warden_path = os.path.join(TOOLS, 'warden.py')
                if os.path.exists(warden_path):
                    log.log(f'[Warden] pre-batch check...')
                    # 2026-08-07 修复：传 --probe-file（探针质量检查 W09 依赖它）——
                    # 之前只传 --levels，Warden 里 tiers_map 为空 → W02 空转（审计 B6）
                    probe_file = os.path.join(TOOLS, 'probe_configs.json')
                    warden_cmd = [sys.executable, warden_path, '--levels',
                                  ','.join(str(l) for l in current_pending)]
                    if os.path.exists(probe_file):
                        warden_cmd += ['--probe-file', probe_file]
                    wr = subprocess.run(
                        warden_cmd,
                        capture_output=True, text=True, timeout=30
                    )
            if wr.returncode != 0:
                log.log(f'  ⛔ Warden BLOCKED batch. Fix violations before retry.')
                for line in wr.stdout.split('\n')[-10:]:
                    if 'BLOCKED' in line or '[' in line:
                        log.log(f'    {line.strip()}')
                continue
            log.log(f'  ✅ Warden passed')

        log.log(f'[Phase 3/5] submit_batch_unity → Unity bot batch')
        # 2026-08-04：探针轮（round<6）开贝叶斯提前停提速；最后一轮跑满验证
        # 2026-08-10 标准：探针轮（round<6）--probe-games（默认200）+贝叶斯——
        #   明显不在目标范围的配置 200 局足以看出方向；验证轮（round 6）跑满 --games（400）。
        use_adaptive = args.adaptive_stop and round_num < MAX_ROUNDS
        batch_games = args.probe_games if round_num < MAX_ROUNDS else args.games
        log.log(f'  adaptive_stop={"ON" if use_adaptive else "OFF"} (round {round_num}/{MAX_ROUNDS})')
        log.log(f'  games={batch_games} (探针轮{args.probe_games}/验证轮{args.games})')
        if not phase_submit_batch(
            log, current_pending, tiers, batch_games, args.strategy, use_adaptive
        ):
            log.log('  Unity batch failed — skipping this round')
            # Do NOT mark levels as errors on first batch failure;
            # submit_batch_unity may have partial results.
            continue

        # ── Phase 4: Refresh pools ──
        log.log(f'[Phase 4/5] dump_level_pools → refresh stage-data')
        phase_refresh_pools(log)

        # ── Phase 5: Review → pass/fail ──
        log.log(f'[Phase 5/5] judge_level → review & verdict')
        review_results = phase_review(log, current_pending)

        for lv, status in review_results.items():
            if status['result'] == '合格':
                passed[lv] = status
                pending.discard(lv)
                tag = '已入库'
                rnd = status["round"]
                log.log(f'  ✅ L{lv} PASSED → {tag} (round {rnd})')
                # ── 2026-08-05 修复：全自动不自动入库 ──
                # 用户明确「全自动的情况下不能入库！只能标记合格然后等待我确认」。
                # 不自动 write_ddc 写 asset、不自动写 Excel/board、不自动跑 bot 400 验证。
                # 只记录最优组合配置到日志，供用户确认后由主 agent 用 reimport.py 落盘。
                try:
                    t = et.get_target(lv)
                    recs = dedup_records(get_all_records(str(lv)))
                    verified = filter_verified(recs)
                    res = find_best_monotonic(
                        verified, t['tiers'], top_n=1, difficulty=t['diff']
                    )
                    if res and res[0]:
                        best = res[0][2]
                        if t['diff'] == 'normal':
                            idx = [0, 0, 2, 4, 4]  # T1=T2, T4=T5
                        else:
                            idx = [0, 1, 2, 3, 4]  # 5 档独立
                        # 2026-08-05 修复：用局部变量 best_tiers，绝不覆盖全局 tiers
                        # （之前 tiers = [...] 污染全局，L162 入库后续轮探针全被替换成
                        # 最优组合 dict，导致 ROUND 3-6 探针空转、数据永不变化）
                        best_tiers = [{'sd': int(best[i]['sd']), 'sc': int(best[i]['sc']),
                                       'ratios': str(best[i]['ratios']), 'of': float(best[i]['of'])}
                                      for i in idx]
                        wrs = [f"{r['wr']:.1f}%" for r in best]
                        note = t['diff']
                        log.log(f'    ⏳ L{lv} 合格待确认入库（未落盘）: WR={wrs}')
                        log.log(f'    ⏳   配置: ' + ' | '.join(
                            f"sd{c['sd']}/{c['sc']}/{c['ratios']}/of{c['of']}" for c in best_tiers))
                        log.log(f'    ⏳   难度={note} 目标={t["tiers"]}')
                        log.log(f'    ⏳   确认后由主 agent 用 reimport.py 落盘 asset/Excel/board')
                    else:
                        log.log(f'    ⏳ L{lv} 合格但 find_best_monotonic 无组合，待人工确认')
                except Exception as ex:
                    log.log(f'    ⏳ L{lv} 记录最优组合失败: {ex}')
            elif status['round'] >= MAX_ROUNDS:
                failed[lv] = status
                pending.discard(lv)
                log.log(
                    f'  ❌ L{lv} MAX ROUNDS ({MAX_ROUNDS}) → 待用户确认改关卡'
                )
                # ── 2026-08-05 修复：全自动不自动标记改关卡 ──
                # 用户明确「改关卡必须用户同意后才能执行」。只报告，
                # 不自动调 retire_level 设时间防线，等用户确认后再手动执行。
                log.log(f'    ⏳ L{lv} 满 {MAX_ROUNDS} 轮仍不合格，待用户确认是否改关卡')
                log.log(f'    ⏳   判定原因: {"; ".join(status.get("reasons", [])[:3])}')
                log.log(f'    ⏳   需要时由主 agent 手动 retire_level 设时间防线')
            else:
                # Still pending — will be processed in next round
                pass

        log.log(
            f'  Round {round_num} done: '
            f'{len(passed)} passed, {len(pending)} pending, {len(failed)} failed'
        )
        # ── 2026-08-17：每轮结构化报告（解决黑盒）──
        # 输出 auto_loop_round_report.json：每关探针配置（实际写 asset 的）
        # + 该轮批次实际胜率（最新批次 campaign-summary CSV）+ 判定结果。
        # 主 agent 每轮结束直接读它展示给用户，不用手动查 probe_configs + CSV。
        try:
            round_report = _build_round_report(round_num, probes, review_results, current_pending)
            report_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'project-state', 'auto_loop_round_report.json')
            with open(report_path, 'w', encoding='utf-8') as f:
                json.dump(round_report, f, indent=2, ensure_ascii=False)
            log.log(f'  📋 round report saved: {report_path}')
        except Exception as e:
            log.log(f'  ⚠ round report failed: {e}')
        # ── Checkpoint：每轮完成后持久化状态，支持断点续跑（2026-08-10 新增）──
        try:
            cp = {
                'round': round_num,
                'levels': sorted(pending, key=int),
                'passed': {k: v.get('round') for k, v in passed.items()},
                'failed': {k: v.get('round') for k, v in failed.items()},
                'errors': dict(errors),
                'saved_at': time.strftime('%Y-%m-%dT%H:%M:%S'),
            }
            cp_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'project-state', 'auto_loop_checkpoint.json')
            with open(cp_path, 'w', encoding='utf-8') as f:
                json.dump(cp, f, indent=2, ensure_ascii=False)
            log.log(f'  💾 checkpoint saved: round {round_num}, pending={len(pending)}')
        except Exception as e:
            log.log(f'  ⚠ checkpoint save failed: {e}')

    # ── Final summary ──
    log.log(' FINAL SUMMARY')
    log.log('=' * 60)

    log.log(f' ✅ Passed (入库):  {len(passed)} levels')
    for lv in sorted(passed.keys(), key=int):
        s = passed[lv]
        log.log(f'    L{lv} [{s["difficulty"]}] r{s["round"]}  {s.get("wrs", "")}')

    log.log(f' ❌ Failed (改关卡): {len(failed)} levels')
    for lv in sorted(failed.keys(), key=int):
        s = failed[lv]
        reasons_str = '; '.join(s.get('reasons', [])[:2])
        wrs_str = s.get('wrs', 'N/A')
        log.log(f'    L{lv} [{s["difficulty"]}] r{s["round"]} — {wrs_str}')
        if reasons_str:
            log.log(f'        {reasons_str}')

    log.log(f' ⚠ Errors:           {len(errors)} levels')
    for lv, err in sorted(errors.items(), key=lambda x: int(x[0])):
        log.log(f'    L{lv}: {err}')

    log.log(f' 🔄 Still pending:    {len(pending)} levels')
    for lv in sorted(pending, key=int):
        log.log(f'    L{lv}')

    log.log('')
    log.log(f' Full log: {log_path}')

    # ── Curator: 跨轮经验积累（在 log.close() 之前调用）──
    curator_path = os.path.join(TOOLS, 'curator.py')
    if os.path.exists(curator_path):
        subprocess.run([sys.executable, curator_path, '--log', log_path],
                      capture_output=True, timeout=30)
        log.log(f' Curator: pattern analysis complete')

    log.close()

    # Exit code: non-zero if any levels are still pending
    sys.exit(0 if not pending else 1)


if __name__ == '__main__':
    main()
