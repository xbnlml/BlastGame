"""Role contracts for scoped BlastGame modules.

This module validates machine-readable role manifests and approved-lesson
contracts.  It deliberately does not load Markdown skills or legacy memory
files; those remain outside the production decision path.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping


class RoleContractError(ValueError):
    """A role manifest is missing, malformed, or internally inconsistent."""


ROLE_NAMES = ("orchestrator", "planner", "warden", "runner", "judge", "curator")
_MODES = {"deterministic", "llm_advisor", "reviewer"}
_FAILURE_POLICIES = {"fail_closed", "script_fallback", "proposal_only"}
_MEMORY_POLICIES = {"none", "review_only", "approved_lessons_only"}
_ROLE_RE = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _manifest_path(role: str, root: Path) -> Path:
    return root / "agents" / role / "manifest.json"


def _require_string(data: Mapping[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise RoleContractError(f"{key} must be a non-empty string")
    return value.strip()


def _require_unique_strings(data: Mapping[str, Any], key: str) -> list[str]:
    value = data.get(key)
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        raise RoleContractError(f"{key} must be a list of non-empty strings")
    result = [item.strip() for item in value]
    if len(result) != len(set(result)):
        raise RoleContractError(f"{key} contains duplicates")
    return result


def load_role_contract(role: str, *, root: str | Path | None = None) -> dict[str, Any]:
    """Load and validate one role manifest, returning its stable hash."""
    role = str(role).strip()
    if not _ROLE_RE.fullmatch(role) or role not in ROLE_NAMES:
        raise RoleContractError(f"unknown role: {role!r}")
    root_path = Path(root) if root is not None else project_root()
    path = _manifest_path(role, root_path)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RoleContractError(f"manifest missing: {path}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise RoleContractError(f"manifest invalid: {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise RoleContractError("manifest root must be an object")

    schema_version = raw.get("schema_version")
    if schema_version != 1:
        raise RoleContractError(f"unsupported schema_version: {schema_version!r}")
    if raw.get("role") != role:
        raise RoleContractError(f"manifest role mismatch: expected {role!r}")
    version = _require_string(raw, "version")
    mode = _require_string(raw, "mode")
    if mode not in _MODES:
        raise RoleContractError(f"unsupported mode: {mode}")
    input_allowlist = _require_unique_strings(raw, "input_allowlist")
    forbidden = _require_unique_strings(raw, "forbidden")
    output_schema = _require_string(raw, "output_schema")
    failure_policy = _require_string(raw, "failure_policy")
    memory_policy = _require_string(raw, "memory_policy")
    policy_refs = _require_unique_strings(raw, "policy_refs")
    if failure_policy not in _FAILURE_POLICIES:
        raise RoleContractError(f"unsupported failure_policy: {failure_policy}")
    if memory_policy not in _MEMORY_POLICIES:
        raise RoleContractError(f"unsupported memory_policy: {memory_policy}")
    if mode == "deterministic" and memory_policy == "approved_lessons_only":
        raise RoleContractError("deterministic roles cannot consume mutable approved lessons in production")
    if mode == "llm_advisor" and failure_policy != "script_fallback":
        raise RoleContractError("llm_advisor must use script_fallback")
    if set(input_allowlist) & set(forbidden):
        raise RoleContractError("input_allowlist and forbidden overlap")

    normalized = {
        "schema_version": 1,
        "role": role,
        "version": version,
        "mode": mode,
        "input_allowlist": input_allowlist,
        "output_schema": output_schema,
        "forbidden": forbidden,
        "failure_policy": failure_policy,
        "memory_policy": memory_policy,
        "policy_refs": policy_refs,
    }
    result = dict(normalized)
    result["manifest_path"] = str(path)
    result["manifest_hash"] = "MAN-" + _hash_text(_canonical(normalized))[:16]
    return result


def load_all_role_contracts(*, root: str | Path | None = None) -> dict[str, dict[str, Any]]:
    return {role: load_role_contract(role, root=root) for role in ROLE_NAMES}


def approved_lessons_snapshot(role: str, *, root: str | Path | None = None) -> dict[str, Any]:
    """Return a stable snapshot identity without loading legacy memory.md."""
    role = str(role).strip()
    if role not in ROLE_NAMES:
        raise RoleContractError(f"unknown role: {role!r}")
    root_path = Path(root) if root is not None else project_root()
    path = root_path / "project-state" / "approved_lessons" / f"{role}.jsonl"
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        raw = b""
    except OSError as exc:
        raise RoleContractError(f"cannot read approved lessons: {path}: {exc}") from exc
    return {
        "path": str(path),
        "exists": path.is_file(),
        "entry_hash": "LES-" + hashlib.sha256(raw).hexdigest()[:16],
    }
