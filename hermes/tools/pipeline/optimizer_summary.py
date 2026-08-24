#!/usr/bin/env python3
"""Read current-board multi-tier optimizer summaries as separate evidence.

Optimizer summaries and V3 receipt generations are deliberately kept as two
provenance domains. This module only discovers/evaluates the former; callers
must not merge its rows into receipt-bound Judge records implicitly.
"""
from __future__ import annotations

import csv
import os
import re
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

from tools.data.adapters import excel_target as et
from tools.judge_level import check_judgment


DEFAULT_REPO = os.environ.get("BLASTGAME_REPO", r"C:\Users\Administrator\Documents\BlastGame")
DEFAULT_OPT_ROOT = os.path.join(DEFAULT_REPO, "telemetry", "multi-tier-opt")
LOCAL_TZ = timezone(timedelta(hours=8))
LOGIC_VERSION_SINCE = "2026-08-13T14:36:00+08:00"
_TIMESTAMP_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})T(\d{2})-(\d{2})-(\d{2})")
_TIER_RE = re.compile(r"^T([1-5])(?:-|$)")


def _path_timestamp(path: str | Path) -> float:
    """Use the real batch timestamp encoded in the directory name."""
    matches = list(_TIMESTAMP_RE.finditer(str(path)))
    if matches:
        m = matches[-1]
        dt = datetime(
            int(m.group(1)), int(m.group(2)), int(m.group(3)),
            int(m.group(4)), int(m.group(5)), int(m.group(6)),
            tzinfo=LOCAL_TZ,
        )
        return dt.timestamp()
    try:
        return os.path.getmtime(path)
    except OSError:
        return 0.0


def _logic_cutoff() -> float:
    return datetime.fromisoformat(LOGIC_VERSION_SINCE).timestamp()


def _tier_index(value: str) -> int | None:
    match = _TIER_RE.match(str(value or "").strip())
    return int(match.group(1)) if match else None


def _is_false(value: Any) -> bool:
    return str(value or "").strip().lower() in {"", "false", "0", "no"}


def _read_summary(path: Path, level: int) -> dict[str, Any] | None:
    """Read one per-level optimizer summary only if all five rows are valid."""
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = [
                row for row in csv.DictReader(handle)
                if str(row.get("GameLevel", "")).strip() == str(level)
            ]
    except (OSError, csv.Error, UnicodeError, ValueError):
        return None

    valid = []
    for row in rows:
        if str(row.get("Rank", "")).strip() != "1":
            continue
        if str(row.get("Status", "")).strip().lower() != "ok":
            continue
        if not _is_false(row.get("OutOfMargin")):
            continue
        tier = _tier_index(row.get("Tier", ""))
        if tier is None:
            continue
        try:
            valid.append({
                "tier": tier,
                "wr": round(float(row["VerifiedWinRate"]) * 100.0, 2),
                "sd": row.get("StartDifficulty", "").strip(),
                "sc": row.get("ShuffleSplitCount", "").strip(),
                "ratios": row.get("ShuffleSplitRatios", "").strip(),
                "of": row.get("ShuffleOverflowFactor", "").strip(),
                "source_phase": row.get("SourcePhase", "").strip(),
                "total_games": int(row.get("TotalRuns", 0) or 0),
                "configured_target": round(float(row.get("ConfiguredTargetWinRate", 0)) * 100.0, 2),
            })
        except (KeyError, TypeError, ValueError):
            return None

    if len(valid) != 5 or {row["tier"] for row in valid} != {1, 2, 3, 4, 5}:
        return None
    valid.sort(key=lambda row: row["tier"])

    fingerprints = {
        str(row.get("BoardFingerprint", "")).strip()
        for row in rows
        if str(row.get("BoardFingerprint", "")).strip()
    }
    if len(fingerprints) != 1:
        return None

    return {
        "source_path": str(path),
        "created_at": datetime.fromtimestamp(
            _path_timestamp(path), tz=LOCAL_TZ
        ).isoformat(),
        "board_fingerprint": next(iter(fingerprints)),
        "tiers": valid,
    }


def _current_board_fingerprint(level: int) -> str | None:
    """Use the existing official helper path; fail closed if it cannot read it."""
    try:
        from tools.compare_level_db import find_asset_path, get_board_fp
        asset_path = find_asset_path(level)
        return get_board_fp(asset_path) if asset_path else None
    except Exception:
        return None


@lru_cache(maxsize=256)
def _find_latest_cached(level: int, current_board_fingerprint: str, opt_root: str) -> dict[str, Any] | None:
    root = Path(opt_root)
    if not root.is_dir():
        return None

    candidates: list[tuple[float, dict[str, Any]]] = []
    for summary_path in root.rglob("summary.csv"):
        batch_timestamp = _path_timestamp(summary_path)
        if batch_timestamp < _logic_cutoff():
            continue
        summary = _read_summary(summary_path, level)
        if not summary:
            continue
        if summary["board_fingerprint"] != current_board_fingerprint:
            continue
        candidates.append((batch_timestamp, summary))

    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def find_latest_optimizer_summary(
    level: int,
    *,
    current_board_fingerprint: str | None = None,
    opt_root: str | None = None,
) -> dict[str, Any] | None:
    """Find the newest valid five-tier summary for the current board fingerprint."""
    fingerprint = current_board_fingerprint or _current_board_fingerprint(int(level))
    if not fingerprint:
        return None
    return _find_latest_cached(int(level), fingerprint, opt_root or DEFAULT_OPT_ROOT)


def evaluate_optimizer_summary(
    level: int,
    *,
    current_board_fingerprint: str | None = None,
    opt_root: str | None = None,
) -> dict[str, Any] | None:
    """Evaluate optimizer evidence with the current Judge, without merging it."""
    summary = find_latest_optimizer_summary(
        int(level),
        current_board_fingerprint=current_board_fingerprint,
        opt_root=opt_root,
    )
    if not summary:
        return None

    target = et.get_target(int(level))
    if not target:
        return None
    wrs = [row["wr"] for row in summary["tiers"]]
    combo = {f"T{i + 1}": wr for i, wr in enumerate(wrs)}
    result, reasons = check_judgment(combo, target["diff"], target["tiers"])
    return {
        "evidence_type": "multi_tier_optimizer_summary",
        "source_path": summary["source_path"],
        "created_at": summary["created_at"],
        "board_fingerprint": summary["board_fingerprint"],
        "wrs": wrs,
        "tiers": summary["tiers"],
        "judge_result": result,
        "judge_reasons": reasons,
    }


__all__ = ["find_latest_optimizer_summary", "evaluate_optimizer_summary"]
