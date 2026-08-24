#!/usr/bin/env python3
"""AI probe selector for the existing BlastGame tuning loop.

The deterministic pipeline still owns candidate generation, validation, asset
writes, Unity execution and judgment.  Hermes only selects five candidate IDs
from the current catalog and explains the experiment hypotheses.
"""

from __future__ import annotations

import json
import contextlib
import io
import os
import sys
import time
from pathlib import Path
from typing import Any, Mapping

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from tools import llm_client
from tools import probe_input_packager as packager
from tools.data import pool
from tools.data.adapters import excel_target as excel_targets
from tools.pipeline.probe_decision import (
    DecisionInvalid,
    build_candidate_catalog,
    build_context_v3,
    validate_probe_decision,
)
from tools.pipeline.approved_lessons import load_approved_lessons
from tools.pipeline.provenance import build_decision_provenance
from tools.pipeline.role_contract import load_role_contract
from tools.design_probes import design as script_design

TOOLS_DIR = Path(__file__).resolve().parent
PROJECT_STATE = TOOLS_DIR.parent / "project-state"
PROMPT_TMPL = TOOLS_DIR / "prompts" / "probe_design_v1.txt"
LESSONS_PATH = TOOLS_DIR / "probe_blacklist.json"
AI_METRICS_PATH = PROJECT_STATE / "ai_probe_metrics.jsonl"


# ---------------------------------------------------------------------------
# Deterministic context and candidate preparation


def _load_lessons(lv: str) -> dict[str, Any]:
    try:
        data = json.loads(LESSONS_PATH.read_text(encoding="utf-8"))
        return data.get(str(lv), {}) if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _load_previous_attempt(lv: str) -> list[dict[str, Any]]:
    """Load this level's full probe history from ai_probe_metrics.jsonl.

    The round report is overwritten every round, so it cannot serve as
    cross-round memory.  Metrics JSONL accumulates every decision; we read
    it back here so the LLM can see what was tried in prior rounds and with
    what result (root cause: LLM was re-selecting identical candidates
    round after round because it could not see its own history).
    """
    history: list[dict[str, Any]] = []
    try:
        if not AI_METRICS_PATH.exists():
            return history
        with AI_METRICS_PATH.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if str(rec.get("level")) != str(lv):
                    continue
                history.append({
                    "round": rec.get("round"),
                    "ts": rec.get("ts"),
                    "designer": rec.get("designer"),
                    "judge_result": rec.get("judge_result") or "",
                    "actual_wrs": rec.get("actual_wrs") or {},
                    "selected_candidate_ids": rec.get("selected_candidate_ids") or [],
                })
    except OSError:
        return []
    # 每轮取最新一条（probe 轮与验证轮可能同 round 两条记录），按 round 升序
    by_round: dict[int, dict[str, Any]] = {}
    for rec in history:
        rnd = rec.get("round")
        if not isinstance(rnd, int):
            continue
        by_round[rnd] = rec  # 后写覆盖，保留最新
    return [by_round[r] for r in sorted(by_round)][-8:]


def _record_metric(entry: Mapping[str, Any]) -> None:
    """Append a compact decision metric; never persist credentials or raw CoT."""
    try:
        PROJECT_STATE.mkdir(parents=True, exist_ok=True)
        with AI_METRICS_PATH.open("a", encoding="utf-8") as fh:
            payload = {
                "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "pipeline": "probe_selector",
                "provider_selection": llm_client.CURRENT_PROVIDER,
                "model_selection": llm_client.CURRENT_MODEL,
                "reasoning": llm_client.REASONING_EFFORT,
                **dict(entry),
            }
            fh.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
    except OSError:
        # Metrics must not block tuning. The round report remains the visible
        # business artifact and will still show the selected probes/WRs.
        pass


def _generated_records(script_ref: Any) -> list[dict[str, Any]]:
    """Turn the existing deterministic designer output into catalog candidates."""
    if not isinstance(script_ref, dict):
        return []
    records = []
    for index, key in enumerate(sorted(script_ref), start=1):
        if not str(key).startswith("T") or not isinstance(script_ref[key], Mapping):
            continue
        probe = script_ref[key]
        required = ("sd", "sc", "ratios", "of")
        if any(field not in probe for field in required):
            continue
        records.append({
            "id": f"script-candidate-{index}",
            "source": "generated",
            "sd": probe["sd"],
            "sc": probe["sc"],
            "ratios": probe["ratios"],
            "of": probe["of"],
            "totalGames": 0,
            "wr": None,
            "retest_allowed": False,
        })
    return records


