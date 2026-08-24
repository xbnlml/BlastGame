#!/usr/bin/env python3
"""AI probe selector integration contracts without real Hermes/Unity calls."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

HERMES = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERMES))


def generated_snapshot():
    return {
        "version": "PROBE_SNAPSHOT_V1",
        "level": "176",
        "round": 2,
        "board_fingerprint": "board-176",
        "logic_version": "2026-08-13T14:36:00+08:00",
        "policy_id": "rules.json",
        "targets": [80, 80, 60, 45, 45],
        "difficulty": "normal",
        "best_combo": {"T1": 80},
        "gaps": [20, 15],
        "judge_reasons": [],
        "verified": [],
        "phase2": [],
        "phase1": [],
        "generated": [
            {
                "id": f"gen-{i}", "source": "generated", "sd": i,
                "sc": 5, "ratios": f"{i},1,1,1,1", "of": 0.1,
                "totalGames": 0, "wr": None, "retest_allowed": False,
            }
            for i in range(1, 6)
        ],
        "attempt_history": [],
    }


class AIProbeSelectorTest(unittest.TestCase):
    def test_llm_selects_candidate_ids_and_returns_execution_slots(self):
        from tools.pipeline.probe_decision import build_candidate_catalog, build_context_v3
        import tools.llm_probe_pipeline as pipeline

        snapshot = generated_snapshot()
        catalog = build_candidate_catalog(snapshot)
        context = build_context_v3(snapshot, catalog)
        selected = catalog["candidates"][:5]
        response = {
            "selected": [
                {
                    "candidate_id": item["candidate_id"],
                    "objective_id": "gap_probe",
                    "role": "exploration",
                    "evidence_ids": item["evidence_ids"],
                    "hypothesis": "test hypothesis",
                }
                for item in selected
            ],
            "design_note": "test",
        }

        with patch.object(pipeline.llm_client, "_load_advisor_cfg", return_value={"enabled": True, "mode": "llm"}), \
             patch.object(pipeline, "script_design", return_value={}), \
             patch.object(pipeline, "_build_snapshot", return_value=snapshot), \
             patch.object(pipeline.packager, "pack_level", return_value={"bands": {}}), \
             patch.object(pipeline.llm_client, "ask", return_value=response), \
             patch.object(pipeline.llm_client, "write_advisor"), \
             patch.object(pipeline, "_record_metric"):
            result = pipeline.design_probes_llm("176", round_num=2)

        self.assertEqual("llm_original", result["status"])
        self.assertEqual(["T1", "T2", "T3", "T4", "T5"], sorted(result["probes"]))
        self.assertEqual(5, len(result["selected_candidate_ids"]))
        self.assertTrue(result["decision_id"].startswith("DEC-"))
        self.assertEqual(1, result["actual_llm_calls"])

    def test_invalid_decision_uses_one_hermes_call_then_fallback(self):
        import tools.llm_probe_pipeline as pipeline

        fallback = {
            f"T{i}": {"sd": i, "sc": 5, "ratios": f"{i},1,1,1,1", "of": 0.1}
            for i in range(1, 6)
        }
        snapshot = generated_snapshot()
        with patch.object(pipeline.llm_client, "_load_advisor_cfg", return_value={"enabled": True, "mode": "llm"}), \
             patch.object(pipeline, "script_design", return_value=fallback), \
             patch.object(pipeline, "_build_snapshot", return_value=snapshot), \
             patch.object(pipeline.packager, "pack_level", return_value={"bands": {}}), \
             patch.object(pipeline.llm_client, "ask", return_value={"selected": []}) as ask, \
             patch.object(pipeline.llm_client, "write_advisor"), \
             patch.object(pipeline, "_record_metric"):
            result = pipeline.design_probes_llm("176", round_num=2)

        self.assertEqual(1, ask.call_count)
        self.assertEqual("script_fallback", result["status"])
        self.assertEqual(1, result["actual_llm_calls"])
        self.assertTrue(result["decision_id"].startswith("DEC-"))

    def test_enabled_approved_lessons_enter_planner_context_only(self):
        import tools.llm_probe_pipeline as pipeline

        captured = {}
        snapshot = generated_snapshot()
        lesson = {
            "entry_id": "planner-lesson-1",
            "role": "planner",
            "status": "active",
            "observation": "approved observation",
            "recommendation": "approved recommendation",
        }

        def capture_prompt(context, catalog, packed, lessons):
            captured["context"] = context
            captured["lessons"] = lessons
            return "{}"

        with patch.object(pipeline.llm_client, "_load_advisor_cfg", return_value={
                 "enabled": True, "mode": "llm",
                 "approved_lessons": {"enabled": True, "max_entries": 8},
             }), \
             patch.object(pipeline, "script_design", return_value={}), \
             patch.object(pipeline, "_build_snapshot", return_value=snapshot), \
             patch.object(pipeline.packager, "pack_level", return_value={"bands": {}}), \
             patch.object(pipeline, "load_approved_lessons", return_value={
                 "status": "ok", "entries": [lesson], "snapshot_hash": "LES-test",
             }), \
             patch.object(pipeline, "_candidate_prompt", side_effect=capture_prompt), \
             patch.object(pipeline.llm_client, "ask", return_value=None), \
             patch.object(pipeline, "_record_metric"):
            pipeline.design_probes_llm("176", round_num=2)

        self.assertEqual([lesson], captured["context"]["approved_lessons"])
        self.assertEqual([lesson], captured["lessons"]["approved_planner_lessons"])

    def test_free_form_or_invalid_decision_falls_back_to_script(self):
        import tools.llm_probe_pipeline as pipeline

        fallback = {
            f"T{i}": {"sd": i, "sc": 5, "ratios": f"{i},1,1,1,1", "of": 0.1}
            for i in range(1, 6)
        }
        snapshot = generated_snapshot()
        with patch.object(pipeline.llm_client, "_load_advisor_cfg", return_value={"enabled": True, "mode": "llm"}), \
             patch.object(pipeline, "script_design", return_value=fallback), \
             patch.object(pipeline, "_build_snapshot", return_value=snapshot), \
             patch.object(pipeline.packager, "pack_level", return_value={"bands": {}}), \
             patch.object(pipeline.llm_client, "ask", return_value={"probes": [{"sd": 1}]}), \
             patch.object(pipeline.llm_client, "write_advisor"), \
             patch.object(pipeline, "_record_metric"):
            result = pipeline.design_probes_llm("176", round_num=2)

        self.assertEqual("script_fallback", result["status"])
        self.assertEqual(fallback, result["probes"])

    def test_round_outcome_metrics_include_actual_wrs(self):
        import tools.llm_probe_pipeline as pipeline
        with patch.object(pipeline, "_record_metric") as record:
            pipeline.record_round_outcomes({
                "round": 2,
                "ai_decisions": {"176": {
                    "status": "llm_original", "designer": "llm",
                    "selected_candidate_ids": ["C176-a"],
                }},
                "levels": {"176": {
                    "batch_wrs": {"T1": 81.2},
                    "judge": {"result": "接近", "reasons": ["gap"]},
                }},
            })
        payload = record.call_args.args[0]
        self.assertEqual({"T1": 81.2}, payload["actual_wrs"])
        self.assertEqual("接近", payload["judge_result"])

    def test_auto_loop_adapter_converts_ai_configs_for_existing_apply_path(self):
        from scripts.auto_loop import _select_ai_probes

        class Log:
            def __init__(self):
                self.lines = []

            def log(self, message):
                self.lines.append(message)

        result = {
            "status": "llm_original",
            "designer": "llm",
            "selected_candidate_ids": [f"C176-{i}" for i in range(5)],
            "snapshot_hash": "SNAP-1",
            "catalog_id": "CAT-1",
            "errors": [],
            "probes": {
                f"T{i}": {"sd": i, "sc": 5, "ratios": f"{i},1,1,1,1", "of": 0.1}
                for i in range(1, 6)
            },
        }
        with patch("tools.llm_probe_pipeline.design_probes_llm", return_value=result):
            probes, decisions = _select_ai_probes(Log(), [176], 2)
        self.assertEqual(set(["T1", "T2", "T3", "T4", "T5"]), set(probes["176"]))
        self.assertEqual("llm_original", decisions["176"]["status"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
