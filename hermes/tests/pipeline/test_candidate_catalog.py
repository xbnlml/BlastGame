#!/usr/bin/env python3
"""CandidateCatalog and ContextV3 contracts."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

HERMES = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERMES))


def record(i, source="phase2", exact=False):
    return {
        "id": f"row-{source}-{i}", "sd": i + 1, "sc": 5,
        "ratios": f"{i + 1},1,1,1,1", "of": 0.1 + i / 100,
        "deal_fingerprint": f"deal-{source}-{i}", "source": source,
        "totalGames": 400, "wr": 0.8 - i / 100,
        "retest_allowed": exact,
    }


def snapshot():
    return {
        "snapshot_hash": "SNAP-fixed", "level": "136", "board_fingerprint": "board-136",
        "logic_version": "2026-08-13T14:36:00+08:00", "policy_id": "rules.json",
        "targets": [80, 80, 60, 45, 45], "best_combo": {"T1": 0.8},
        "gaps": [20, 20], "judge_reasons": [],
        "verified": [record(99, "verified")],
        "phase2": [record(i) for i in range(7)],
        "phase1": [record(i, "phase1") for i in range(3)],
        "attempt_history": [],
    }


class CandidateCatalogTest(unittest.TestCase):
    def setUp(self):
        from tools.pipeline.probe_decision import build_candidate_catalog, build_context_v3
        self.snapshot = snapshot()
        self.catalog = build_candidate_catalog(self.snapshot)
        self.context = build_context_v3(self.snapshot, self.catalog)

    def test_catalog_keeps_all_sources_without_top_n_cut(self):
        self.assertEqual(11, len(self.catalog["candidates"]))
        self.assertEqual({"phase1", "phase2", "verified"}, {
            origin for c in self.catalog["candidates"] for origin in c["origins"]
        })

    def test_script_baseline_and_validated_decision_use_five_current_ids(self):
        from tools.pipeline.probe_decision import freeze_script_baseline, validate_probe_decision
        decision = freeze_script_baseline(self.context, self.catalog)
        validated = validate_probe_decision(decision, self.catalog, self.context)
        self.assertTrue(validated["validated"])
        self.assertEqual(["P1", "P2", "P3", "P4", "P5"], [x["execution_slot"] for x in validated["selected"]])

    def test_free_form_config_and_unknown_or_duplicate_id_are_rejected(self):
        from tools.pipeline.probe_decision import DecisionInvalid, freeze_script_baseline, validate_probe_decision
        decision = freeze_script_baseline(self.context, self.catalog)
        with self.assertRaises(DecisionInvalid):
            validate_probe_decision({**decision, "selected": decision["selected"][:4] + [{"sd": 1}]}, self.catalog, self.context)
        duplicate = dict(decision)
        duplicate["selected"] = decision["selected"][:]
        duplicate["selected"][1] = dict(duplicate["selected"][0])
        with self.assertRaises(DecisionInvalid):
            validate_probe_decision(duplicate, self.catalog, self.context)
        stale = dict(decision); stale["snapshot_hash"] = "SNAP-old"
        with self.assertRaises(DecisionInvalid):
            validate_probe_decision(stale, self.catalog, self.context)

    def test_deterministic_baseline_is_a_valid_five_candidate_fallback(self):
        from tools.pipeline.probe_decision import freeze_script_baseline, validate_probe_decision
        decision = freeze_script_baseline(self.context, self.catalog)
        validated = validate_probe_decision(decision, self.catalog, self.context)
        self.assertEqual("frozen_script", validated["designer"])
        self.assertEqual(5, len(validated["selected"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
