#!/usr/bin/env python3
"""Hermes client for the shared BlastGame Planner campaign session.

The business pipeline never handles credentials or provider endpoints. Every
attempt goes through the installed Hermes CLI, which owns authentication.
Technical failure is structured and fail-open to the frozen script fallback.
One Planner session is reused across the campaign so it can learn across
levels; current-level evidence is scoped in each prompt and durable state.
"""

from __future__ import annotations

import atexit
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import time
from typing import Any

PROJECT_STATE = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "project-state"))
ADVISOR_CFG = os.path.join(PROJECT_STATE, "llm_advisor.json")
USAGE_LOG = os.path.join(PROJECT_STATE, "llm_usage.jsonl")
ADVISOR_DIR = os.path.join(PROJECT_STATE, "advisor")
PLANNER_SESSION_STATE = os.path.join(PROJECT_STATE, "planner_session.json")

CURRENT_PROVIDER = "current"
CURRENT_MODEL = "current"
REASONING_EFFORT = "max"
PROMPT_VERSION = "probe-design-v4-shared-session"
_SESSION_ID_RE = re.compile(r"(?:^|\n)\s*session_id:\s*([^\s]+)")

_CAMPAIGN_ID: str | None = None
_SESSION_ID: str | None = None
_CAMPAIGN_STARTED_AT = 0.0


