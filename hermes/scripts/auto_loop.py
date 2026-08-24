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
from collections.abc import Mapping
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


# ── Phase 1: deterministic context + Hermes probe selector ──

def _select_ai_probes(log, levels, round_num):
    """Ask the current Hermes model for candidate IDs, fail-open to script."""
    selected = {}
    decisions = {}
    try:
        from tools.llm_probe_pipeline import design_probes_llm
    except Exception as exc:
        log.log(f'  AI probe selector unavailable: {type(exc).__name__}')
        return selected, decisions

    for lv in levels:
        try:
            result = design_probes_llm(str(lv), round_num=round_num, advisor_mode='llm')
        except Exception as exc:
            log.log(f'  L{lv}: AI probe selector exception — {type(exc).__name__}')
            continue
        status = result.get('status', 'disabled') if isinstance(result, dict) else 'disabled'
        raw = result.get('probes') if isinstance(result, dict) else None
        if status not in ('llm_original', 'llm_after_hint', 'script_fallback') or not isinstance(raw, dict):
            log.log(f'  L{lv}: AI selector {status}; retain planner output')
            continue
        raw_list = []
        for key, probe in sorted(raw.items(), key=lambda item: int(str(item[0]).lstrip('T') or 0)):
            if not isinstance(probe, dict):
                continue
            item = dict(probe)
            item['tier'] = int(str(key).lstrip('T'))
            raw_list.append(item)
        if len(raw_list) != 5:
            log.log(f'  L{lv}: AI selector returned {len(raw_list)}/5 probes; retain planner output')
            continue
        selected[str(lv)] = {
            f'T{item["tier"]}': {
                key: value for key, value in item.items()
                if key in ('sd', 'sc', 'ratios', 'of')
            }
            for item in raw_list
        }
        decisions[str(lv)] = {
            'status': status,
            'designer': result.get('designer', 'script'),
            'decision_source': result.get('decision_provenance', {}).get('decision_source', status),
            'selected_candidate_ids': result.get('selected_candidate_ids', []),
            'candidate_to_execution_slot': result.get('decision_provenance', {}).get('candidate_to_execution_slot', {}),
            'decision_id': result.get('decision_id'),
            'snapshot_hash': result.get('snapshot_hash'),
            'context_hash': result.get('context_hash'),
            'catalog_id': result.get('catalog_id'),
            'manifest_version': result.get('decision_provenance', {}).get('manifest_version'),
            'manifest_hash': result.get('decision_provenance', {}).get('manifest_hash'),
            'memory_snapshot_hash': result.get('decision_provenance', {}).get('memory_snapshot_hash'),
            'prompt_version': result.get('decision_provenance', {}).get('prompt_version'),
            'actual_llm_calls': result.get('actual_llm_calls', 0),
            'errors': result.get('errors', []),
            'decision': result.get('decision'),
            'decision_provenance': result.get('decision_provenance'),
        }
        log.log(
            f'  L{lv}: probe designer={status}, '
            f'candidate_ids={result.get("selected_candidate_ids", [])}'
        )
    return selected, decisions


def phase_analyze(log, levels, round_num=1, return_metadata=False, use_ai=True):
    """Run planner (决策编排) to get combo analysis and probes for each level.

    planner 内部串联：agent_analyze → judge_level → design_probes。
    返回 {lv_str: {T1:{sd,sc,ratios,of}, ...}, ...}
    """
    probes = {}
    ai_probes, ai_decisions = (
        _select_ai_probes(log, levels, round_num) if use_ai else ({}, {})
    )
    levels_str = ','.join(str(l) for l in levels)

    cmd = [
        sys.executable, '-X', 'utf8',
        os.path.join(TOOLS, 'planner.py'),
        '--levels', levels_str,
        '--output', 'json',
    ]
    if use_ai:
        cmd.append('--skip-probes')

    result = run_cmd(log, cmd, timeout=600)
    if not result:
        log.log('  planner FAILED after retries')
        return (ai_probes, ai_decisions) if return_metadata else ai_probes

    data = extract_json(result.stdout)
    if not data:
        log.log('  planner: could not parse JSON output')
        # Dump first 500 chars for debugging
        preview = (result.stdout or '')[:500]
        log.log(f'  stdout preview: {preview}')
        return (ai_probes, ai_decisions) if return_metadata else ai_probes

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

        raw_probes = ai_probes.get(lv, r.get('probes', []))
        judge = r.get('judge', '?')
        log.log(f'  L{lv}: {len(raw_probes)} probes, judge={judge}, combo quality={combo.get("quality","?")}')

        # Convert probe list -> probe_configs.json format {T1:{...}, T2:{...}, ...}.
        # Never fill a missing slot with combo/default data: that would turn a
        # failed experiment design into a plausible-looking Unity batch.
        tier_probes = _normalise_probe_slots(raw_probes)
        if tier_probes is None:
            log.log(f'  L{lv}: probe design rejected — requires 5 raw probe records')
            continue
        probes[lv] = tier_probes
        log.log(f'  L{lv}: {len(tier_probes)}/5 tiers configured')

    # Planner output may omit a level after a partial failure. AI already has
    # an independent deterministic context, so retain its valid five-slot
    # result instead of silently dropping that level.
    for lv, ai_config in ai_probes.items():
        if lv not in probes:
            normalised = _normalise_probe_slots(ai_config)
            if normalised is not None:
                probes[lv] = normalised
    return (probes, ai_decisions) if return_metadata else probes


