#!/usr/bin/env python3
"""Regression tests for separate optimizer-summary evidence discovery."""
from __future__ import annotations

import csv
import os
import tempfile
import unittest
from pathlib import Path

from tools.pipeline.optimizer_summary import evaluate_optimizer_summary, find_latest_optimizer_summary


BOARD_FP = "e8bd0f7be4e3779eebfd6d568f83b2771cfbe191cd92c433815887b444df236c"
HEADER = [
    "GameLevel", "Tier", "Rank", "BoardFingerprint", "Status", "OutOfMargin",
    "SourcePhase", "VerifiedWinRate", "TotalRuns", "ConfiguredTargetWinRate",
    "StartDifficulty", "ShuffleSplitCount", "ShuffleSplitRatios", "ShuffleOverflowFactor",
]
ROWS = [
    ["124", "T1-超高胜率", "1", BOARD_FP, "ok", "False", "p3", "0.6324", "370", "0.70", "38", "5", "10,10,0,0,0", "1.0"],
    ["124", "T2-高胜率", "1", BOARD_FP, "ok", "False", "p3", "0.5100", "400", "0.55", "40", "5", "10,10,0,10,10", "1.0"],
    ["124", "T3-中等胜率", "1", BOARD_FP, "ok", "False", "p3", "0.4154", "390", "0.40", "38", "5", "10,10,10,0,0", "1.0"],
    ["124", "T4-低胜率", "1", BOARD_FP, "ok", "False", "p3", "0.3472", "360", "0.30", "20", "5", "0,0,10,0,0", "0.5"],
    ["124", "T5-超低胜率", "1", BOARD_FP, "ok", "False", "p0", "0.2038", "260", "0.20", "26", "5", "10,1,1,1,10", "0.5"],
]


class OptimizerSummaryGuardTest(unittest.TestCase):
    def write_summary(self, root: Path) -> Path:
        path = root / "101-150-2026-08-19T10-23-45" / "124-2026-08-19T21-45-04" / "summary.csv"
        path.parent.mkdir(parents=True)
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(HEADER)
            writer.writerows(ROWS)
        return path

    def test_current_board_summary_is_found_and_judged_separately(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write_summary(Path(tmp))
            evidence = evaluate_optimizer_summary(
                124,
                current_board_fingerprint=BOARD_FP,
                opt_root=tmp,
            )
            self.assertIsNotNone(evidence)
            self.assertEqual(str(path), evidence["source_path"])
            self.assertEqual("接近", evidence["judge_result"])
            self.assertEqual([63.24, 51.0, 41.54, 34.72, 20.38], evidence["wrs"])

    def test_mismatched_board_summary_is_not_used(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.write_summary(Path(tmp))
            self.assertIsNone(find_latest_optimizer_summary(
                124,
                current_board_fingerprint="different-board",
                opt_root=tmp,
            ))


if __name__ == "__main__":
    unittest.main(verbosity=2)
