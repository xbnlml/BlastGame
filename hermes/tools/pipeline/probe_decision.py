"""Deterministic CandidateCatalog/ContextV3/ProbeDecision contracts."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from typing import Any, Mapping, Sequence


class DecisionInvalid(ValueError):
    """A decision is not bound to the current catalog/context."""


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _config(record: Mapping[str, Any]) -> dict[str, Any]:
    required = ("sd", "sc", "ratios", "of")
    if any(key not in record for key in required):
        raise DecisionInvalid(f"candidate config missing {required}")
    return {
        "sd": int(record["sd"]),
        "sc": int(record["sc"]),
        "ratios": str(record["ratios"]),
        "of": float(record["of"]),
    }


def _config_identity(config: Mapping[str, Any]) -> str:
    return _hash({
        "sd": int(config["sd"]), "sc": int(config["sc"]),
        "ratios": str(config["ratios"]).replace(" ", ""), "of": float(config["of"]),
    })


def _evidence_id(record: Mapping[str, Any], config_id: str) -> str:
    raw = record.get("evidence_id") or record.get("id") or _hash({"config": config_id, "record": dict(record)})[:16]
    return "E" + str(raw).replace(" ", "_")[:32]


def _deal_fingerprint(record: Mapping[str, Any], config_id: str) -> str:
    # Real Unity records carry the official deal fingerprint. Catalogs built
    # before execution may only have a canonical config identity; that value is
    # explicitly marked as a catalog identity and must be remapped by P1 before
    # Unity can run it.
    return str(record.get("deal_fingerprint") or "catalog-config-" + config_id)


def build_candidate_catalog(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """Compile all legal records without ranking or top-N truncation."""
    level = str(snapshot.get("level", ""))
    board = str(snapshot.get("board_fingerprint", ""))
    logic = str(snapshot.get("logic_version", ""))
    if not level or not board or not logic:
        raise DecisionInvalid("snapshot identity is incomplete")
    records_by_source: dict[str, list[Mapping[str, Any]]] = {}
    for source in ("verified", "phase2", "phase1", "generated"):
        raw = snapshot.get(source, [])
        if not isinstance(raw, list):
            raise DecisionInvalid(f"{source} must be list")
        records_by_source[source] = raw
    exact_verified: set[tuple[str, str]] = set()
    verified_config_ids: set[str] = set()
    for record in records_by_source["verified"]:
        cfg = _config(record)
        config_id = _config_identity(cfg)
        exact_verified.add((_deal_fingerprint(record, config_id), config_id))
        verified_config_ids.add(config_id)

    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    for source in ("phase1", "phase2", "verified", "generated"):
        for record in records_by_source[source]:
            cfg = _config(record)
            config_id = _config_identity(cfg)
            deal_fp = _deal_fingerprint(record, config_id)
            candidate_id = "C{}-{}".format(level, _hash({"board": board, "logic": logic, "deal": deal_fp, "config": config_id})[:12])
            if candidate_id in seen:
                continue
            seen.add(candidate_id)
            # A generated/catalog record may not carry Unity's official deal
            # fingerprint yet.  The four-tuple itself is still enough to block
            # an undeclared retest of a verified configuration.
            exact = (deal_fp, config_id) in exact_verified or config_id in verified_config_ids
            candidates.append({
                "candidate_id": candidate_id,
                "level": level,
                "config": cfg,
                "deal_fingerprint": deal_fp,
                "fingerprint_algorithm": "official-record" if record.get("deal_fingerprint") else "catalog-config-v1",
                "origins": [source],
                "evidence_ids": [_evidence_id(record, config_id)],
                "retest_allowed": bool(record.get("retest_allowed", False)),
                "exact_verified": exact,
                "total_games": int(record.get("totalGames", record.get("total_games", 0)) or 0),
                "wr": record.get("wr", record.get("win_rate")),
            })
    catalog_body = {
        "version": "CANDIDATE_CATALOG_V1", "level": level,
        "board_fingerprint": board, "logic_version": logic,
        "candidates": candidates,
    }
    catalog = dict(catalog_body)
    catalog["catalog_id"] = "CAT-" + _hash(catalog_body)[:16]
    catalog["snapshot_hash"] = str(snapshot.get("snapshot_hash") or "SNAP-" + _hash({k: snapshot.get(k) for k in ("level", "board_fingerprint", "logic_version", "verified", "phase2", "phase1")})[:16])
    return catalog


def build_context_v3(
    snapshot: Mapping[str, Any],
    catalog: Mapping[str, Any],
    *,
    prompt_version: str = "probe-design-v3",
    context_metadata: Mapping[str, Any] | None = None,
    approved_lessons: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a stable, complete context; source bands remain separate."""
    if catalog.get("snapshot_hash") != (snapshot.get("snapshot_hash") or catalog.get("snapshot_hash")):
        raise DecisionInvalid("catalog snapshot binding mismatch")
    context = {
        "version": "PROBE_CONTEXT_V3",
        "run_id": snapshot.get("run_id"), "attempt_id": snapshot.get("attempt_id"),
        "level": str(snapshot["level"]), "board_fingerprint": snapshot["board_fingerprint"],
        "logic_version": snapshot["logic_version"], "policy_id": snapshot.get("policy_id", "rules.json"),
        "targets": snapshot.get("targets"), "best_combo": snapshot.get("best_combo"),
        "gaps": snapshot.get("gaps", []), "judge_reasons": snapshot.get("judge_reasons", []),
        "records": {
            "verified": snapshot.get("verified", []),
            "phase2": snapshot.get("phase2", []),
            "phase1": snapshot.get("phase1", []),
        },
        "attempt_history": snapshot.get("attempt_history", []),
        "catalog_id": catalog["catalog_id"], "snapshot_hash": catalog["snapshot_hash"],
        "prompt_version": prompt_version,
    }
    if context_metadata:
        context["context_metadata"] = dict(context_metadata)
    if approved_lessons is not None:
        context["approved_lessons"] = [dict(item) for item in approved_lessons]
    context["context_hash"] = "CTX-" + _hash(context)[:16]
    return context