def _normalise_probe_slots(raw_probes):
    """Convert five raw probe records into five occupied slots.

    Duplicate or missing tier labels are assigned to the next free slot rather
    than overwriting an earlier probe. The caller still requires five records;
    no combo/default fabrication happens here.
    """
    if isinstance(raw_probes, dict):
        converted = []
        for key, probe in raw_probes.items():
            item = dict(probe) if isinstance(probe, dict) else probe
            if isinstance(item, dict):
                item['tier'] = str(key).lstrip('T')
            converted.append(item)
        raw_probes = converted
    if not isinstance(raw_probes, list) or len(raw_probes) < 5:
        return None
    slots = {}
    for probe in raw_probes[:5]:
        if not isinstance(probe, dict):
            return None
        try:
            requested = int(probe.get('tier', 0))
        except (TypeError, ValueError):
            requested = 0
        if requested not in range(1, 6) or requested in slots:
            requested = next((slot for slot in range(1, 6) if slot not in slots), None)
        if requested is None:
            return None
        slots[f'T{requested}'] = {
            'sd': int(probe.get('sd', 0)),
            'sc': int(probe.get('sc', 5)),
            'ratios': str(probe.get('ratios', '')),
            'of': float(probe.get('of', 0.5)),
        }
    return slots if len(slots) == 5 else None


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

    result = run_cmd(log, cmd, timeout=120)
    if result:
        # Print the last few lines of output
        lines = result.stdout.strip().split('\n')
        for line in lines[-10:]:
            if line.strip():
                log.log(f'    {line.strip()}')
        # 2026-08-18：解析失败关列表——部分成功时只跳过失败关，不整轮放弃
        # 注意：stdout 行可能带 '[stdout] ' 前缀（run_cmd 打印时加的），需剥离
        failed = []
        for line in lines:
            clean = line.strip()
            if clean.startswith('[stdout] '):
                clean = clean[len('[stdout] '):]
            if clean.startswith('FAILED_LEVELS:'):
                failed = [x for x in clean.split(':', 1)[1].split(',') if x.strip()]
        # 2026-08-18：apply_probes 部分失败时退出码为 0（FAILED_LEVELS 已记录），
        # 所以这里以 FAILED_LEVELS 为准判断部分成功，而非退出码
        return (result.returncode == 0 or bool(failed)), failed
    else:
        log.log('  apply_probes FAILED')
        return False, []


# ── Phase 3: submit_batch_unity → Unity bot batch ──

def phase_submit_batch(log, levels, tiers, games=400, strategy='scoring_opt_vg', adaptive_stop=False,
                       v3_request=None, expected_probes=None):
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
        # 2026-08-19 P0-4：贝叶斯提前停最小局数兜底（防极端配置 30 局过早停）
        cmd.append('--bayes-min-runs')
        cmd.append('60')
    # Legacy mode uses the existing Workbench EditorPrefs worker setting.
    # V3 kept the CLI override for backwards-compatible manual experiments;
    # the active workflow no longer depends on it.
    if v3_request:
        cmd.append('--worker-count')
        cmd.append('7')
    if v3_request:
        from tools.pipeline.unity_request import write_request
        request_path = os.path.join(
            HERMES, 'batch-logs', 'v3-request-' + str(v3_request['batch_id']) + '.json')
        write_request(request_path, v3_request)
        cmd.extend(['--v3-request', request_path])
        log.log('  V3 request: ' + request_path)

    # Timeout: at least 2 hours, or scaled by level×tier count
    timeout = max(len(levels) * len(tiers) * 300, 7200)
    log.log(
        f'  Submitting Unity batch: {len(levels)} levels × {len(tiers)} tiers, '
        f'timeout={timeout}s ({timeout // 60}min)'
    )

    # A V3 request owns one immutable batch identity.  Retrying the same
    # command after Unity has created its batch directory would reuse the same
    # batch_id with a second execution and fail closed as a specification
    # conflict (or, worse, create ambiguous artifacts).  Legacy submissions
    # retain the historical single retry because they have no V3 identity.
    started_at = time.time()
    result = run_cmd(log, cmd, timeout=timeout, retries=0 if v3_request else 1)
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

    if not v3_request:
        try:
            from tools.pipeline.legacy_batch import (
                LegacyBatchVerificationError,
                resolve_legacy_batch_dir,
                verify_legacy_batch,
            )
            batch_dir = resolve_legacy_batch_dir(REPO, result.stdout, started_at=started_at)
            details = verify_legacy_batch(
                batch_dir,
                levels,
                tiers,
                expected_probes or {},
                max_games=games,
            )
            log.log(
                f'  ✅ legacy CSV/asset 验收: {details["artifact_count"]} artifacts '
                f'(batch_dir={details["batch_dir"]})'
            )
            return details
        except Exception as exc:
            # A validation defect must fail closed, not crash the orchestrator
            # after Unity has already spent the batch budget. The caller stops
            # the campaign on this status instead of blindly rerunning Unity.
            log.log(f'  ⛔ legacy 批次验收失败: {type(exc).__name__}: {exc}')
            return {
                'mode': 'legacy',
                'status': 'verification_failed',
                'error': f'{type(exc).__name__}: {exc}',
            }

    # V3 path: successful submission is defined by the explicit request-bound
    # receipt and CSV artifacts. Never select a "latest" directory by mtime.
    try:
        from tools.pipeline.batch_run import verify_batch_artifacts
        artifact_result = verify_batch_artifacts(
            os.path.join(REPO, 'telemetry', 'bot'), v3_request
        )
        if artifact_result.get('status') != 'accepted':
            log.log(f'  ⛔ CSV 验收阻断: {artifact_result.get("status")}')
            return False
        log.log(
            f'  ✅ CSV/receipt 验收: {len(artifact_result.get("artifacts", []))} artifacts '
            f'(batch_id={v3_request["batch_id"]})'
        )
    except Exception as exc:
        log.log(f'  ⛔ CSV/receipt 验收失败: {exc}')
        return False

    return True


