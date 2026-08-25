#!/usr/bin/env python3
"""P0 process-standard regression tests."""
from __future__ import annotations

import copy
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

HERMES = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERMES))


class ProcessStandardsTest(unittest.TestCase):
    def test_removed_t3_anchor_is_not_required_by_judge(self):
        from tools import judge_level
        from tools.judge_level import check_judgment

        rules = json.loads(
            (HERMES / "project-state" / "rules.json").read_text(encoding="utf-8")
        )["judge_rules"]
        for difficulty in ("normal", "hard", "superhard"):
            self.assertNotIn("anchor", rules[difficulty])
            self.assertIn("hard_violations", rules[difficulty])
            self.assertFalse(any("t3" in item.lower() for item in rules[difficulty]["hard_violations"]))

        cases = [
            ("normal", {"T1": 70, "T2": 70, "T3": 45, "T4": 30, "T5": 30}, [70, 70, 45, 30, 30]),
            ("hard", {"T1": 75, "T2": 65, "T3": 55, "T4": 45, "T5": 35}, [75, 65, 55, 45, 35]),
            ("superhard", {"T1": 75, "T2": 65, "T3": 55, "T4": 45, "T5": 35}, [75, 65, 55, 45, 35]),
        ]
        for difficulty, combo, targets in cases:
            result, reasons = check_judgment(combo, difficulty, targets)
            self.assertEqual("合格", result, reasons)

        original = judge_level._rules_cache
        try:
            judge_level._rules_cache = {"judge_rules": {}}
            with self.assertRaises(ValueError):
                check_judgment(cases[0][1], "normal", cases[0][2])

            invalid = copy.deepcopy(rules)
            invalid["normal"]["hard_violations"] = ["inverted>1"]
            judge_level._rules_cache = {"judge_rules": invalid}
            with self.assertRaises(ValueError):
                check_judgment(cases[0][1], "normal", cases[0][2])
        finally:
            judge_level._rules_cache = original

    def test_curator_calls_qualified_results_pending_import(self):
        from unittest.mock import patch
        from tools import curator

        cases = [(0, 0, 0), (1, 1, 1), (2, 4, 3)]
        for passed, failed, errors in cases:
            log = (
                f"✅ Passed (待确认入库): {passed} levels\n"
                f"❌ Failed (改关卡): {failed} levels\n"
                f"⚠ Errors: {errors} levels\n"
            )
            with self.subTest(passed=passed, failed=failed, errors=errors), patch.object(
                curator, "update_memory"
            ) as update:
                curator.update_curator_stats(log, "auto-log/example.log")
                content = update.call_args.args[2]
                self.assertIn(f"合格待确认入库: {passed}", content)
                self.assertIn(f"改关卡: {failed}", content)
                self.assertIn(f"错误: {errors}", content)
                self.assertNotIn("通过入库", content)

    def test_planner_round_boundary_matches_judge(self):
        from tools.judge_level import action_for_judgment as judge_action
        from tools.planner import action_for_judgment as planner_action

        cases = [
            ("合格", 5, "待确认入库"),
            ("接近", 1, "继续调优(接近)"),
            ("接近", 5, "继续调优(接近)"),
            ("接近", 6, "改关卡"),
            ("不合格", 1, "下一轮(2/6)"),
            ("不合格", 5, "下一轮(6/6)"),
            ("不合格", 6, "改关卡"),
        ]
        for result, completed, expected in cases:
            with self.subTest(result=result, completed=completed):
                self.assertEqual(expected, judge_action(result, completed, 6))
                self.assertEqual(expected, planner_action(result, completed, 6))

    def test_curator_accepts_close_and_repeated_round_sequences(self):
        from tools.curator import supervise

        for rounds in (1, 2, 6):
            chunks = []
            for round_number in range(1, rounds + 1):
                chunks.append(
                    f"=== ROUND {round_number}/6 ===\n"
                    "Phase 1: planner.py\n"
                    "Phase 2: apply probes\n"
                    "Phase 3: Warden 通过\n"
                    "Phase 4: refresh\n"
                    "Phase 5: Judge\n"
                    f"L79 r{round_number}/6: 接近 — 继续调优(接近)"
                )
            with self.subTest(rounds=rounds):
                self.assertEqual([], supervise("\n".join(chunks)))

    def test_final_summary_parser_and_watchdog_zero_error_contract(self):
        from scripts.auto_loop_watchdog import final_summary_messages
        from tools.auto_log_summary import parse_final_summary

        cases = [(0, 0, 0), (1, 2, 0), (7, 4, 3)]
        for passed, failed, errors in cases:
            text = (
                "=== FINAL SUMMARY ===\n"
                f"✅ Passed (待确认入库): {passed} levels\n"
                f"❌ Failed (改关卡): {failed} levels\n"
                f"⚠ Errors: {errors} levels\n"
            )
            with self.subTest(passed=passed, failed=failed, errors=errors):
                summary = parse_final_summary(text)
                self.assertEqual(
                    {"passed": passed, "failed": failed, "errors": errors},
                    summary,
                )
                messages = final_summary_messages(text)
                self.assertTrue(any("auto_loop 已结束" in item for item in messages))
                self.assertEqual(errors > 0, any("有错误" in item for item in messages))

    def test_watchdog_handles_checkout_without_auto_logs(self):
        from unittest.mock import patch
        from scripts import auto_loop_watchdog

        with tempfile.TemporaryDirectory() as tmp, patch.object(
            auto_loop_watchdog, "AUTOLOG", str(Path(tmp) / "missing-auto-log")
        ):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                auto_loop_watchdog.check()
        self.assertIn("无 auto_loop 日志", output.getvalue())

    def test_watchdog_detects_final_summary_larger_than_old_tail_window(self):
        from unittest.mock import patch
        from scripts import auto_loop_watchdog

        summary = (
            "=== FINAL SUMMARY ===\n"
            "✅ Passed (待确认入库): 42 levels\n"
            "❌ Failed (改关卡): 3 levels\n"
            "⚠ Errors: 0 levels\n"
            + "".join(f"L{level}: detail {'x' * 80}\n" for level in range(1, 151))
        )
        self.assertGreater(len(summary), 3000)
        with tempfile.TemporaryDirectory() as tmp:
            log_dir = Path(tmp) / "auto-log"
            log_dir.mkdir()
            (log_dir / "latest.log").write_text(summary, encoding="utf-8")
            with patch.object(auto_loop_watchdog, "AUTOLOG", str(log_dir)), patch.object(
                auto_loop_watchdog, "ROUNDS", str(Path(tmp) / "missing-rounds.json")
            ), patch.object(
                auto_loop_watchdog.subprocess,
                "run",
                return_value=SimpleNamespace(stdout=b"INFO: No tasks are running"),
            ):
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    auto_loop_watchdog.check()
        self.assertIn("auto_loop 已结束", output.getvalue())
        self.assertNotIn("有错误", output.getvalue())

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
