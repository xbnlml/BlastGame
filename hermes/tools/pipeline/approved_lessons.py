"""Safe, deterministic loader for approved role lessons.

Legacy ``agents/*/memory.md`` is intentionally not read here.  Only
machine-readable, active lessons with evidence and matching scope can enter a
role context.
"""

from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


LESSON_VERSION = "APPROVED_LESSONS_V1"
_ALLOWED_STATUS = {"active", "proposed", "rejected", "superseded", "expired"}
_OUTPUT_FIELDS = (
    "entry_id", "role", "status", "logic_version", "evidence_refs",
    "applicable_when", "observation", "recommendation", "confidence",
    "created_at", "expires_at",
)


class ApprovedLessonsError(ValueError):
    """The lesson store itself is malformed at a structural level."""


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _matches_scope(entry: Mapping[str, Any], *, level: str | int | None,
                   difficulty: str | None, logic_version: str | None) -> bool:
    scope = entry.get("applicable_when")
    if not isinstance(scope, Mapping):
        return False
    if level is not None and str(scope.get("level", "*")) not in {"*", str(level)}:
        return False
    if difficulty is not None and str(scope.get("difficulty", "*")) not in {"*", str(difficulty)}:
        return False
    entry_logic = str(entry.get("logic_version", "*"))
    if logic_version is not None and entry_logic not in {"*", str(logic_version)}:
        return False
    return True


def _normalise_entry(raw: Mapping[str, Any], *, line_no: int,
                     role: str, level: str | int | None,
                     difficulty: str | None, logic_version: str | None) -> tuple[dict[str, Any] | None, str | None]:
    entry_id = raw.get("entry_id")
    if not isinstance(entry_id, str) or not entry_id.strip():
        return None, f"line_{line_no}:missing_entry_id"
    if raw.get("role") != role:
        return None, None
    status = raw.get("status")
    if status not in _ALLOWED_STATUS:
        return None, f"{entry_id}:invalid_status"
    if status != "active":
        return None, None
    evidence = raw.get("evidence_refs")
    if not isinstance(evidence, list) or not evidence or any(not isinstance(item, str) or not item.strip() for item in evidence):
        return None, f"{entry_id}:missing_evidence"
    scope = raw.get("applicable_when", {})
    if not isinstance(scope, Mapping):
        return None, f"{entry_id}:invalid_scope"
    if not _matches_scope(raw, level=level, difficulty=difficulty, logic_version=logic_version):
        return None, None
    created_at = _parse_time(raw.get("created_at"))
    if created_at is None:
        return None, f"{entry_id}:invalid_created_at"
    expires_at_raw = raw.get("expires_at")
    if expires_at_raw not in (None, ""):
        expires_at = _parse_time(expires_at_raw)
        if expires_at is None:
            return None, f"{entry_id}:invalid_expires_at"
        if expires_at <= datetime.now(timezone.utc):
            return None, f"{entry_id}:expired"
        expires_at_value = expires_at.isoformat()
    else:
        expires_at_value = None
    try:
        confidence = float(raw.get("confidence"))
    except (TypeError, ValueError):
        return None, f"{entry_id}:invalid_confidence"
    if not math.isfinite(confidence) or not 0.0 <= confidence <= 1.0:
        return None, f"{entry_id}:invalid_confidence"
    observation = raw.get("observation")
    recommendation = raw.get("recommendation")
    if not isinstance(observation, str) or not observation.strip():
        return None, f"{entry_id}:missing_observation"
    if not isinstance(recommendation, str) or not recommendation.strip():
        return None, f"{entry_id}:missing_recommendation"
    clean_scope = {
        key: str(scope[key])
        for key in ("level", "difficulty", "failure_signature")
        if key in scope
    }
    entry = {
        "entry_id": entry_id.strip(),
        "role": role,
        "status": "active",
        "logic_version": str(raw.get("logic_version", "*")),
        "evidence_refs": sorted({str(item).strip() for item in evidence}),
        "applicable_when": clean_scope,
        "observation": observation.strip(),
        "recommendation": recommendation.strip(),
        "confidence": confidence,
        "created_at": created_at.isoformat(),
        "expires_at": expires_at_value,
    }
    return entry, None


def _empty_result(role: str, status: str, *, reason: str = "") -> dict[str, Any]:
    body = {"version": LESSON_VERSION, "role": role, "status": status, "entries": []}
    if reason:
        body["diagnostics"] = [reason]
    else:
        body["diagnostics"] = []
    body["snapshot_hash"] = "LES-" + _hash(body)[:16]
    return body


def load_approved_lessons(
    role: str,
    *,
    root: str | Path | None = None,
    level: str | int | None = None,
    difficulty: str | None = None,
    logic_version: str | None = None,
    enabled: bool = True,
    limit: int = 8,
) -> dict[str, Any]:
    """Load active, evidence-backed lessons for one role and one scope."""
    role = str(role).strip()
    if not role:
        raise ApprovedLessonsError("role is required")
    if not enabled:
        return _empty_result(role, "disabled")
    if int(limit) < 0:
        raise ApprovedLessonsError("limit must be non-negative")
    root_path = Path(root) if root is not None else Path(__file__).resolve().parents[2]
    path = root_path / "project-state" / "approved_lessons" / f"{role}.jsonl"
    if not path.is_file():
        result = _empty_result(role, "missing")
        result["source_path"] = str(path)
        return result

    diagnostics: list[str] = []
    entries: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ApprovedLessonsError(f"cannot read {path}: {exc}") from exc
    for line_no, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError:
            diagnostics.append(f"line_{line_no}:invalid_json")
            continue
        if not isinstance(raw, Mapping):
            diagnostics.append(f"line_{line_no}:not_object")
            continue
        entry, diagnostic = _normalise_entry(
            raw, line_no=line_no, role=role, level=level,
            difficulty=difficulty, logic_version=logic_version,
        )
        if diagnostic:
            diagnostics.append(diagnostic)
        if entry is not None:
            entries.append(entry)

    counts: dict[str, int] = {}
    for entry in entries:
        counts[entry["entry_id"]] = counts.get(entry["entry_id"], 0) + 1
    duplicate_ids = {entry_id for entry_id, count in counts.items() if count > 1}
    for entry_id in sorted(duplicate_ids):
        diagnostics.append(f"duplicate_entry_id:{entry_id}")
    entries = [entry for entry in entries if entry["entry_id"] not in duplicate_ids]
    entries.sort(key=lambda item: item["entry_id"])
    entries.sort(key=lambda item: item["created_at"], reverse=True)
    entries = entries[: int(limit)]
    snapshot_body = {
        "version": LESSON_VERSION,
        "role": role,
        "level": None if level is None else str(level),
        "difficulty": difficulty,
        "logic_version": logic_version,
        "entries": entries,
    }
    return {
        "version": LESSON_VERSION,
        "role": role,
        "status": "ok",
        "source_path": str(path),
        "entries": entries,
        "diagnostics": sorted(set(diagnostics)),
        "snapshot_hash": "LES-" + _hash(snapshot_body)[:16],
    }