class _AutoLoopBatchRunner:
    """Adapter that makes the existing submit script the Coordinator runner."""

    def __init__(self, log, levels, tiers, games, strategy, adaptive_stop):
        self.log = log
        self.levels = levels
        self.tiers = tiers
        self.games = games
        self.strategy = strategy
        self.adaptive_stop = adaptive_stop

    def run(self, request):
        from tools.pipeline.runtime import V3RunRuntime
        safe_run_id = ''.join(ch if ch.isalnum() or ch in '-_.' else '_' for ch in request['run_id'])
        runtime = V3RunRuntime(os.path.join(HERMES, 'runs', safe_run_id), request)
        runtime.start()
        runtime.submitted()
        ok = phase_submit_batch(
            self.log, self.levels, self.tiers, self.games,
            self.strategy, self.adaptive_stop, request,
        )
        if not ok:
            raise RuntimeError('UNITY_BATCH_FAILED')
        receipt_path = os.path.join(
            REPO, 'telemetry', 'bot', str(request['batch_id']), 'unity_receipt.json')
        try:
            with open(receipt_path, encoding='utf-8') as receipt_file:
                receipt = json.load(receipt_file)
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f'V3_RECEIPT_MISSING: {receipt_path}: {exc}') from exc
        ingest_receipt = runtime.finish(receipt)
        return {
            'status': 'submitted',
            'run_id': request['run_id'],
            'attempt_id': request['attempt_id'],
            'receipt': receipt,
            'ingest_receipt': ingest_receipt,
            'runtime': runtime,
        }


def _auto_loop_preflight(log, request):
    """Run the existing preflight CLI and expose a Coordinator-compatible result."""
    preflight_path = os.path.join(TOOLS, 'preflight.py')
    if not os.path.exists(preflight_path):
        return {'returncode': 1, 'stdout': 'preflight.py missing'}
    levels = request.get('levels', [])
    tiers = request.get('tiers', [])
    log.log('[Preflight] asset & config check...')
    try:
        result = subprocess.run(
            [sys.executable, preflight_path, 'submit',
             '--levels', ','.join(str(l) for l in levels),
             '--tiers', ','.join(str(t) for t in tiers),
             '--unit-only'],
            capture_output=True, text=True, timeout=60,
        )
    except Exception as exc:
        raise RuntimeError(f'preflight execution failed: {exc}') from exc
    stdout = (result.stdout or '') + ('\n' + result.stderr if result.stderr else '')
    if result.returncode == 0:
        log.log('  ✅ Preflight passed')
    else:
        log.log('  ⛔ Preflight FAILED')
        for line in stdout.splitlines()[-10:]:
            if line.strip():
                log.log(f'    {line.strip()}')
    return {'returncode': result.returncode, 'stdout': stdout}