def _load_advisor_cfg() -> dict[str, Any]:
    try:
        with open(ADVISOR_CFG, encoding="utf-8") as fh:
            value = json.load(fh)
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _log_usage(entry: dict[str, Any]) -> None:
    try:
        os.makedirs(PROJECT_STATE, exist_ok=True)
        with open(USAGE_LOG, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")
    except Exception:
        pass


def _today() -> str:
    return time.strftime("%Y-%m-%d")


def _daily_calls_today() -> int:
    try:
        count = 0
        with open(USAGE_LOG, encoding="utf-8") as fh:
            for line in fh:
                try:
                    if json.loads(line).get("ts", "").startswith(_today()):
                        count += 1
                except Exception:
                    continue
        return count
    except Exception:
        return 0


def available() -> bool:
    cfg = _load_advisor_cfg()
    return bool(cfg.get("enabled", False)) and _daily_calls_today() < int(cfg.get("daily_call_limit", 200))


def _load_saved_session() -> dict[str, Any]:
    try:
        with open(PLANNER_SESSION_STATE, encoding="utf-8") as fh:
            value = json.load(fh)
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _persist_session() -> None:
    if not _CAMPAIGN_ID:
        return
    try:
        os.makedirs(os.path.dirname(PLANNER_SESSION_STATE), exist_ok=True)
        tmp_path = PLANNER_SESSION_STATE + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as fh:
            json.dump({
                "campaign_id": _CAMPAIGN_ID,
                "session_id": _SESSION_ID,
                "session_name": _session_name(),
                "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            }, fh, ensure_ascii=False, indent=2)
        os.replace(tmp_path, PLANNER_SESSION_STATE)
    except Exception:
        pass


def configure_campaign(campaign_id: str, session_id: str | None = None,
                       *, load_saved: bool = True) -> None:
    """Bind this process to the shared Planner campaign session."""
    global _CAMPAIGN_ID, _SESSION_ID, _CAMPAIGN_STARTED_AT
    _CAMPAIGN_ID = str(campaign_id or "") or None
    _SESSION_ID = str(session_id).strip() if session_id else None
    _CAMPAIGN_STARTED_AT = time.time()
    if _SESSION_ID is None and load_saved:
        saved = _load_saved_session()
        if str(saved.get("campaign_id") or "") == str(_CAMPAIGN_ID or ""):
            saved_id = saved.get("session_id")
            if saved_id:
                _SESSION_ID = str(saved_id)
    if _SESSION_ID:
        _hide_tool_session(_SESSION_ID)
    _persist_session()


def reset_campaign_for_test() -> None:
    """Clear in-memory session state without touching production state."""
    global _CAMPAIGN_ID, _SESSION_ID, _CAMPAIGN_STARTED_AT
    _CAMPAIGN_ID = None
    _SESSION_ID = None
    _CAMPAIGN_STARTED_AT = 0.0


def campaign_id() -> str | None:
    return _CAMPAIGN_ID


def session_id() -> str | None:
    return _SESSION_ID


def session_active() -> bool:
    return bool(_SESSION_ID)


def _session_name() -> str:
    """Stable human-readable session key for one campaign.

    A name is deliberately used in addition to the opaque session id: a CLI
    process killed by a timeout can create a row before it returns the id.
    ``--continue --create-if-missing`` can recover that row on the next call.
    """
    raw = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(_CAMPAIGN_ID or "planner"))
    return f"blastgame-planner-{raw[:96]}"


def _hermes_state_db_path() -> str:
    home = os.environ.get("HERMES_HOME")
    if not home:
        home = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "hermes")
    return os.path.join(os.path.expanduser(home), "state.db")


def _hide_tool_session(session_id: str | None) -> None:
    """Soft-hide a Planner session from global Desktop listings.

    The session remains resumable by id/name. This is intentionally best
    effort: a busy Hermes DB must not block probe design.
    """
    if not session_id:
        return
    try:
        db_path = _hermes_state_db_path()
        if not os.path.isfile(db_path):
            return
        conn = sqlite3.connect(db_path, timeout=5)
        try:
            conn.execute("PRAGMA busy_timeout=5000")
            conn.execute(
                "UPDATE sessions SET hidden=1 WHERE id=? AND source='tool'",
                (str(session_id),),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception:
        pass


def _finish_tool_sessions() -> None:
    """Hide and close the current campaign's tool session at process exit."""
    try:
        db_path = _hermes_state_db_path()
        if not os.path.isfile(db_path):
            return
        conn = sqlite3.connect(db_path, timeout=5)
        try:
            conn.execute("PRAGMA busy_timeout=5000")
            ids = set()
            if _SESSION_ID:
                ids.add(str(_SESSION_ID))
            if _CAMPAIGN_ID:
                rows = conn.execute(
                    "SELECT id FROM sessions WHERE source='tool' AND title=?",
                    (_session_name(),),
                ).fetchall()
                ids.update(str(row[0]) for row in rows)
            for session_id in ids:
                conn.execute(
                    "UPDATE sessions SET hidden=1, ended_at=COALESCE(ended_at, strftime('%s','now')), "
                    "end_reason=COALESCE(end_reason, 'tool_campaign_end') "
                    "WHERE id=? AND source='tool'",
                    (session_id,),
                )
            conn.commit()
        finally:
            conn.close()
    except Exception:
        pass


atexit.register(_finish_tool_sessions)


def _prompt(system: str, user: str, json_mode: bool) -> str:
    campaign = ""
    if _CAMPAIGN_ID:
        campaign = (
            "[SHARED PLANNER CAMPAIGN]\n"
            f"campaign_id={_CAMPAIGN_ID}\n"
            "This is one shared Planner session across levels. The CURRENT_LEVEL "
            "and CURRENT_ROUND in the latest user payload are authoritative. "
            "Prior turns are cross-level experience only; never treat their raw "
            "candidate records as evidence for the current level.\n\n"
        )
    text = f"{campaign}[SYSTEM]\n{system}\n\n[USER]\n{user}"
    if json_mode:
        text += "\n\nReturn JSON only. Do not include markdown fences or commentary."
    return text


def _extract_json(text: str) -> Any:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        parts = cleaned.split("\n", 1)
        cleaned = parts[1].rsplit("```", 1)[0].strip() if len(parts) == 2 else cleaned
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        starts = [i for i in (cleaned.find("{"), cleaned.find("[")) if i >= 0]
        if not starts:
            raise
        start = min(starts)
        for end in range(len(cleaned), start, -1):
            try:
                return json.loads(cleaned[start:end])
            except json.JSONDecodeError:
                continue
        raise


def _extract_session_id(stderr: str | bytes | None) -> str | None:
    if isinstance(stderr, bytes):
        stderr = stderr.decode("utf-8", errors="replace")
    if not stderr:
        return None
    match = _SESSION_ID_RE.search(str(stderr))
    return match.group(1) if match else None


def _build_command(prompt: str) -> list[str]:
    command = [
        "hermes", "chat", "-q", prompt,
        "--quiet", "--source", "tool",
    ]
    if _SESSION_ID:
        command.extend(["--resume", _SESSION_ID])
    else:
        command.extend(["--continue", _session_name(), "--create-if-missing"])
    command.extend(["--reasoning", REASONING_EFFORT, "--ignore-rules"])
    return command


def _session_not_found(stderr: str | bytes | None) -> bool:
    if isinstance(stderr, bytes):
        stderr = stderr.decode("utf-8", errors="replace")
    text = (stderr or "").lower()
    return "session" in text and any(token in text for token in ("not found", "missing", "unknown"))


def _run_command(command: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=timeout,
        encoding="utf-8",
        errors="replace",
        shell=False,
    )


def _ask_via_hermes(system: str, user: str, max_tokens: int | None, json_mode: bool,
                    agent: str, timeout: int = 120) -> Any:
    global _SESSION_ID
    del max_tokens
    prompt = _prompt(system, user, json_mode)
    prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    started = time.time()
    reused_session = bool(_SESSION_ID)
    command = _build_command(prompt)
    common = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "agent": agent,
        "provider_selection": CURRENT_PROVIDER,
        "model_selection": CURRENT_MODEL,
        "reasoning": REASONING_EFFORT,
        "prompt_version": PROMPT_VERSION,
        "prompt_hash": prompt_hash,
        "campaign_id": _CAMPAIGN_ID,
        "session_reused": reused_session,
    }
    entry = dict(common)
    try:
        proc = _run_command(command, timeout)
        if proc.returncode != 0 and _SESSION_ID and _session_not_found(proc.stderr):
            _SESSION_ID = None
            _persist_session()
            reused_session = False
            command = _build_command(prompt)
            proc = _run_command(command, timeout)
            entry["session_recreated"] = True

        new_session_id = _extract_session_id(proc.stderr)
        if new_session_id:
            _SESSION_ID = new_session_id
            _hide_tool_session(_SESSION_ID)
            _persist_session()
        entry.update({
            "session_id": _SESSION_ID,
            "session_reused": reused_session,
            "returncode": proc.returncode,
            "latency_s": round(time.time() - started, 3),
        })
        output = (proc.stdout or "").strip()
        if proc.returncode != 0:
            entry.update({"status": "error", "error": "hermes_nonzero"})
            _log_usage(entry)
            return None
        entry.update({"status": "ok", "output_hash": hashlib.sha256(output.encode("utf-8")).hexdigest()})
        if json_mode:
            try:
                value = _extract_json(output)
            except Exception:
                entry.update({"status": "error", "error": "invalid_json"})
                _log_usage(entry)
                return None
            _log_usage(entry)
            return value
        _log_usage(entry)
        return output
    except subprocess.TimeoutExpired as exc:
        new_session_id = _extract_session_id(getattr(exc, "stderr", None))
        if new_session_id:
            _SESSION_ID = new_session_id
            _hide_tool_session(_SESSION_ID)
            _persist_session()
        entry.update({"session_id": _SESSION_ID, "status": "error", "error": "timeout",
                      "latency_s": round(time.time() - started, 3)})
        _log_usage(entry)
        return None
    except Exception as exc:
        entry.update({"session_id": _SESSION_ID, "status": "error", "error": type(exc).__name__,
                      "latency_s": round(time.time() - started, 3)})
        _log_usage(entry)
        return None


def ask(system: str, user: str, *, max_tokens: int | None = None, json_mode: bool = True,
        timeout: int = 120, agent: str = "probe") -> Any:
    if not available():
        _log_usage({
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "agent": agent,
            "provider_selection": CURRENT_PROVIDER, "model_selection": CURRENT_MODEL,
            "reasoning": REASONING_EFFORT, "prompt_version": PROMPT_VERSION,
            "status": "disabled", "campaign_id": _CAMPAIGN_ID,
        })
        return None
    return _ask_via_hermes(system, user, max_tokens, json_mode, agent, timeout)


def write_advisor(agent: str, lv: str | int, round_num: int, content: Any) -> str | None:
    """Write rationale/evidence only; never persist raw chain-of-thought."""
    try:
        os.makedirs(ADVISOR_DIR, exist_ok=True)
        filename = f"{agent}_{lv}_{round_num}_{time.strftime('%Y%m%d_%H%M%S')}.json"
        with open(os.path.join(ADVISOR_DIR, filename), "w", encoding="utf-8") as fh:
            json.dump({
                "ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "agent": agent,
                "level": str(lv), "round": round_num, "content": content,
            }, fh, ensure_ascii=False, indent=2)
        return filename
    except Exception:
        return None


if __name__ == "__main__":
    print(json.dumps({"available": available(), "provider_selection": CURRENT_PROVIDER,
                      "model_selection": CURRENT_MODEL, "reasoning": REASONING_EFFORT,
                      "campaign_id": _CAMPAIGN_ID, "session_id": _SESSION_ID}))
