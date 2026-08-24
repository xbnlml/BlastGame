#!/usr/bin/env python3
"""Coordinator resume contracts: no repeat Unity or ingest after an accepted receipt."""
from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

HERMES = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERMES))


class RecordingRunner:
    def __init__(self):
        self.requests = []

    def run(self, request):
        self.requests.append(copy.deepcopy(request))
        return {"status": "submitted"}


class RecordingIngestor:
    def __init__(self):
        self.receipts = []

    def ingest(self, receipt):
        self.receipts.append(copy.deepcopy(receipt))


def partial_receipt(status="partial"):
    accepted = [{"level": "60", "slot": "T1", "tier": 1}]
    if status == "accepted":
        accepted = [
            {"level": "60", "slot": f"T{tier}", "tier": tier}
            for tier in range(1, 6)
        ]
    return {
        "status": status,
        "identity": {"run_id": "run-resume", "attempt_id": "attempt-001", "batch_id": "batch-001"},
        "accepted_artifacts": accepted,
        "retry_pairs": [["60", "T2"], ["60", "T3"], ["60", "T4"]] if status == "partial" else [],
    }


def resume_request(receipt, advisory_events=None):
    return {
        "run_id": "run-resume", "attempt_id": "attempt-001", "levels": ["60"],
        "prior_receipt": receipt, "advisory_events": advisory_events or [],
    }


class CoordinatorRecoveryContractTest(unittest.TestCase):
    def coordinator(self, runner, ingestor):
        from tools.pipeline.control import Coordinator
        return Coordinator(
            runner=runner, ingestor=ingestor,
            preflight=lambda _request: {"returncode": 0}, guards=[],
        )

    def test_partial_resume_reuses_attempt_and_submits_only_missing_pairs(self):
        runner, ingestor = RecordingRunner(), RecordingIngestor()
        coordinator = self.coordinator(runner, ingestor)
        coordinator.resume(resume_request(partial_receipt()))
        self.assertEqual(1, len(runner.requests))
        self.assertEqual("attempt-001", runner.requests[0]["attempt_id"])
        self.assertEqual({("60", "T2"), ("60", "T3"), ("60", "T4")}, {tuple(x) for x in runner.requests[0]["execution_pairs"]})
        self.assertEqual([], ingestor.receipts)

    def test_accepted_receipt_or_post_review_failure_never_restarts_unity(self):
        for advisory_events in ([], [{"type": "POST_REVIEW_FAILED"}]):
            with self.subTest(advisory_events=advisory_events):
                runner, ingestor = RecordingRunner(), RecordingIngestor()
                self.coordinator(runner, ingestor).resume(
                    resume_request(partial_receipt(status="accepted"), advisory_events)
                )
                self.assertEqual([], runner.requests)
                self.assertEqual([], ingestor.receipts)


if __name__ == "__main__":
    unittest.main(verbosity=2)