def _auto_loop_warden(log, request):
    """Run all legacy Warden checks; absence/error is fail-closed."""
    warden_path = os.path.join(TOOLS, 'warden.py')
    if not os.path.exists(warden_path):
        return False, 'WARDEN_MISSING warden.py missing'
    levels = request.get('levels', [])
    probe_file = os.path.join(TOOLS, 'probe_configs.json')
    command = [sys.executable, warden_path, '--levels', ','.join(str(l) for l in levels)]
    if os.path.exists(probe_file):
        command += ['--probe-file', probe_file]
    log.log('[Warden] pre-batch check...')
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=30)
    except Exception as exc:
        return False, f'WARDEN_EXCEPTION {exc}'
    if result.returncode == 0:
        log.log('  ✅ Warden passed')
        return True, ''
    output = (result.stdout or '') + ('\n' + result.stderr if result.stderr else '')
    log.log('  ⛔ Warden BLOCKED batch')
    for line in output.splitlines()[-10:]:
        if 'BLOCKED' in line or '[' in line:
            log.log(f'    {line.strip()}')
    return False, f'WARDEN_BLOCKED {output[-300:]}'


def phase_submit_guarded(
        log, levels, tiers, probes, games=400, strategy='scoring_opt_vg',
        adaptive_stop=False, round_num=1, *, preflight_fn=None, warden_fn=None,
        runner=None, run_id=None, decision_metadata=None):
    """Submit only after preflight, V3 W02/W09/health and legacy Warden pass.

    This is the one legacy Phase-3 gateway.  All adapters are injectable so
    tests can prove a blocked condition starts Unity zero times.
    """
    from tools.pipeline.control import Coordinator, PipelineBlocked
    from tools.pipeline.policy import production_guards

    level_list = [str(level) for level in levels]
    request = {
        # RunStore 的 run.json 是不可变规格；每轮的 attempt_id / plan hash
        # 会变化，因此 run_id 必须按轮次隔离，不能复用同一目录。
        'run_id': run_id or f'auto-{os.path.basename(getattr(log, "path", "run"))}-r{round_num}',
        'attempt_id': f'round-{round_num}',
        'levels': level_list,
        'tiers': list(tiers),
        'probes': probes,
        'require_decision_provenance': True,
    }
    try:
        from tools.pipeline.unity_request import build_unity_request
        request.update(build_unity_request(
            levels=[int(level) for level in levels],
            tiers=tiers,
            run_id=request['run_id'],
            attempt_id=request['attempt_id'],
            games=games,
            adaptive_stop=adaptive_stop,
            strategy=strategy,
            worker_count=7,
            bayes_min_runs=60,
        ))
        from tools.pipeline.provenance import build_decision_provenance, validate_decision_provenance
        decision_metadata = decision_metadata if isinstance(decision_metadata, Mapping) else {}
        request['decision_provenance'] = {}
        for level in level_list:
            raw = decision_metadata.get(level, {})
            if not isinstance(raw, Mapping):
                raw = {}
            nested = raw.get('decision_provenance')
            if isinstance(nested, Mapping):
                validate_decision_provenance(
                    nested,
                    level=level,
                    round_num=round_num,
                    probes=probes.get(level, {}),
                )
                provenance = dict(nested)
            else:
                metadata = dict(raw)
                if not metadata:
                    metadata = {
                        'decision_source': 'deterministic_planner',
                        'designer': 'planner',
                        'actual_llm_calls': 0,
                    }
                provenance = build_decision_provenance(
                    level=level,
                    round_num=round_num,
                    probes=probes.get(level, {}),
                    metadata=metadata,
                )
            validate_decision_provenance(
                provenance,
                level=level,
                round_num=round_num,
                probes=probes.get(level, {}),
            )
            request['decision_provenance'][level] = provenance
    except Exception as exc:
        log.log(f'  ⛔ V3 request build blocked before Unity: {exc}')
        return False
    active_preflight = preflight_fn or (lambda req: _auto_loop_preflight(log, req))
    active_warden = warden_fn or (lambda req: _auto_loop_warden(log, req))
    active_runner = runner or _AutoLoopBatchRunner(
        log, levels, tiers, games, strategy, adaptive_stop,
    )
    coordinator = Coordinator(
        runner=active_runner,
        preflight=active_preflight,
        guards=[*production_guards(), active_warden],
    )
    try:
        result = coordinator.run(request)
        if isinstance(result, Mapping):
            return {'ok': True, 'request': request, **result}
        return {'ok': True, 'request': request, 'result': result}
    except PipelineBlocked as exc:
        log.log(f'  ⛔ Phase-3 blocked before Unity: {exc.code} {exc.detail}')
        return False
    except Exception as exc:
        # Runner failures are distinct from safety blocks but must never allow
        # subsequent refresh/judge steps to treat this round as successful.
        log.log(f'  ⛔ Phase-3 submission failed: {exc}')
        return False


def phase_submit_legacy_guarded(
        log, levels, tiers, probes, games=400, strategy='scoring_opt_vg',
        adaptive_stop=False):
    """Active single-Unity batch gateway without V3 identity plumbing.

    The legacy path still requires preflight, Warden, explicit batch-directory
    discovery, loaded-asset snapshots, and complete campaign-summary coverage.
    It deliberately does not touch the Unity C# V3 entry points.
    """
    request = {
        'levels': [str(level) for level in levels],
        'tiers': list(tiers),
        'probes': probes,
    }
    preflight = _auto_loop_preflight(log, request)
    if preflight.get('returncode') != 0:
        log.log('  ⛔ legacy preflight failed before Unity')
        return False
    warden_ok, warden_detail = _auto_loop_warden(log, request)
    if not warden_ok:
        log.log(f'  ⛔ legacy Warden blocked before Unity: {warden_detail}')
        return False
    return phase_submit_batch(
        log,
        levels,
        tiers,
        games=games,
        strategy=strategy,
        adaptive_stop=adaptive_stop,
        expected_probes=probes,
    )


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


