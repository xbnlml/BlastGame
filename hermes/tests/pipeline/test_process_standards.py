#!/usr/bin/env python3
"""P0 process-standard regression tests."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

HERMES = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERMES))


class ProcessStandardsTest(unittest.TestCase):
    def test_probe_gap_analysis_does_not_reintroduce_removed_t3_anchor(self):
        from tools.design_probes import analyze_gaps

        _, hard_specs = analyze_gaps(
            [85.0, 85.0, 55.0, 45.0, 45.0],
            [80.0, 80.0, 50.0, 45.0, 45.0],
            "normal",
        )
        self.assertFalse(any(spec.get("tier") == 2 for spec in hard_specs))

    def test_fallback_probe_slots_are_positioned_not_overwritten(self):
        from tools.agent_analyze import _fallback_probes

        probes = _fallback_probes(
            [
                {"wr": 90, "sd": 1, "sc": 5, "ratios": "1,1,1,1,1", "of": 0.1},
                {"wr": 80, "sd": 2, "sc": 5, "ratios": "2,1,1,1,1", "of": 0.1},
                {"wr": 70, "sd": 3, "sc": 5, "ratios": "3,1,1,1,1", "of": 0.1},
                {"wr": 60, "sd": 4, "sc": 5, "ratios": "4,1,1,1,1", "of": 0.1},
                {"wr": 50, "sd": 5, "sc": 5, "ratios": "5,1,1,1,1", "of": 0.1},
            ],
            [],
        )
        self.assertEqual([1, 2, 3, 4, 5], [item["tier"] for item in probes])

    def test_auto_loop_rejects_probe_design_with_fewer_than_five_records(self):
        from scripts.auto_loop import _normalise_probe_slots

        self.assertIsNone(_normalise_probe_slots([{"sd": 1, "sc": 5, "ratios": "1,1,1,1,1", "of": 0.1}] * 4))

    def test_round_report_has_no_latest_directory_fallback(self):
        from scripts.auto_loop import _build_round_report

        report = _build_round_report(2, {"136": {}}, {"136": {}}, [136])
        self.assertEqual("missing_explicit_receipt", report["batch_wrs_source"])
        self.assertEqual({}, report["levels"]["136"]["batch_wrs"])

    def test_receipt_wrs_are_read_from_explicit_artifacts(self):
        from tools.pipeline.batch_run import receipt_games, receipt_win_rates

        receipt = {
            "status": "accepted",
            "batch_id": "batch-explicit",
            "artifacts": [
                {"level": "136", "slot": "T1", "win_rate": 0.813, "total_games": 400},
                {"level": "136", "slot": "T3", "win_rate": 0.612, "total_games": 240},
                {"level": "136", "slot": "T5", "win_rate": 0.441, "total_games": 400},
            ],
        }
        self.assertEqual(
            {"136": {"T1": 81.3, "T3": 61.2, "T5": 44.1}},
            receipt_win_rates(receipt, [136]),
        )
        self.assertEqual(
            {"136": {"T1": 400, "T3": 240, "T5": 400}},
            receipt_games(receipt, [136]),
        )

    def test_planner_marks_close_as_continue_not_import(self):
        from tools.planner import action_for_judgment

        self.assertEqual("继续调优(接近)", action_for_judgment("接近", 2, 6))
        self.assertEqual("待确认入库", action_for_judgment("合格", 2, 6))

    def test_probe_validator_accepts_real_asset_of_range(self):
        from tools.probe_validator import validate_probes

        probes = [
            {"sd": i + 1, "sc": 5, "ratios": f"{i + 1},1,1,1,1", "of": of}
            for i, of in enumerate((0.75, 0.85, 1.0, 0.35, 0.5))
        ]
        errors = validate_probes(probes, "136")
        self.assertFalse([e for e in errors if e["kind"] == "schema" and "of=" in e["msg"]])


if __name__ == "__main__":
    unittest.main(verbosity=2)
