#!/usr/bin/env python3
"""Explicit V3 Unity request -> marker -> CSV -> receipt contracts."""
from __future__ import annotations

import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

HERMES = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERMES))


def artifacts():
    return [
        {"level": "60", "slot": "T1", "tier": 1, "board_fingerprint": "board-60", "deal_fingerprint": "deal-1"},
        {"level": "60", "slot": "T2", "tier": 2, "board_fingerprint": "board-60", "deal_fingerprint": "deal-2"},
    ]


def request():
    from tools.pipeline.unity_request import execution_plan_hash
    rows = artifacts()
    plan_hash = execution_plan_hash(rows, "logic-v1")
    return {
        "run_id": "run-1", "attempt_id": "attempt-1", "batch_id": "v3-batch-1",
        "request_plan_hash": plan_hash, "executed_plan_hash": plan_hash,
        "logic_version": "logic-v1", "expected_artifacts": rows,
    }


def write_marker(directory, req, mismatch=None):
    marker = {field: req[field] for field in ("run_id", "attempt_id", "batch_id", "request_plan_hash")}
    if mismatch:
        marker[mismatch] = "wrong"
    (directory / "v3-unity-run.json").write_text(json.dumps(marker), encoding="utf-8")


def write_csv(directory, rows):
    with (directory / "campaign-summary-T1.csv").open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["level", "Tier", "BoardFingerprint", "DealFingerprint", "winkate"])
        writer.writeheader()
        for row in rows:
            writer.writerow({
                "level": row["level"], "Tier": row["tier"],
                "BoardFingerprint": row["board_fingerprint"],
                "DealFingerprint": row["deal_fingerprint"], "winkate": "0.75",
            })


class UnityRequestReceiptTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.req = request()
        self.batch = self.root / self.req["batch_id"]
        self.batch.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def test_explicit_marker_and_full_csv_make_verified_receipt(self):
        from tools.pipeline.batch_run import verify_batch_artifacts
        from tools.pipeline.unity_request import write_receipt_from_batch
        write_marker(self.batch, self.req)
        write_csv(self.batch, artifacts())
        receipt = write_receipt_from_batch(self.batch, self.req)
        self.assertEqual("accepted", receipt["status"])
        verified = verify_batch_artifacts(self.root, self.req)
        self.assertEqual("accepted", verified["status"])
        self.assertEqual(2, len(verified["artifacts"]))

    def test_partial_csv_receipt_has_exact_missing_partition(self):
        from tools.pipeline.batch_run import verify_batch_artifacts
        from tools.pipeline.unity_request import write_receipt_from_batch
        write_marker(self.batch, self.req)
        write_csv(self.batch, artifacts()[:1])
        receipt = write_receipt_from_batch(self.batch, self.req)
        self.assertEqual("partial", receipt["status"])
        self.assertEqual([["60", "T2"]], receipt["missing_pairs"])
        verified = verify_batch_artifacts(self.root, self.req)
        self.assertEqual([["60", "T2"]], verified["retry_pairs"])

    def test_marker_identity_tamper_blocks_before_csv_is_consumed(self):
        from tools.pipeline.batch_run import ArtifactVerificationError
        from tools.pipeline.unity_request import write_receipt_from_batch
        write_marker(self.batch, self.req, mismatch="attempt_id")
        write_csv(self.batch, artifacts())
        with self.assertRaises(ArtifactVerificationError) as caught:
            write_receipt_from_batch(self.batch, self.req)
        self.assertEqual("UNITY_MARKER_IDENTITY_MISMATCH", caught.exception.code)

    def test_builder_filters_exact_slots_and_uses_canonical_plan_hash(self):
        from tools.pipeline.unity_request import build_unity_request, execution_plan_hash
        with patch("tools.pipeline.unity_request._official_asset_plan", return_value=artifacts() + [
            {"level": "60", "slot": "T3", "tier": 3, "board_fingerprint": "board-60", "deal_fingerprint": "deal-3"},
            {"level": "60", "slot": "T4", "tier": 4, "board_fingerprint": "board-60", "deal_fingerprint": "deal-4"},
            {"level": "60", "slot": "T5", "tier": 5, "board_fingerprint": "board-60", "deal_fingerprint": "deal-5"},
        ]):
            built = build_unity_request(
                levels=[60], tiers=[1, 3], run_id="r", attempt_id="a", batch_id="safe-batch",
                logic_version="logic-v1",
            )
        self.assertEqual(["T1", "T3"], [row["slot"] for row in built["expected_artifacts"]])
        self.assertEqual(execution_plan_hash(built["expected_artifacts"], "logic-v1"), built["request_plan_hash"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