def _build_round_report(round_num, probes, review_results, levels, submission_context=None):
    """Collect probes, explicit receipt WRs and the authoritative verdict.

    Measured WRs are read only from this round's accepted receipt artifacts.
    Missing identity/receipt data remains visible as missing; no mtime/latest
    directory heuristic is allowed to fabricate a result.
    """
    from tools.pipeline.batch_run import receipt_games, receipt_win_rates

    request = submission_context.get('request', {}) if isinstance(submission_context, Mapping) else {}
    receipt = submission_context.get('receipt') if isinstance(submission_context, Mapping) else None
    if isinstance(submission_context, Mapping) and submission_context.get('mode') == 'legacy':
        batch_wrs = submission_context.get('batch_wrs', {})
        batch_games = submission_context.get('batch_games', {})
        identity = {
            'mode': 'legacy',
            'batch_dir': submission_context.get('batch_dir', ''),
            'artifact_count': submission_context.get('artifact_count', 0),
        }
        receipt_status = 'legacy_artifacts_verified'
        wrs_source = 'legacy_campaign_summary_artifacts'
    else:
        batch_wrs = receipt_win_rates(receipt or {}, levels)
        batch_games = receipt_games(receipt or {}, levels)
        identity = {
            key: request.get(key)
            for key in ('run_id', 'attempt_id', 'batch_id', 'request_plan_hash', 'logic_version')
        } if request else {}
        if request:
            identity['decision_ids'] = {
                str(level): value.get('decision_id')
                for level, value in (request.get('decision_provenance') or {}).items()
                if isinstance(value, Mapping)
            }
        receipt_status = receipt.get('status') if isinstance(receipt, Mapping) else 'missing'
        wrs_source = 'accepted_receipt_artifacts' if receipt else 'missing_explicit_receipt'

    report = {
        'round': round_num,
        'saved_at': time.strftime('%Y-%m-%dT%H:%M:%S'),
        'batch_identity': identity,
        'receipt_status': receipt_status,
        'batch_wrs_source': wrs_source,
        'levels': {},
    }
    for lv in levels:
        lv = str(lv)
        report['levels'][lv] = {
            'probes': probes.get(lv, {}),
            'batch_wrs': batch_wrs.get(lv, {}),
            'batch_games': batch_games.get(lv, {}),
            'judge': review_results.get(lv, {}),
        }
    return report


# ── Phase 5: agent_review / judge_level → pass/fail ──

