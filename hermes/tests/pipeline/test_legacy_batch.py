#!/usr/bin/env python3
"""Regression tests for the simplified legacy batch acceptance path."""
from __future__ import annotations

import csv
import tempfile
import time
import unittest
from pathlib import Path

from tools.pipeline.legacy_batch import (
    LegacyBatchVerificationError,
    resolve_legacy_batch_dir,
    verify_legacy_batch,
)


ASSET = """--- !u!114 &11400000
MonoBehaviour:
  myStack:
    DynamicDifficultyConfigs:
    - StartDifficulty: 10
      ShuffleSplitCount: 5
      ShuffleSplitRatios: 1,1,1,1,1
      ShuffleOverflowFactor: 0.5
    - StartDifficulty: 11
      ShuffleSplitCount: 5
      ShuffleSplitRatios: 1,1,1,1,1
      ShuffleOverflowFactor: 0.5
    - StartDifficulty: 12
      ShuffleSplitCount: 5
      ShuffleSplitRatios: 1,1,1,1,1
      ShuffleOverflowFactor: 0.5
    - StartDifficulty: 13
      ShuffleSplitCount: 5
      ShuffleSplitRatios: 1,1,1,1,1
      ShuffleOverflowFactor: 0.5
    - StartDifficulty: 14
      ShuffleSplitCount: 5
      ShuffleSplitRatios: 1,1,1,1,1
      ShuffleOverflowFactor: 0.5
  customCellDrawingListV2:
"""


class LegacyBatchTest(unittest.TestCase):
    def make_batch(self) -> tuple[Path, dict[str, list[dict[str, object]]]]:
        tmp = Path(self.tmp.name)
        batch = tmp / "L1-20260821T150000"
        snapshot = batch / "level-assets" / "test" / "1.asset"
        snapshot.parent.mkdir(parents=True)
        snapshot.write_text(ASSET, encoding="utf-8")

        summary_dir = batch / "L1-T1-2026-08-21T15-00-00-batch-range"
        summary_dir.mkdir(parents=True)
        summary = summary_dir / "campaign-summary-T1.csv"
        with summary.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow([
                "LevelGroup", "level", "Tier", "startDifficulty",
                "shuffleSplitCount", "shuffleSplitRatios", "shuffleOverflowFactor",
                "winCount", "failCount", "winkate", "BoardFingerprint",
            ])
            for tier, sd in enumerate([10, 11, 12, 13, 14], start=1):
                writer.writerow(["test", 1, tier, sd, 5, "1,1,1,1,1", 0.5, 80, 20, 0.8, "fp"])
        expected = {
            "1": [
                {"sd": 10, "sc": 5, "ratios": "1,1,1,1,1", "of": 0.5},
                {"sd": 11, "sc": 5, "ratios": "1,1,1,1,1", "of": 0.5},
                {"sd": 12, "sc": 5, "ratios": "1,1,1,1,1", "of": 0.5},
                {"sd": 13, "sc": 5, "ratios": "1,1,1,1,1", "of": 0.5},
                {"sd": 14, "sc": 5, "ratios": "1,1,1,1,1", "of": 0.5},
            ]
        }
        return batch, expected

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def test_snapshot_and_csv_coverage_are_verified(self):
        batch, expected = self.make_batch()
        result = verify_legacy_batch(batch, [1], [1, 2, 3, 4, 5], expected, max_games=400)
        self.assertTrue(result["asset_snapshots_verified"])
        self.assertEqual(5, result["artifact_count"])
        self.assertEqual(80.0, result["batch_wrs"]["1"]["T1"])

    def test_auto_loop_tier_mapping_is_accepted(self):
        batch, expected = self.make_batch()
        mapped = {"1": {f"T{i + 1}": value for i, value in enumerate(expected["1"])}}
        result = verify_legacy_batch(batch, [1], [1, 2, 3, 4, 5], mapped, max_games=400)
        self.assertEqual(5, result["artifact_count"])

    def test_non_mapping_expected_config_fails_as_verification_error(self):
        batch, expected = self.make_batch()
        bad = {"1": {f"T{i + 1}": "not-a-config" for i in range(5)}}
        with self.assertRaises(LegacyBatchVerificationError):
            verify_legacy_batch(batch, [1], [1, 2, 3, 4, 5], bad, max_games=400)

    def test_snapshot_mismatch_blocks_batch(self):
        batch, expected = self.make_batch()
        expected["1"][0]["sd"] = 99
        with self.assertRaises(LegacyBatchVerificationError):
            verify_legacy_batch(batch, [1], [1, 2, 3, 4, 5], expected, max_games=400)

    def test_explicit_buildlogs_pointer_is_used(self):
        batch, _ = self.make_batch()
        repo = Path(self.tmp.name) / "repo"
        pointer = repo / "BuildLogs" / "auto-batch-last-export.txt"
        pointer.parent.mkdir(parents=True)
        pointer.write_text(str(batch), encoding="utf-8")
        resolved = resolve_legacy_batch_dir(repo, "", started_at=time.time() - 2)
        self.assertEqual(batch, resolved)


if __name__ == "__main__":
    unittest.main(verbosity=2)
