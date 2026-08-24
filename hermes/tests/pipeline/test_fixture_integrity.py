#!/usr/bin/env python3
"""Fixture self-integrity: protects the historical evidence from accidental drift."""
from __future__ import annotations

import csv
import json
import re
import unittest
from pathlib import Path

HERMES = Path(__file__).resolve().parents[2]
FIXTURES = HERMES / "tests" / "fixtures"
HEADER = [
    "LevelGroup", "level", "Tier", "FingerprintAlgorithm", "BoardFingerprint",
    "LegacyBoardFingerprint", "DealFingerprint", "startDifficulty",
    "shuffleSplitCount", "shuffleSplitRatios", "shuffleOverflowFactor",
    "DifficultyLevel", "failBucketDistribution", "winCount", "failCount",
    "winkate", "V2BoardFingerprint",
]
HASH = re.compile(r"^[0-9a-f]{64}$")


class FixtureIntegrityTest(unittest.TestCase):
    def test_shared_csv_schema_identity_and_35_artifacts_are_exact(self):
        root = FIXTURES / "shared_csv_7_levels"
        request = json.loads((root / "request.json").read_text(encoding="utf-8"))
        receipt = json.loads(next((root / "telemetry" / "bot").rglob("unity_receipt.json")).read_text(encoding="utf-8"))
        rows = []
        for path in (root / "telemetry" / "bot").rglob("campaign-summary-*.csv"):
            with path.open(encoding="utf-8", newline="") as fh:
                reader = csv.DictReader(fh)
                self.assertEqual(HEADER, reader.fieldnames)
                rows.extend(reader)

        expected = {
            (item["level"], item["slot"], item["tier"], item["board_fingerprint"], item["deal_fingerprint"])
            for item in request["expected_artifacts"]
        }
        actual = {
            (row["level"], f"T{row['Tier']}", int(row["Tier"]), row["BoardFingerprint"], row["DealFingerprint"])
            for row in rows
        }
        self.assertEqual(35, len(rows))
        self.assertEqual(35, len(actual))
        self.assertEqual(expected, actual)
        self.assertEqual(request["expected_artifacts"], receipt["artifacts"])
        for key in ("run_id", "attempt_id", "batch_id", "request_plan_hash", "executed_plan_hash", "logic_version"):
            self.assertEqual(request[key], receipt[key])
        for _, _, _, board, deal in actual:
            self.assertRegex(board, HASH)
            self.assertRegex(deal, HASH)

    def test_partial_fixture_preserves_one_row_and_declares_the_other_three(self):
        root = FIXTURES / "partial_batch"
        request = json.loads((root / "request.json").read_text(encoding="utf-8"))
        receipt = json.loads(next((root / "telemetry" / "bot").rglob("unity_receipt.json")).read_text(encoding="utf-8"))
        self.assertEqual("partial", receipt["status"])
        accepted = {(x["level"], x["slot"]) for x in receipt["artifacts"]}
        missing = {tuple(x) for x in receipt["missing_pairs"]}
        expected = {(x["level"], x["slot"]) for x in request["expected_artifacts"]}
        self.assertEqual({("60", "T1")}, accepted)
        self.assertEqual(
            {("60", "T2"), ("62", "T1"), ("62", "T2")},
            missing,
        )
        self.assertFalse(accepted & missing)
        self.assertEqual(expected, accepted | missing)
        self.assertEqual(request["attempt_id"], receipt["attempt_id"])
        csv_rows = []
        for path in (root / "telemetry" / "bot").rglob("campaign-summary-*.csv"):
            with path.open(encoding="utf-8", newline="") as fh:
                reader = csv.DictReader(fh)
                self.assertEqual(HEADER, reader.fieldnames)
                csv_rows.extend(reader)
        self.assertEqual(accepted, {(row["level"], f"T{row['Tier']}") for row in csv_rows})

    def test_stale_fixture_request_receipt_and_csv_bind_the_same_identity(self):
        root = FIXTURES / "stale_latest_dir"
        request = json.loads((root / "request.json").read_text(encoding="utf-8"))
        requested = root / "telemetry" / "bot" / request["batch_id"]
        receipt = json.loads((requested / "unity_receipt.json").read_text(encoding="utf-8"))
        for key in ("run_id", "attempt_id", "batch_id", "request_plan_hash", "executed_plan_hash", "logic_version"):
            self.assertEqual(request[key], receipt[key])
        with next(requested.rglob("campaign-summary-*.csv")).open(encoding="utf-8", newline="") as fh:
            rows = list(csv.DictReader(fh))
        self.assertEqual(1, len(rows))
        self.assertEqual("60", rows[0]["level"])
        self.assertEqual(1, int(rows[0]["Tier"]))
        self.assertEqual(receipt["artifacts"][0]["board_fingerprint"], rows[0]["BoardFingerprint"])
        self.assertEqual(receipt["artifacts"][0]["deal_fingerprint"], rows[0]["DealFingerprint"])

    def test_l138_fixture_is_all_slot_health_red_light(self):
        health = json.loads((FIXTURES / "asset_db_mismatch_l138" / "system_health.json").read_text(encoding="utf-8"))
        self.assertEqual("138", health["level"])
        self.assertEqual("asset_db_fingerprint_mismatch", health["reason"])
        self.assertEqual(5, len(health["asset_configs"]))
        self.assertEqual(5, len(health["database_configs"]))
        self.assertNotEqual(health["asset_configs"], health["database_configs"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