def phase_review(log, levels, v3_context=None):
    """Judge each level using judge_with_rounds, which reads stage-data
    and manages round tracking via _rounds.json.

    Returns {lv_str: {result, difficulty, round, max_rounds, action, reasons, wrs}}
    """
    # Make tools importable
    if TOOLS not in sys.path:
        sys.path.insert(0, TOOLS)

    import judge_level  # noqa: E402 — deliberate late import after path setup

    results = {}
    v3_runtime = v3_context.get('runtime') if isinstance(v3_context, Mapping) else None
    for lv in sorted(levels, key=int):
        lv_int = int(lv)
        if v3_context is not None:
            if v3_runtime is None:
                combo, result, reasons, ri = None, 'ERROR_BLOCKED', ['V3 runtime missing'], {
                    'round': judge_level.get_round(lv_int), 'max': MAX_ROUNDS,
                    'action': 'blocked_missing_runtime',
                }
            elif not v3_context.get('receipt') or v3_context['receipt'].get('status') != 'accepted':
                combo, result, reasons, ri = None, 'ERROR_BLOCKED', ['accepted receipt missing'], {
                    'round': judge_level.get_round(lv_int), 'max': MAX_ROUNDS,
                    'action': 'blocked_missing_receipt',
                }
            else:
                try:
                    supporting_roots = v3_context.get('supporting_run_roots', [])
                    records = v3_runtime.records_for_judge(lv_int, supporting_roots)
                    v3_context.setdefault('judge_records', {})[str(lv)] = records
                    v3_context.setdefault('judge_generation_ids', {})[str(lv)] = (
                        v3_runtime.consumed_generation_ids(lv_int)
                    )
                    combo, result, reasons, ri = judge_level.judge_with_rounds(
                        lv_int, records_override=records)
                except Exception as exc:
                    combo, result, reasons, ri = None, 'ERROR_BLOCKED', [f'V3 generation rejected: {exc}'], {
                        'round': judge_level.get_round(lv_int), 'max': MAX_ROUNDS,
                        'action': 'blocked_generation',
                    }
        else:
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

        # Keep optimizer-summary evidence separate from receipt-bound Judge data.
        # A receipt pool can have no legal combo while the current-board
        # multi-tier optimizer has a separate candidate set.  Do not change the
        # authoritative result or round accounting; expose the alternate scope
        # explicitly so "no combo" is never reported as "no project-wide plan".
        if result == '不合格' and any('无法拼出单调递减组合' in str(reason)
                                    for reason in reasons):
            try:
                from tools.pipeline.optimizer_summary import evaluate_optimizer_summary
                optimizer_evidence = evaluate_optimizer_summary(lv_int)
                if optimizer_evidence:
                    status['optimizer_summary'] = optimizer_evidence
                    log.log(
                        f'  ⚠ L{lv} receipt池=无合法组合；'
                        f'当前牌面optimizer summary={optimizer_evidence["judge_result"]}'
                    )
                    for reason in optimizer_evidence.get('judge_reasons', [])[:3]:
                        log.log(f'    • optimizer: {reason}')
            except Exception as optimizer_exc:
                # Evidence discovery must never block the receipt-bound Judge.
                status['optimizer_summary_error'] = str(optimizer_exc)
                log.log(f'  ⚠ L{lv} optimizer summary 检查失败（不影响 receipt Judge）: {optimizer_exc}')

        results[str(lv)] = status

        if v3_runtime is not None and result in ('合格', '接近', '不合格'):
            try:
                generation_ids = (v3_context.get('judge_generation_ids', {})
                                  .get(str(lv), [])) if isinstance(v3_context, Mapping) else []
                v3_runtime.judged(
                    lv_int,
                    result,
                    supporting_generation_ids=generation_ids[1:],
                )
            except Exception as exc:
                status['result'] = 'ERROR_BLOCKED'
                status['action'] = 'blocked_event_persist'
                status['reasons'] = [f'JUDGED event rejected: {exc}']
                log.log(f'  ⛔ L{lv} V3 JUDGED event rejected: {exc}')

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
        '--probe-games', type=int, default=400,
        help='探针轮每档局数 (default: 400)；adaptive-stop 开启时仍受 '
             '--bayes-min-runs=60 保护，验证轮默认 400 局')
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
    log.log(' Batch mode: LEGACY (readable batch dir + post-run asset snapshot)')
    log.log('')
    # ── Safety: never terminate a user's Unity process ──
    log.log('[Safety] 检查 Unity 进程...')
    unity_busy = False
    try:
        r = subprocess.run(['tasklist'], capture_output=True, text=False, timeout=10)
        out = r.stdout.decode('gbk', errors='replace') if r.stdout else ''
        if 'Unity.exe' in out:
            unity_busy = True
            log.log('  ⛔ Unity.exe 正在运行，阻断本轮；不自动 taskkill 用户进程')
        else:
            log.log('  无 Unity 进程')
    except Exception as e:
        unity_busy = True
        log.log(f'  ⛔ Unity 进程检查失败，fail-closed: {e}')

    if HERMES not in sys.path:
        sys.path.insert(0, HERMES)
    if unity_busy:
        log.log('  ⛔ 请先关闭 Unity 后重新启动 auto_loop')
        log.close()
        sys.exit(1)
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
    # 2026-08-19 P0-1 失败三级分类：
    #   L0 单关失败（探针失败/无数据）→ consec_fail[lv]++，≥2 次无产出移入 errors
    #   L1 整批失败（apply_probes 全失败/submit 失败）→ batch_fail++，≥2 次提前终止
    #   L2 崩溃（进程被杀）→ checkpoint 恢复兜底
    consec_fail = {}   # lv → 连续无产出轮数
    batch_fail = 0     # 整批连续失败次数

    # ── Resume from checkpoint（2026-08-10 新增）──
    resume_round = 0
    history_run_roots = []
    planner_campaign_id = f'auto-{os.path.splitext(os.path.basename(log_path))[0]}'
    planner_session_id = None
    planner_client = None
    resume_state_loaded = False
    if args.resume:
        cp_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'project-state', 'auto_loop_checkpoint.json')
        if os.path.exists(cp_path):
            try:
                with open(cp_path, encoding='utf-8') as f:
                    cp = json.load(f)
                checkpoint_levels = {
                    str(x) for x in cp.get('campaign_levels', [])
                }
                if not checkpoint_levels:
                    checkpoint_levels = (
                        {str(x) for x in cp.get('levels', [])}
                        | {str(x) for x in cp.get('passed', {})}
                        | {str(x) for x in cp.get('failed', {})}
                        | {str(x) for x in cp.get('errors', {})}
                    )
                requested_levels = {str(x) for x in levels}
                if checkpoint_levels != requested_levels:
                    raise ValueError(
                        f'checkpoint level set mismatch: '
                        f'checkpoint={sorted(checkpoint_levels, key=int)} '
                        f'requested={sorted(requested_levels, key=int)}'
                    )
                saved_round = cp.get('round', 0)
                planner_campaign_id = cp.get('planner_campaign_id') or planner_campaign_id
                planner_session_id = cp.get('planner_session_id') or None
                history_run_roots = [
                    os.path.normpath(str(root))
                    for root in cp.get('run_roots', [])
                    if isinstance(root, str) and os.path.isdir(root)
                ]
                # Resume must retain prior terminal statuses in the final
                # summary; otherwise a passed level removed from pending is
                # silently omitted after restart (e.g. L148).
                for lv, value in cp.get('passed', {}).items():
                    info = et.get_target(int(lv))
                    passed[str(lv)] = {
                        'round': value if isinstance(value, int) else 0,
                        'difficulty': info.get('diff', 'unknown') if info else 'unknown',
                        'result': '合格',
                        'wrs': '',
                    }
                for lv, value in cp.get('failed', {}).items():
                    info = et.get_target(int(lv))
                    failed[str(lv)] = {
                        'round': value if isinstance(value, int) else MAX_ROUNDS,
                        'difficulty': info.get('diff', 'unknown') if info else 'unknown',
                        'result': '不合格',
                        'reasons': [],
                    }
                # 只保留 checkpoint 里仍 pending 的关（passed/failed 不再跑）
                cp_pending = set(str(x) for x in cp.get('levels', []))
                keep = pending & cp_pending
                done = set(str(x) for x in cp.get('passed', {})) | set(str(x) for x in cp.get('failed', {}))
                dropped = sorted(pending - cp_pending - done, key=int)
                pending = keep
                resume_round = saved_round
                resume_state_loaded = True
                log.log(f'  🔄 RESUME: checkpoint round={saved_round}, pending={sorted(pending, key=int)}')
                if dropped:
                    log.log(f'  ⚠ 从 pending 移除（checkpoint 无记录）: {dropped}')
            except Exception as e:
                log.log(f'  ⚠ resume failed（忽略，从头跑）: {e}')
        else:
            log.log('  ⚠ --resume 但无 checkpoint，从头跑')

    if not resume_state_loaded:
        # A new campaign must not inherit stale per-level rounds left by an
        # interrupted campaign or an earlier manual Judge invocation.
        try:
            if TOOLS not in sys.path:
                sys.path.insert(0, TOOLS)
            import judge_level as _round_judge
            for level in levels:
                _round_judge.reset_round(int(level))
            log.log(f'  🧹 fresh campaign: reset rounds for {sorted(levels)}')
        except Exception as exc:
            log.log(f'  ⛔ fresh campaign round reset failed: {exc}')
            log.close()
            sys.exit(1)

    # ── Shared Planner session ──
    try:
        from tools import llm_client as planner_client
        planner_client.configure_campaign(planner_campaign_id, planner_session_id)
        log.log(
            f'  Planner campaign={planner_campaign_id} '
            f'session={"resumed" if planner_client.session_active() else "new"}'
        )
    except Exception as e:
        log.log(f'  ⚠ shared Planner session setup failed: {e}')

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
        probes, ai_decisions = phase_analyze(
            log, pending_sorted, round_num=round_num, return_metadata=True
        )

        # Fallback: if any pending level has no probes, try design_probes directly
        missing_probes = [lv for lv in pending_sorted if str(lv) not in probes]
        if missing_probes:
            log.log(
                f'  {len(missing_probes)} level(s) missing probes — '
                f'running fallback design_probes...'
            )
            fallback_ok = fallback_design_probes(log, missing_probes)

            # Re-read probes after fallback
            probes2, ai_decisions2 = phase_analyze(
                log, fallback_ok, round_num=round_num, return_metadata=True, use_ai=False
            )
            probes.update(probes2)
            ai_decisions.update(ai_decisions2)

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
        ok_probes, failed_probes = phase_apply_probes(log, probes)
        if not ok_probes and not failed_probes:
            log.log('  apply_probes 完全失败 — skipping this round')
            # 2026-08-19 P0-1 L1：整批失败计数，≥2 次提前终止
            batch_fail += 1
            if batch_fail >= 2:
                log.log(f'  ❌ 连续 {batch_fail} 轮整批失败 — 提前终止')
                break
            continue
        else:
            batch_fail = 0  # 本轮有部分成功，重置整批失败计数
        # 2026-08-18：部分成功时，跳过失败关（从本轮批跑移除），其余继续
        if failed_probes:
            log.log(f'  ⏭ 跳过探针失败关: {failed_probes}，仅调优其余关')
            # 2026-08-19 P0-1 L0：单关连续失败计数，≥2 次无产出移入 errors
            for lv in failed_probes:
                consec_fail[str(lv)] = consec_fail.get(str(lv), 0) + 1
                if consec_fail[str(lv)] >= 2:
                    errors[str(lv)] = f'连续 {consec_fail[str(lv)]} 轮无产出（探针失败）'
                    pending.discard(str(lv))
                    log.log(f'    ❌ L{lv} 连续 {consec_fail[str(lv)]} 轮无产出 → 移入 errors')
            # 从本轮批跑 levels 移除失败关
            run_levels = [lv for lv in probes.keys() if str(lv) not in failed_probes]
        else:
            run_levels = list(probes.keys())
        if not run_levels:
            log.log('  ⚠ 所有关探针失败，跳过本轮')
            continue

        # ── Phase 3: Unity bot batch ──
        current_pending = sorted(run_levels, key=int)
        log.log(f'[Phase 3/5] submit_batch_unity → Unity bot batch')
        # 2026-08-04：探针轮（round<6）开贝叶斯提前停提速；最后一轮跑满验证
        # 探针轮（round<6）使用 --probe-games（默认400）+贝叶斯；
        # 验证轮（round 6）跑满 --games（默认400）。阈值与 min-runs 不在这里改写。
        use_adaptive = args.adaptive_stop and round_num < MAX_ROUNDS
        batch_games = args.probe_games if round_num < MAX_ROUNDS else args.games
        log.log(f'  adaptive_stop={"ON" if use_adaptive else "OFF"} (round {round_num}/{MAX_ROUNDS})')
        log.log(f'  games={batch_games} (探针轮{args.probe_games}/验证轮{args.games})')
        active_probes = {
            str(lv): probes[str(lv)]
            for lv in current_pending
            if str(lv) in probes
        }
        submission_context = phase_submit_legacy_guarded(
            log, current_pending, tiers, active_probes, batch_games,
            args.strategy, use_adaptive,
        )
        if (
            isinstance(submission_context, Mapping)
            and submission_context.get('mode') == 'legacy'
            and submission_context.get('status') == 'verification_failed'
        ):
            log.log(
                '  ⛔ legacy 验收器异常，fail-closed 停止本 campaign；'
                '不重复提交已完成的 Unity batch'
            )
            break
        if not submission_context:
            log.log('  Unity batch failed — skipping this round')
            # 2026-08-19 P0-1 L1：批跑失败计数，≥2 次提前终止（submit 可能部分成功）
            batch_fail += 1
            if batch_fail >= 2:
                log.log(f'  ❌ 连续 {batch_fail} 轮整批失败（submit_batch）— 提前终止')
                break
            # Do NOT mark levels as errors on first batch failure;
            # submit_batch_unity may have partial results.
            continue
        else:
            batch_fail = 0

        # ── Phase 4/5: legacy batch refresh + Judge ──
        log.log(f'[Phase 4/5] dump_level_pools → refresh stage-data')
        if not phase_refresh_pools(log):
            log.log('  stage-data refresh failed — skipping this round')
            batch_fail += 1
            if batch_fail >= 2:
                log.log(f'  ❌ 连续 {batch_fail} 轮数据刷新失败 — 提前终止')
                break
            continue

        log.log(f'[Phase 5/5] judge_level → review & verdict')
        review_results = phase_review(log, current_pending, None)
        legacy_batch_dir = str(submission_context.get('batch_dir', ''))
        if legacy_batch_dir:
            history_run_roots.append(legacy_batch_dir)

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
                    runtime = submission_context.get('runtime') if isinstance(submission_context, Mapping) else None
                    recs = ((submission_context.get('judge_records', {}) or {}).get(str(lv))
                            if isinstance(submission_context, Mapping)
                            else None)
                    if recs is None:
                        recs = (runtime.records_for_judge(
                            lv,
                            submission_context.get('supporting_run_roots', []),
                        ) if runtime is not None
                        else dedup_records(get_all_records(str(lv))))
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
            round_report = _build_round_report(
                round_num, probes, review_results, current_pending, submission_context
            )
            round_report['ai_decisions'] = ai_decisions
            report_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'project-state', 'auto_loop_round_report.json')
            with open(report_path, 'w', encoding='utf-8') as f:
                json.dump(round_report, f, indent=2, ensure_ascii=False)
            log.log(f'  📋 round report saved: {report_path}')
            try:
                from tools.llm_probe_pipeline import record_round_outcomes
                record_round_outcomes(round_report)
            except Exception as metric_exc:
                log.log(f'  ⚠ AI outcome metrics failed (non-blocking): {metric_exc}')
        except Exception as e:
            log.log(f'  ⚠ round report failed: {e}')
        # ── Checkpoint：每轮完成后持久化状态，支持断点续跑（2026-08-10 新增）──
        try:
            cp = {
                'round': round_num,
                'campaign_levels': sorted(levels),
                'levels': sorted(pending, key=int),
                'passed': {k: v.get('round') for k, v in passed.items()},
                'failed': {k: v.get('round') for k, v in failed.items()},
                'errors': dict(errors),
                'run_roots': list(history_run_roots),
                'planner_campaign_id': planner_campaign_id,
                'planner_session_id': (
                    planner_client.session_id() if planner_client is not None else planner_session_id
                ),
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