def _build_snapshot(lv: str, round_num: int, script_ref: Any) -> dict[str, Any] | None:
    """Build the single-level, source-separated context used by the selector."""
    info = excel_targets.get_target(lv)
    if not info:
        return None

    from tools.asset_patcher import level_sig
    from tools.get_level_pool import LOGIC_VERSION_SINCE
    from tools.judge_level import find_best_combo

    board_fingerprint = level_sig(int(lv))
    if not board_fingerprint:
        return None

    records = pool.dedup_records(pool.get_all_records(lv))
    reliable = pool.filter_verified(records)
    source_rows = {
        "verified": reliable,
        "phase2": [r for r in records if r.get("source") == "phase2"],
        "phase1": [r for r in records if r.get("source") == "phase1"],
    }

    best_combo = None
    gaps: list[float] = []
    judge_reasons: list[str] = []
    try:
        combo, verdict, reasons = find_best_combo(records, info["diff"], info["tiers"])
        judge_reasons = list(reasons or [])
        if combo:
            best_combo = combo
            wrs = [float(combo[f"T{i}"]) for i in range(1, 6)]
            pairs = [(0, 2), (2, 4)] if info["diff"] == "normal" else [(i, i + 1) for i in range(4)]
            gaps = [round(wrs[i] - wrs[j], 2) for i, j in pairs]
    except Exception as exc:
        judge_reasons = [f"deterministic context unavailable: {type(exc).__name__}"]

    return {
        "version": "PROBE_SNAPSHOT_V1",
        "level": str(lv),
        "round": int(round_num),
        "board_fingerprint": str(board_fingerprint),
        "logic_version": LOGIC_VERSION_SINCE,
        "policy_id": "rules.json",
        "targets": list(info["tiers"]),
        "difficulty": info["diff"],
        "best_combo": best_combo,
        "gaps": gaps,
        "judge_reasons": judge_reasons[:10],
        "verified": source_rows["verified"],
        "phase2": source_rows["phase2"],
        "phase1": source_rows["phase1"],
        "generated": _generated_records(script_ref),
        "attempt_history": _load_previous_attempt(lv),
    }


