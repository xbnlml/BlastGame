#!/usr/bin/env python3
"""Atomic ingest generation contracts."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

HERMES = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERMES))


def accepted_receipt():
    return {
        "status": "accepted",
        "identity": {
            "run_id": "run-001", "attempt_id": "attempt-001", "batch_id": "batch-001",
            "request_plan_hash": "plan-a", "executed_plan_hash": "plan-a", "logic_version": "logic-v1",
        },
        "artifacts": [
            {"level": "60", "slot": "T1", "deal_fingerprint": "deal-60-t1"},
            {"level": "60", "slot": "T2", "deal_fingerprint": "deal-60-t2"},
        ],
    }


def records(offset=0):
    return {"60": [
        {"level": "60", "slot": "T1", "deal_fingerprint": "deal-60-t1", "wr": 0.8 + offset},
        {"level": "60", "slot": "T2", "deal_fingerprint": "deal-60-t2", "wr": 0.6 + offset},
    ]}


class AtomicIngestContractTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        from tools.pipeline.ingest import AtomicGenerationStore
        self.store = AtomicGenerationStore(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_partial_receipt_cannot_write_generation(self):
        from tools.pipeline.ingest import IngestBlocked
        receipt = accepted_receipt() | {"status": "partial"}
        with self.assertRaises(IngestBlocked):
            self.store.ingest(receipt, records())
        self.assertFalse((Path(self.temp.name) / "generations").exists())

    def test_accepted_receipt_commits_once_and_judge_reads_exact_generation(self):
        first = self.store.ingest(accepted_receipt(), records())
        second = self.store.ingest(accepted_receipt(), records())
        self.assertEqual(first, second)
        self.assertEqual([0.8, 0.6], [row["wr"] for row in self.store.load_for_judge(first, "60")])
        pointer = json.loads((Path(self.temp.name) / "current.json").read_text(encoding="utf-8"))
        self.assertEqual(first["generation_id"], pointer["generation_id"])

    def test_same_receipt_with_changed_payload_fails_closed(self):
        from tools.pipeline.ingest import IngestReplayConflict
        self.store.ingest(accepted_receipt(), records())
        with self.assertRaises(IngestReplayConflict):
            self.store.ingest(accepted_receipt(), records(0.01))

    def test_judge_requires_receipt_and_rejects_tampered_generation(self):
        from tools.pipeline.ingest import IngestBlocked
        with self.assertRaises(IngestBlocked):
            self.store.load_for_judge({}, "60")
        receipt = self.store.ingest(accepted_receipt(), records())
        path = Path(self.temp.name) / "generations" / receipt["generation_id"] / "levels" / "60.json"
        path.write_text("[]", encoding="utf-8")
        with self.assertRaises(IngestBlocked) as caught:
            self.store.load_for_judge(receipt, "60")
        self.assertIn("checksum", str(caught.exception))


if __name__ == "__main__":
    unittest.main(verbosity=2)
