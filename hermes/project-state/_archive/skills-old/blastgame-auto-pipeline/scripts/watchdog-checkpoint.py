#!/usr/bin/env python3
"""
watchdog-checkpoint.py — 自动构建 pipeline-progress-check.json

用途：消除 agent 手动构造 JSON 时反复遗漏 stuck_count 等必填字段的问题。
      一次终端调用完成全部检查 + JSON 构建 + 字段完整性保证。

依赖：Python 3.8+, 仅使用标准库 json, os, datetime, pathlib

使用：
  python3 /c/Users/.../skills/game-design/blastgame-auto-pipeline/scripts/watchdog-checkpoint.py
  (输出到 stdout，重定向保存)

输出：
  - 打印 JSON 到 stdout
  - 退出码：0（成功），1（数据读取失败）

⚠️ 路径硬编码为 BlastGame 项目路径。
"""

import json, os, datetime, sys, re
from pathlib import Path

BASE = Path(r"C:\Users\Administrator\Documents\BlastGame")
PROGRESS_PATH = BASE / "BuildLogs" / "pipeline-progress.json"
CHECKPOINT_PATH = BASE / "BuildLogs" / "pipeline-progress-check.json"
BOT_DIR = BASE / "telemetry" / "bot"

NOW = datetime.datetime.now()

def fmt_dt(dt):
    return dt.strftime("%Y-%m-%d %H:%M")

def parse_dt(s):
    for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H-%M-%S", "%Y-%m-%dT%H-%M-%S.%f"]:
        try:
            return datetime.datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None

def main():
    if not PROGRESS_PATH.exists():
        print(f"ERROR: {PROGRESS_PATH} not found", file=sys.stderr); sys.exit(1)
    with open(PROGRESS_PATH, encoding="utf-8") as f:
        pp = json.load(f)

    levels_done = pp.get("levels_done", 0)
    levels_total = pp.get("levels_total", "?")
    scope = pp.get("scope", "?")
    done_array_len = len(pp.get("levels", {}).get("done", []))
    if levels_done != done_array_len:
        levels_done = done_array_len
    progress_mtime = datetime.datetime.fromtimestamp(PROGRESS_PATH.stat().st_mtime)

    prev = {}
    if CHECKPOINT_PATH.exists():
        with open(CHECKPOINT_PATH, encoding="utf-8") as f:
            prev = json.load(f)
    prev_levels_done = prev.get("levels_done", levels_done)
    prev_last_check_str = prev.get("last_check", None)
    prev_last_check_dt = parse_dt(prev_last_check_str) if prev_last_check_str else None

    now_ts = NOW.timestamp()
    cutoff_30 = now_ts - 1800
    recent_30 = []
    all_bot = []
    if BOT_DIR.exists():
        for e in sorted(BOT_DIR.iterdir(), key=lambda e: e.stat().st_mtime, reverse=True):
            if e.is_dir():
                m = e.stat().st_mtime; all_bot.append(e.name)
                if m >= cutoff_30:
                    recent_30.append(e.name)

    new_since_check = []
    if prev_last_check_dt:
        pt = prev_last_check_dt.timestamp()
        if BOT_DIR.exists():
            for e in BOT_DIR.iterdir():
                if e.is_dir() and e.stat().st_mtime > pt:
                    new_since_check.append(e.name)
    else:
        new_since_check = recent_30[:]

    latest_ts = ""; latest_name = ""
    sorted_dirs = sorted([e for e in BOT_DIR.iterdir() if e.is_dir()] if BOT_DIR.exists() else [],
                         key=lambda e: e.stat().st_mtime, reverse=True)
    if sorted_dirs:
        latest_ts = fmt_dt(datetime.datetime.fromtimestamp(sorted_dirs[0].stat().st_mtime))
        latest_name = sorted_dirs[0].name

    ld_changed = levels_done != prev_levels_done
    has_recent = len(recent_30) > 0
    prog_upd = prev_last_check_dt is None or progress_mtime > prev_last_check_dt
    is_active = ld_changed or has_recent or prog_upd
    stuck = not is_active

    ps = prev.get("stuck_count", 0)
    if isinstance(ps, bool): ps = 1 if ps else 0
    ps = int(ps) if isinstance(ps, (int, float)) else 0
    stuck_count = 0 if is_active else ps + 1

    lsa = prev.get("last_stuck_alert", None)
    if stuck and stuck_count == 1:
        lsa = fmt_dt(NOW)
    elif not stuck:
        lsa = None

    s_reason = ""
    if stuck:
        bits = []
        if not ld_changed: bits.append(f"levels_done={levels_done} 未变")
        if not has_recent: bits.append("30 分钟无 Bot 目录")
        if sorted_dirs:
            a = int((NOW - datetime.datetime.fromtimestamp(sorted_dirs[0].stat().st_mtime)).total_seconds() / 60)
            bits.append(f"最后 Bot 目录 {a} 分钟前")
        s_reason = "; ".join(bits)

    cp = {
        "last_check": fmt_dt(NOW),
        "levels_done": levels_done,
        "recent_bot_dirs": recent_30[:5],
        "latest_bot_timestamp": latest_ts,
        "last_progress_update": fmt_dt(progress_mtime),
        "stuck_count": stuck_count,
        "last_stuck_alert": lsa,
        "levels_total": levels_total,
        "scope": scope,
        "stuck": stuck,
        "stuck_reason": s_reason,
        "new_dirs_since_last_check": len(new_since_check),
        "total_bot_dirs": len(all_bot),
        "latest_bot_dir": latest_name,
        "done_array_len": done_array_len,
        "last_checkpoint_levels_done": prev_levels_done,
        "last_checkpoint_time": prev_last_check_str or "N/A",
    }

    if recent_30:
        cp["active_batch"] = re.sub(r'-2026-\d{2}-\d{2}T[\d\-]+.*$', '', recent_30[0]).replace("-batch-range", "")

    json.dump(cp, sys.stdout, indent=2, ensure_ascii=False)
    print()

if __name__ == "__main__":
    main()