def candidates_raw(catalog: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Extract candidate projection used in both prompt builders."""
    return [
        {
            "candidate_id": item["candidate_id"],
            "config": item["config"],
            "origins": item.get("origins", []),
            "evidence_ids": item.get("evidence_ids", []),
            "exact_verified": item.get("exact_verified", False),
            "total_games": item.get("total_games", 0),
            "wr": item.get("wr"),
        }
        for item in catalog.get("candidates", [])
    ]


def _mark_tried(candidates: list[dict[str, Any]],
                attempt_history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Annotate candidates that were selected in a previous round.

    Prevents the LLM from re-selecting the same configs round after round
    (observed for L92/L143: identical candidate sets for many rounds).
    """
    tried: dict[str, int] = {}
    for rec in attempt_history:
        for cid in rec.get("selected_candidate_ids") or []:
            rnd = rec.get("round")
            if isinstance(rnd, int):
                tried.setdefault(cid, rnd)  # first round wins (oldest)
    out = []
    for item in candidates:
        item = dict(item)
        if item["candidate_id"] in tried:
            item["previously_tried_round"] = tried[item["candidate_id"]]
        else:
            item["previously_tried_round"] = None
        out.append(item)
    return out


def _candidate_prompt(context: Mapping[str, Any], catalog: Mapping[str, Any], packed: Mapping[str, Any], lessons: Any) -> str:
    template = PROMPT_TMPL.read_text(encoding="utf-8")
    attempt_history = context.get("attempt_history", [])
    state = {
        "level": context["level"],
        "round": context.get("round"),
        "targets": context.get("targets"),
        "difficulty": context.get("difficulty"),
        "best_combo": context.get("best_combo"),
        "gaps": context.get("gaps"),
        "judge_reasons": context.get("judge_reasons"),
        "snapshot_hash": context["snapshot_hash"],
        "catalog_id": catalog["catalog_id"],
        "context_metadata": context.get("context_metadata", {}),
        "attempt_history": attempt_history,
    }
    tried_by_round = _mark_tried(candidates_raw(catalog), attempt_history)
    candidates = tried_by_round
    return (template
            .replace("{state_snapshot}", json.dumps(state, ensure_ascii=False, indent=1))
            .replace("{aggregated_data}", json.dumps({"packed": packed, "candidates": candidates}, ensure_ascii=False))
            .replace("{lessons}", json.dumps(lessons or {}, ensure_ascii=False)[:2000])
            .replace("{script_reference}", json.dumps({"generated_candidate_ids": [c["candidate_id"] for c in candidates_raw(catalog) if "generated" in c["origins"]]}, ensure_ascii=False)))


def _candidate_delta_prompt(
    context: Mapping[str, Any], catalog: Mapping[str, Any], packed: Mapping[str, Any], lessons: Any,
) -> str:
    """Build a compact turn for the shared Planner session.

    The first turn carries the full role contract. Later turns carry only the
    current level/round envelope, current evidence, candidate catalog and
    relevant lessons; prior turns remain available as cross-level experience.
    """
    state = {
        "current_level": context["level"],
        "current_round": context.get("round"),
        "difficulty": context.get("difficulty"),
        "targets": context.get("targets"),
        "best_combo": context.get("best_combo"),
        "gaps": context.get("gaps"),
        "judge_reasons": context.get("judge_reasons"),
        "snapshot_hash": context["snapshot_hash"],
        "catalog_id": catalog["catalog_id"],
        "context_metadata": context.get("context_metadata", {}),
        "attempt_history": context.get("attempt_history", []),
    }
    candidates = _mark_tried(candidates_raw(catalog), context.get("attempt_history", []))
    payload = {
        "current_state": state,
        "verified_and_phase_data": packed,
        "candidates": candidates,
        "relevant_lessons": lessons or {},
    }
    return (
        "SHARED CAMPAIGN PLANNER TURN.\n"
        "The current_state block is authoritative for this level and round. "
        "Use prior turns only for transferable hypotheses, never as current "
        "evidence. Select exactly five different candidate_id values from the "
        "current candidates list; do not invent IDs or configurations. Preserve "
        "evidence_ids. Return the same JSON schema as the initial Planner turn.\n"
        + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    )


def _normalise_decision(response: Any, context: Mapping[str, Any], catalog: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(response, Mapping):
        raise DecisionInvalid("Hermes response must be an object")
    selected = response.get("selected")
    if not isinstance(selected, list):
        raise DecisionInvalid("response.selected must be a list")
    decision = {
        "version": "PROBE_DECISION_V3",
        "designer": "llm",
        "level": str(context["level"]),
        "snapshot_hash": context["snapshot_hash"],
        "catalog_id": catalog["catalog_id"],
        "revision": 1,
        "selected": selected,
        "design_note": str(response.get("design_note", "")),
    }
    return validate_probe_decision(decision, catalog, context)


def _decision_to_probes(decision: Mapping[str, Any], catalog: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    by_id = {str(item["candidate_id"]): item for item in catalog.get("candidates", [])}
    probes: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(decision["selected"], start=1):
        candidate = by_id[str(item["candidate_id"])]
        probes[f"T{index}"] = dict(candidate["config"])
    if set(probes) != {"T1", "T2", "T3", "T4", "T5"}:
        raise DecisionInvalid("validated decision did not produce T1-T5 execution slots")
    return probes


def _quiet_script_design(lv: str) -> Any:
    """Call the legacy designer without leaking human diagnostics into stdout."""
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return script_design(lv)


def _fallback(lv: str, round_num: int, errors: list[str], status: str = "script_fallback") -> dict[str, Any]:
    fallback = _quiet_script_design(lv)
    result = {
        "status": status,
        "probes": fallback if isinstance(fallback, dict) else None,
        "designer": "script",
        "selected_candidate_ids": [],
        "snapshot_hash": None,
        "catalog_id": None,
        "borrowed": False,
        "errors": errors,
    }
    _record_metric({
        "level": str(lv), "round": int(round_num), "status": status,
        "designer": "script", "selected_candidate_ids": [], "errors": errors[:5],
    })
    return result


def _attach_provenance(
    result: dict[str, Any],
    *,
    lv: str,
    round_num: int,
    probes: Mapping[str, Mapping[str, Any]] | None,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    provenance = build_decision_provenance(
        level=lv,
        round_num=round_num,
        probes=probes or {},
        metadata={
            "status": result.get("status"),
            "designer": result.get("designer"),
            "selected_candidate_ids": result.get("selected_candidate_ids", []),
            "catalog_id": result.get("catalog_id"),
            "snapshot_hash": result.get("snapshot_hash"),
            "context_hash": result.get("context_hash"),
            "errors": result.get("errors", []),
            **dict(metadata or {}),
        },
    )
    result["decision_id"] = provenance["decision_id"]
    result["decision_provenance"] = provenance
    if isinstance(result.get("decision"), dict):
        result["decision"]["decision_id"] = provenance["decision_id"]
        result["decision"]["candidate_to_execution_slot"] = provenance["candidate_to_execution_slot"]
    return result


# ---------------------------------------------------------------------------
# Public entry used by auto_loop


def design_probes_llm(lv: str | int, round_num: int = 1, advisor_mode: str = "llm") -> dict[str, Any]:
    """Select five current candidate IDs; fail open to deterministic design."""
    lv = str(lv)
    cfg = llm_client._load_advisor_cfg()
    if not cfg.get("enabled", False) or cfg.get("mode") == "script":
        _record_metric({
            "level": lv, "round": int(round_num), "status": "disabled",
            "designer": "script", "selected_candidate_ids": [],
            "errors": ["AI disabled by llm_advisor.json"],
        })
        return {
            "status": "disabled", "probes": None, "designer": "script",
            "selected_candidate_ids": [], "snapshot_hash": None,
            "catalog_id": None, "borrowed": False,
            "errors": ["AI disabled by llm_advisor.json"],
        }

    script_ref = None
    try:
        contract = load_role_contract("planner")
        script_ref = _quiet_script_design(lv)
        snapshot = _build_snapshot(lv, round_num, script_ref)
        packed = packager.pack_level(lv, round_num=round_num)
        if snapshot is None or packed is None:
            return _fallback(lv, round_num, ["missing asset snapshot or pool data"])
        catalog = build_candidate_catalog(snapshot)
        lesson_cfg = cfg.get("approved_lessons", {})
        lessons_enabled = isinstance(lesson_cfg, Mapping) and bool(lesson_cfg.get("enabled", False))
        approved = load_approved_lessons(
            "planner",
            root=PROJECT_STATE.parent,
            level=lv,
            difficulty=snapshot.get("difficulty"),
            logic_version=snapshot.get("logic_version"),
            enabled=lessons_enabled,
            limit=int(lesson_cfg.get("max_entries", 8)) if isinstance(lesson_cfg, Mapping) else 8,
        )
        context = build_context_v3(
            snapshot,
            catalog,
            context_metadata={
                "role": "planner",
                "manifest_version": contract["version"],
                "manifest_hash": contract["manifest_hash"],
                "memory_snapshot_hash": approved["snapshot_hash"],
                "approved_lessons_status": approved["status"],
            },
            approved_lessons=approved["entries"] if lessons_enabled else None,
        )
        legacy_lessons = _load_lessons(lv)
        lessons = legacy_lessons
        if lessons_enabled:
            lessons = {
                "probe_blacklist": legacy_lessons,
                "approved_planner_lessons": approved["entries"],
            }
    except Exception as exc:
        return _fallback(lv, round_num, [f"context build failed: {type(exc).__name__}"])

    prompt = (
        _candidate_delta_prompt(context, catalog, packed, lessons)
        if llm_client.session_active()
        else _candidate_prompt(context, catalog, packed, lessons)
    )
    errors: list[str] = []
    actual_llm_calls = 1
    response = llm_client.ask(
        "你是资深休闲游戏难度调优专家，只能从候选目录选择候选 ID。",
        prompt,
        max_tokens=800,
        json_mode=True,
        agent="probe",
    )
    if response is not None:
        try:
            decision = _normalise_decision(response, context, catalog)
            probes = _decision_to_probes(decision, catalog)
            selected_ids = [item["candidate_id"] for item in decision["selected"]]
            result = {
                "status": "llm_original",
                "probes": probes,
                "designer": "llm",
                "selected_candidate_ids": selected_ids,
                "snapshot_hash": context["snapshot_hash"],
                "context_hash": context["context_hash"],
                "catalog_id": catalog["catalog_id"],
                "decision": decision,
                "borrowed": False,
                "actual_llm_calls": actual_llm_calls,
                "errors": [],
            }
            result = _attach_provenance(
                result,
                lv=lv,
                round_num=round_num,
                probes=probes,
                metadata={
                    "decision_source": "llm_original",
                    "actual_llm_calls": actual_llm_calls,
                    "manifest_version": contract["version"],
                    "manifest_hash": contract["manifest_hash"],
                    "memory_snapshot_hash": approved["snapshot_hash"],
                    "prompt_version": context["prompt_version"],
                    "model_selection": llm_client.CURRENT_MODEL,
                },
            )
            llm_client.write_advisor("probe", lv, round_num, {
                "status": result["status"],
                "decision_id": result["decision_id"],
                "candidate_ids": selected_ids,
                "design_note": decision.get("design_note", ""),
                "hypotheses": [item.get("hypothesis", "") for item in decision["selected"]],
            })
            _record_metric({
                "level": lv, "round": int(round_num), "status": result["status"],
                "designer": "llm", "selected_candidate_ids": selected_ids,
                "snapshot_hash": context["snapshot_hash"],
                "context_hash": context["context_hash"],
                "catalog_id": catalog["catalog_id"],
                "decision_id": result["decision_id"],
                "actual_llm_calls": actual_llm_calls,
                "manifest_version": contract["version"],
                "memory_snapshot_hash": approved["snapshot_hash"],
            })
            return result
        except DecisionInvalid as exc:
            errors.append(str(exc))
    else:
        errors.append("Hermes unavailable/failed")

    fallback = _fallback(lv, round_num, errors[:5])
    fallback["snapshot_hash"] = context.get("snapshot_hash")
    fallback["context_hash"] = context.get("context_hash")
    fallback["catalog_id"] = catalog.get("catalog_id")
    fallback["actual_llm_calls"] = actual_llm_calls
    return _attach_provenance(
        fallback,
        lv=lv,
        round_num=round_num,
        probes=fallback.get("probes") if isinstance(fallback.get("probes"), Mapping) else {},
        metadata={
            "decision_source": "script_fallback",
            "actual_llm_calls": actual_llm_calls,
            "manifest_version": contract["version"],
            "manifest_hash": contract["manifest_hash"],
            "memory_snapshot_hash": approved["snapshot_hash"],
            "prompt_version": context["prompt_version"],
            "model_selection": llm_client.CURRENT_MODEL,
        },
    )


def record_round_outcomes(round_report: Mapping[str, Any]) -> None:
    """Append actual WR/Judge outcomes for decisions made in this round."""
    decisions = round_report.get("ai_decisions", {})
    levels = round_report.get("levels", {})
    if not isinstance(decisions, Mapping) or not isinstance(levels, Mapping):
        return
    for lv, decision in decisions.items():
        if not isinstance(decision, Mapping):
            continue
        level_report = levels.get(str(lv), {})
        if not isinstance(level_report, Mapping):
            level_report = {}
        judge = level_report.get("judge", {})
        _record_metric({
            "level": str(lv),
            "round": round_report.get("round"),
            "status": decision.get("status"),
            "designer": decision.get("designer"),
            "selected_candidate_ids": decision.get("selected_candidate_ids", []),
            "snapshot_hash": decision.get("snapshot_hash"),
            "catalog_id": decision.get("catalog_id"),
            "decision_id": decision.get("decision_id"),
            "context_hash": decision.get("context_hash"),
            "actual_llm_calls": decision.get("actual_llm_calls", 0),
            "actual_wrs": level_report.get("batch_wrs", {}),
            "actual_games": level_report.get("batch_games", {}),
            "judge_result": judge.get("result") if isinstance(judge, Mapping) else None,
            "judge_reasons": (judge.get("reasons", [])[:5]
                              if isinstance(judge, Mapping) else []),
        })


if __name__ == "__main__":
    level = sys.argv[1] if len(sys.argv) > 1 else "62"
    print(json.dumps(design_probes_llm(level), ensure_ascii=False, indent=2, default=str))
