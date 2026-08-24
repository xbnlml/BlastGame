#!/usr/bin/env python3
"""State-machine contracts: only a fully matched receipt can consume an attempt."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

HERMES = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERMES))

RUN_ID = "run-contract"


def valid_attempt_events(level: str, attempt: int, result: str = "不合格") -> list[dict]:
    aid = f"{level}-attempt-{attempt:03d}"
    receipt = f"receipt-{aid}"
    generation = f"generation-{aid}"
    return [
        {
            "type": "SUBMITTED", "run_id": RUN_ID, "level": level,
            "attempt_id": aid, "idempotency_key": f"submit-{aid}",
            "payload_hash": f"payload-submit-{aid}",
            "request_plan_hash": f"request-plan-{aid}",
        },
        {
            "type": "ARTIFACT_VERIFIED", "run_id": RUN_ID, "level": level,
            "attempt_id": aid, "batch_receipt_id": receipt,
            "verification_status": "accepted",
            "request_plan_hash": f"request-plan-{aid}",
            "executed_plan_hash": f"request-plan-{aid}",
            "expected_artifact_set_hash": f"expected-artifacts-{aid}",
            "accepted_artifact_set_hash": f"expected-artifacts-{aid}",
            "idempotency_key": f"verified-{aid}", "payload_hash": f"payload-verified-{aid}",
        },
        {
            "type": "INGESTED", "run_id": RUN_ID, "level": level,
            "attempt_id": aid, "batch_receipt_id": receipt,
            "ingest_generation_id": generation,
            "request_plan_hash": f"request-plan-{aid}",
            "executed_plan_hash": f"request-plan-{aid}",
            "accepted_artifact_set_hash": f"expected-artifacts-{aid}",
            "idempotency_key": f"ingested-{aid}", "payload_hash": f"payload-ingested-{aid}",
        },
        {
            "type": "JUDGED", "run_id": RUN_ID, "level": level,
            "attempt_id": aid, "batch_receipt_id": receipt,
            "consumed_generation_id": generation, "result": result,
            "request_plan_hash": f"request-plan-{aid}",
            "executed_plan_hash": f"request-plan-{aid}",
            "accepted_artifact_set_hash": f"expected-artifacts-{aid}",
            "idempotency_key": f"judged-{aid}", "payload_hash": f"payload-judged-{aid}",
        },
    ]


def level_state(events: list[dict], level: str) -> dict:
    from tools.pipeline.control import reduce_events
    return reduce_events(events)["levels"][level]


class StateMachineContractTest(unittest.TestCase):
    def test_only_full_verified_ingested_judged_chain_consumes_attempt(self):
        complete = valid_attempt_events("60", 1)
        for missing_type in ("SUBMITTED", "ARTIFACT_VERIFIED", "INGESTED", "JUDGED"):
            with self.subTest(missing_type=missing_type):
                events = [event for event in complete if event["type"] != missing_type]
                self.assertEqual(0, level_state(events, "60")["attempts_consumed"])

    def test_receipt_or_generation_mismatch_never_consumes_attempt(self):
        for field, value in (
            ("batch_receipt_id", "wrong-receipt"),
            ("consumed_generation_id", "wrong-generation"),
            ("accepted_artifact_set_hash", "wrong-artifact-set"),
            ("request_plan_hash", "wrong-request-plan"),
            ("executed_plan_hash", "wrong-executed-plan"),
        ):
            with self.subTest(field=field):
                events = valid_attempt_events("60", 1)
                events[-1][field] = value
                state = level_state(events, "60")
                self.assertEqual(0, state["attempts_consumed"])
                self.assertEqual("ERROR_BLOCKED", state["status"])

    def test_partial_receipt_cannot_be_ingested_or_consume_attempt(self):
        for status in ("partial", "rejected", "failed", None):
            with self.subTest(status=status):
                events = valid_attempt_events("60", 1)
                if status is None:
                    del events[1]["verification_status"]
                else:
                    events[1]["verification_status"] = status
                events[1]["accepted_artifact_set_hash"] = "partial-artifact-set"
                events[2]["accepted_artifact_set_hash"] = "partial-artifact-set"
                events[3]["accepted_artifact_set_hash"] = "partial-artifact-set"
                state = level_state(events, "60")
                self.assertEqual(0, state["attempts_consumed"])
                self.assertEqual("ERROR_BLOCKED", state["status"])

    def test_six_valid_mixed_near_and_unqualified_attempts_require_redesign_approval(self):
        events: list[dict] = []
        for attempt, result in enumerate(["不合格", "接近", "不合格", "接近", "不合格", "接近"], start=1):
            events.extend(valid_attempt_events("60", attempt, result))
        state = level_state(events, "60")
        self.assertEqual(6, state["attempts_consumed"])
        self.assertEqual("AWAIT_REDESIGN_APPROVAL", state["status"])

    def test_sixth_valid_qualified_attempt_queues_full_validation_not_redesign(self):
        events: list[dict] = []
        for attempt in range(1, 6):
            events.extend(valid_attempt_events("60", attempt, "不合格"))
        events.extend(valid_attempt_events("60", 6, "合格"))
        state = level_state(events, "60")
        self.assertEqual(6, state["attempts_consumed"])
        self.assertEqual("VALIDATION_QUEUED", state["status"])

    def test_attempt_budget_isolated_per_level(self):
        events: list[dict] = []
        for attempt in range(1, 7):
            events.extend(valid_attempt_events("60", attempt))
        events.extend(valid_attempt_events("62", 1, "接近"))
        from tools.pipeline.control import reduce_events
        states = reduce_events(events)["levels"]
        self.assertEqual(6, states["60"]["attempts_consumed"])
        self.assertEqual("AWAIT_REDESIGN_APPROVAL", states["60"]["status"])
        self.assertEqual(1, states["62"]["attempts_consumed"])
        self.assertEqual("QUEUED_NEXT_ATTEMPT", states["62"]["status"])

    def test_post_review_failure_is_control_state_neutral_before_or_after_receipt(self):
        baselines = [
            valid_attempt_events("60", 1, "接近")[:1],
            valid_attempt_events("60", 1, "接近"),
        ]
        for events in baselines:
            with self.subTest(baseline=events[-1]["type"]):
                baseline = level_state(events, "60")
                after_events = events + [{
                    "type": "POST_REVIEW_FAILED", "run_id": RUN_ID, "level": "60",
                    "attempt_id": "60-attempt-001", "idempotency_key": f"post-review-{events[-1]['type']}",
                    "payload_hash": f"payload-post-review-{events[-1]['type']}",
                }]
                after = level_state(after_events, "60")
                self.assertEqual(baseline["attempts_consumed"], after["attempts_consumed"])
                self.assertEqual(baseline["status"], after["status"])

    def test_exact_replay_is_idempotent_but_conflicting_replay_is_blocked(self):
        from tools.pipeline.control import IdempotencyConflict
        complete = valid_attempt_events("60", 1)
        self.assertEqual(1, level_state(complete + complete, "60")["attempts_consumed"])
        conflict = [dict(event) for event in complete]
        conflict[-1]["result"] = "合格"
        conflict[-1]["payload_hash"] = "different-payload"
        with self.assertRaises(IdempotencyConflict):
            level_state(complete + [conflict[-1]], "60")

    def test_same_receipt_with_a_new_event_key_is_not_ingested_twice(self):
        events = valid_attempt_events("60", 1)
        replay = dict(events[2])
        replay["idempotency_key"] = "ingested-same-receipt-new-key"
        replay["payload_hash"] = "payload-ingested-same-receipt-new-key"
        state = level_state(events[:3] + [replay] + events[3:], "60")
        self.assertEqual(["receipt-60-attempt-001"], state["ingested_receipt_ids"])
        self.assertEqual(1, state["ingest_count"])


if __name__ == "__main__":
    unittest.main(verbosity=2)