def freeze_script_baseline(context: Mapping[str, Any], catalog: Mapping[str, Any]) -> dict[str, Any]:
    """Return a deterministic control decision from the same catalog.

    This is a control arm/fallback, not information shown to Luna.
    """
    available = [c for c in catalog.get("candidates", []) if not c.get("exact_verified") or c.get("retest_allowed")]
    available.sort(key=lambda c: (c.get("exact_verified", False), c["candidate_id"]))
    if len(available) < 5:
        raise DecisionInvalid("candidate catalog has fewer than five legal control candidates")
    selected = []
    used_deals = set()
    used_configs = set()
    for candidate in available:
        if candidate["deal_fingerprint"] in used_deals:
            continue
        config_id = _config_identity(candidate["config"])
        if config_id in used_configs:
            continue
        selected.append({
            "candidate_id": candidate["candidate_id"], "objective_id": "SCRIPT_CONTROL",
            "role": "exploration", "evidence_ids": list(candidate.get("evidence_ids", [])),
            "hypothesis": "frozen deterministic control",
        })
        used_deals.add(candidate["deal_fingerprint"])
        used_configs.add(config_id)
        if len(selected) == 5:
            break
    if len(selected) != 5:
        raise DecisionInvalid("catalog cannot provide five distinct control deals")
    return {
        "version": "PROBE_DECISION_V3", "designer": "frozen_script",
        "level": str(context["level"]), "snapshot_hash": context["snapshot_hash"],
        "catalog_id": catalog["catalog_id"], "revision": 1, "selected": selected,
    }


def validate_probe_decision(decision: Mapping[str, Any], catalog: Mapping[str, Any], context: Mapping[str, Any]) -> dict[str, Any]:
    """Accept only five current candidate IDs with valid evidence and deals."""
    if decision.get("snapshot_hash") != context.get("snapshot_hash"):
        raise DecisionInvalid("decision snapshot is stale")
    if decision.get("catalog_id") != catalog.get("catalog_id"):
        raise DecisionInvalid("decision catalog is stale")
    selected = decision.get("selected")
    if not isinstance(selected, list) or len(selected) != 5:
        raise DecisionInvalid("decision must select exactly five P slots")
    by_id = {str(c.get("candidate_id")): c for c in catalog.get("candidates", [])}
    if len(by_id) != len(catalog.get("candidates", [])):
        raise DecisionInvalid("catalog candidate IDs are not unique")
    allowed_retests = set(context.get("declared_retest_candidate_ids", []))
    seen_ids: set[str] = set()
    seen_deals: set[str] = set()
    seen_configs: set[str] = set()
    validated = []
    for index, item in enumerate(selected, start=1):
        if not isinstance(item, Mapping) or not item.get("candidate_id"):
            raise DecisionInvalid(f"P{index} candidate_id missing")
        cid = str(item["candidate_id"])
        if cid in seen_ids or cid not in by_id:
            raise DecisionInvalid(f"P{index} candidate is unknown or duplicated: {cid}")
        candidate = by_id[cid]
        if candidate.get("exact_verified") and not candidate.get("retest_allowed") and cid not in allowed_retests:
            raise DecisionInvalid(f"P{index} undeclared exact retest: {cid}")
        deal = str(candidate.get("deal_fingerprint"))
        if deal in seen_deals:
            raise DecisionInvalid(f"P{index} deal fingerprint duplicated: {deal}")
        config_id = _config_identity(candidate["config"])
        if config_id in seen_configs:
            raise DecisionInvalid(f"P{index} four-tuple duplicated: {config_id}")
        evidence = item.get("evidence_ids")
        if not isinstance(evidence, list) or not set(evidence).issubset(set(candidate.get("evidence_ids", []))):
            raise DecisionInvalid(f"P{index} evidence is not bound to candidate")
        seen_ids.add(cid); seen_deals.add(deal); seen_configs.add(config_id)
        validated.append({
            "execution_slot": f"P{index}", "candidate_id": cid,
            "objective_id": item.get("objective_id", "UNSPECIFIED"),
            "role": item.get("role", "exploration"),
            "evidence_ids": list(evidence), "hypothesis": str(item.get("hypothesis", "")),
            "deal_fingerprint": deal,
        })
    result = dict(decision)
    result["selected"] = validated
    result["validated"] = True
    return result



