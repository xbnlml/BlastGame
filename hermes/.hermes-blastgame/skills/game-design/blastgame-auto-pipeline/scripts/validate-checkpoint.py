#!/usr/bin/env python3
"""
validate-checkpoint.py — pipeline-progress-check.json 写入前验证器

使用：
  python3 scripts/validate-checkpoint.py BuildLogs/pipeline-progress-check.json

功能：
  1. 检查必填 7 字段是否存在（含 stuck_count 和 last_stuck_alert）
  2. 检查字段名是否与 schema 一致（防 typo）
  3. 检查 stuck_count 类型为 int
  4. 检查 last_stuck_alert 格式（ISO 或 null）
  5. 检查 last_check 格式（YYYY-MM-DD HH:MM）
  6. 检查 recent_bot_dirs 类型
  7. 交叉检查 levels_done 与 levels_total

返回码：
  0 = 通过
  1 = 至少一项检查未通过（输出到 stderr）
"""

import json, sys, re

def check(condition, msg):
    if not condition:
        print(f"  [FAIL] {msg}", file=sys.stderr)
        return False
    return True

def validate(path):
    errors = 0
    with open(path, encoding='utf-8') as f:
        d = json.load(f)

    print(f"Validating: {path}")

    # ── 必填 7 字段 ──
    required = [
        "last_check",
        "levels_done",
        "recent_bot_dirs",
        "latest_bot_timestamp",
        "last_progress_update",
        "stuck_count",
        "last_stuck_alert",
    ]
    for field in required:
        if not check(field in d, f"Missing required field: {field}"):
            errors += 1

    # ── 字段名防 typo ──
    known_typos = {
        "check_time": "应该用 last_check（不是 check_time）",
        "stuck": "stuck 是可选字段，但 stuck_count 是必填",
        "latest_bot": "应该用 latest_bot_timestamp",
        "bot_active_30min": "bot_active_30min 是可选，不是必填",
        "stuck_counter": "应该用 stuck_count（不是 stuck_counter）",
        "stuck_alert_last": "应该用 last_stuck_alert",
    }
    for typo, hint in known_typos.items():
        if typo in d:
            print(f"  [WARN] 字段 '{typo}' 存在？{hint}", file=sys.stderr)

    # ── stuck_count 类型 ──
    if "stuck_count" in d:
        if not check(isinstance(d["stuck_count"], int),
                     f"stuck_count 必须是 int，收到 {type(d['stuck_count']).__name__}"):
            errors += 1

    # ── last_stuck_alert 格式 ──
    if "last_stuck_alert" in d:
        v = d["last_stuck_alert"]
        if v is not None:
            if not check(isinstance(v, str) and len(v) >= 16,
                         f"last_stuck_alert 应为 'YYYY-MM-DD HH:MM' 字符串或 null，收到 '{v}'"):
                errors += 1

    # ── last_check 格式 ──
    if "last_check" in d:
        if not check(re.match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}", d["last_check"]),
                     f"last_check 格式应为 'YYYY-MM-DD HH:MM'，收到 '{d['last_check']}'"):
            errors += 1

    # ── recent_bot_dirs 类型 ──
    if "recent_bot_dirs" in d:
        if not check(isinstance(d["recent_bot_dirs"], list),
                     f"recent_bot_dirs 必须是 list，收到 {type(d['recent_bot_dirs']).__name__}"):
            errors += 1

    # ── levels_done 与 levels_total ──
    if "levels_done" in d and "levels_total" in d:
        if not check(d["levels_done"] <= d["levels_total"],
                     f"levels_done ({d['levels_done']}) 不应大于 levels_total ({d['levels_total']})"):
            errors += 1

    # ── stuck 与 stuck_count 的逻辑关系 ──
    if "stuck" in d and d["stuck"] == True and "stuck_count" in d:
        if d["stuck_count"] == 0:
            print("  [WARN] stuck=true 但 stuck_count=0 — 首次卡住应设 stuck_count=1", file=sys.stderr)

    # ── 可选字段类型检查 ──
    optional_checks = [
        ("levels_total", int),
        ("new_dirs_since_last_check", int),
        ("bot_active_30min", bool),
        ("unity_editor_running", bool),
    ]
    for field, expected_type in optional_checks:
        if field in d and d[field] is not None:
            if not check(isinstance(d[field], expected_type),
                         f"{field} 应为 {expected_type.__name__}，收到 {type(d[field]).__name__}"):
                errors += 1

    # ── stuck_reason 长度 ──
    if "stuck_reason" in d and d["stuck_reason"] is not None:
        if not check(len(d["stuck_reason"]) >= 10,
                     f"stuck_reason 太短（{len(d['stuck_reason'])} 字符），应有描述性内容"):
            errors += 1

    # ── pipeline_phase 认可值 ──
    valid_phases = ["running", "stalled", "dead", "optimizer_running",
                    "bot_batch_active", "post_batch_stall", "mixed_state",
                    "idle_after_retest", "stalled_after_retest",
                    "retest_only_loop"]
    if "pipeline_phase" in d:
        if d["pipeline_phase"] not in valid_phases:
            print(f"  [WARN] pipeline_phase='{d['pipeline_phase']}' 不在认可值列表中", file=sys.stderr)

    print()
    if errors == 0:
        print(f"ALL CHECKS PASSED ({len(required)} required fields OK)")
    else:
        print(f"{errors} CHECK(S) FAILED — 修正后再写入", file=sys.stderr)

    return errors

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python3 scripts/validate-checkpoint.py <path-to-checkpoint.json>", file=sys.stderr)
        sys.exit(2)
    sys.exit(validate(sys.argv[1]))
