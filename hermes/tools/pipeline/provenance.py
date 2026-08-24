"""Decision provenance shared by Planner, request, RunStore, and receipt chain."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping


PROVENANCE_VERSION = "DECISION_PROVENANCE_V1"
_ALLOWED_SOURCES = {"llm_original", "script_fallback", "deterministic_planner", "disabled"}


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def stable_hash(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def probe_config_hash(probes: Mapping[str, Mapping[str, Any]]) -> str:
    normalized = []
    for slot, raw in sorted(probes.items(), key=lambda item: str(item[0])):
        if not isinstance(raw, Mapping):
            raise ValueError(f"probe {slot} must be an object")
        normalized.append({
            "slot": str(slot),
            "sd": int(raw["sd"]),
            "sc": int(raw["sc"]),
            "ratios": str(raw["ratios"]).replace(" ", ""),
            "of": float(raw["of"]),
        })
    return "CFG-" + stable_hash(normalized)[:16]


def _candidate_slot_map(metadata: Mapping[str, Any]) -> dict[str, str]:
    explicit = metadata.get("candidate_to_execution_slot")
    if isinstance(explicit, Mapping):
        return {str(key): str(value) for key, value in explicit.items()}
    selected = metadata.get("selected_candidate_ids", [])
    if not isinstance(selected, list):
        return {}
    return {str(candidate): f"T{index}" for index, candidate in enumerate(selected, start=1)}


def make_decision_id(provenance: Mapping[str, Any]) -> str:
    body = {
        key: provenance.get(key)
        for key in (
            "level", "round", "decision_source", "context_hash", "snapshot_hash",
            "catalog_id", "manifest_version", "manifest_hash", "prompt_version",
            "memory_snapshot_hash", "selected_candidate_ids",
            "candidate_to_execution_slot", "probe_config_hash",
        )
    }
    return "DEC-" + stable_hash(body)[:20]


def build_decision_provenance(
    *, level: str | int,
    round_num: int,
    probes: Mapping[str, Mapping[str, Any]],
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Normalize AI or deterministic metadata into an immutable decision record."""
    metadata = dict(metadata or {})
    source = str(metadata.get("decision_source") or metadata.get("status") or "deterministic_planner")
    if source not in _ALLOWED_SOURCES:
        source = "deterministic_planner"
    selected = metadata.get("selected_candidate_ids", [])
    if not isinstance(selected, list):
        selected = []
    selected = [str(item) for item in selected]
    mapping = _candidate_slot_map({**metadata, "selected_candidate_ids": selected})
    result: dict[str, Any] = {
        "version": PROVENANCE_VERSION,
        "level": str(level),
        "round": int(round_num),
        "decision_source": source,
        "designer": str(metadata.get("designer") or ("llm" if source == "llm_original" else "script")),
        "catalog_id": metadata.get("catalog_id"),
        "snapshot_hash": metadata.get("snapshot_hash"),
        "context_hash": metadata.get("context_hash"),
        "memory_snapshot_hash": metadata.get("memory_snapshot_hash"),
        "manifest_version": metadata.get("manifest_version"),
        "manifest_hash": metadata.get("manifest_hash"),
        "prompt_version": metadata.get("prompt_version", "probe-design-v3"),
        "selected_candidate_ids": selected,
        "candidate_to_execution_slot": mapping,
        "probe_config_hash": probe_config_hash(probes),
        "actual_llm_calls": int(metadata.get("actual_llm_calls", 0) or 0),
        "fallback_reason": list(metadata.get("fallback_reason", metadata.get("errors", [])) or []),
        "model_selection": metadata.get("model_selection", "current"),
        "resolved_model": metadata.get("resolved_model"),
    }
    result["decision_id"] = make_decision_id(result)
    return result


def validate_decision_provenance(
    provenance: Mapping[str, Any],
    *,
    level: str | int,
    round_num: int,
    probes: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Fail closed if provenance no longer describes the execution probes."""
    if not isinstance(provenance, Mapping):
        raise ValueError("decision provenance must be an object")
    if provenance.get("version") != PROVENANCE_VERSION:
        raise ValueError("unsupported decision provenance version")
    if str(provenance.get("level")) != str(level) or int(provenance.get("round", -1)) != int(round_num):
        raise ValueError("decision provenance level/round mismatch")
    source = str(provenance.get("decision_source", ""))
    if source not in _ALLOWED_SOURCES:
        raise ValueError(f"unknown decision source: {source}")
    expected_config_hash = probe_config_hash(probes)
    if provenance.get("probe_config_hash") != expected_config_hash:
        raise ValueError("decision probe config hash mismatch")
    selected = provenance.get("selected_candidate_ids", [])
    mapping = provenance.get("candidate_to_execution_slot", {})
    if not isinstance(selected, list) or len(selected) != len(set(selected)):
        raise ValueError("decision candidate IDs are not unique")
    if not isinstance(mapping, Mapping):
        raise ValueError("candidate_to_execution_slot must be an object")
    if set(map(str, selected)) != set(map(str, mapping.keys())):
        raise ValueError("candidate-to-slot mapping does not match selected candidates")
    actual_calls = int(provenance.get("actual_llm_calls", 0) or 0)
    if actual_calls < 0 or actual_calls > 1:
        raise ValueError("actual_llm_calls must be 0 or 1")
    expected_id = make_decision_id(provenance)
    if provenance.get("decision_id") != expected_id:
        raise ValueError("decision_id does not match provenance payload")
    return dict(provenance)
