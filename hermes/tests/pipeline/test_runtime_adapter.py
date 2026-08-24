#!/usr/bin/env python3
"""V3 runtime adapter integration contracts."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

HERMES = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERMES))


class RuntimeAdapterTest(unittest.TestCase):
    def test_accepted_receipt_is_ingested_and_judged_once(self):
        from tools.pipeline.runtime import V3RunRuntime
        from tools.pipeline.unity_request import artifact_set_hash, execution_plan_hash
        artifacts = [
            {"level": "60", "slot": "T1", "tier": 1, "board_fingerprint": "b", "deal_fingerprint": "d1",
             "sd": "7", "sc": "5", "ratios": "1,1,1,1,10", "of": "0.1", "win_rate": 0.8, "total_games": 400},
            {"level": "60", "slot": "T2", "tier": 2, "board_fingerprint": "b", "deal_fingerprint": "d2",
             "sd": "8", "sc": "5", "ratios": "1,1,1,10,1", "of": "0.2", "win_rate": 0.6, "total_games": 400},
        ]
        plan = execution_plan_hash(artifacts, "logic-v1")
        receipt = {
            "status": "accepted", "batch_receipt_id": "receipt-1",
            "run_id": "run-1", "attempt_id": "attempt-1", "batch_id": "batch-1",
            "request_plan_hash": plan, "executed_plan_hash": plan, "logic_version": "logic-v1",
            "expected_artifact_set_hash": artifact_set_hash(artifacts),
            "accepted_artifact_set_hash": artifact_set_hash(artifacts),
            "identity": {"run_id": "run-1", "attempt_id": "attempt-1", "batch_id": "batch-1",
                         "request_plan_hash": plan, "executed_plan_hash": plan, "logic_version": "logic-v1"},
            "artifacts": artifacts,
        }
        request = {"run_id": "run-1", "attempt_id": "attempt-1", "logic_version": "logic-v1",
                   "levels": ["60"], "tiers": [1, 2], "request_plan_hash": plan}
        with tempfile.TemporaryDirectory() as temp:
            runtime = V3RunRuntime(Path(temp) / "run-1", request)
            runtime.start()
            runtime.submitted()
            runtime.finish(receipt)
            runtime.judged("60", "接近")
            state = runtime.state()["levels"]["60"]
            self.assertEqual(1, state["attempts_consumed"])
            self.assertEqual("QUEUED_NEXT_ATTEMPT", state["status"])
            records = runtime.records_for_judge("60")
            self.assertEqual(2, len(records))
            self.assertEqual(80.0, records[0]["wr"])
            self.assertEqual(60.0, records[1]["wr"])
            runtime.judged("60", "接近")
            self.assertEqual(1, runtime.state()["levels"]["60"]["attempts_consumed"])

    def test_judge_history_uses_only_explicit_accepted_generations(self):
        from tools.pipeline.runtime import V3RunRuntime
        from tools.pipeline.unity_request import artifact_set_hash, execution_plan_hash

        def make_attempt(root, run_id, batch_id, receipt_id, first_wr):
            artifacts = [
                {"level": "60", "slot": "T1", "tier": 1, "board_fingerprint": "b",
                 "deal_fingerprint": f"{batch_id}-d1", "sd": "7", "sc": "5",
                 "ratios": "1,1,1,1,10", "of": "0.1", "win_rate": first_wr,
                 "total_games": 400},
                {"level": "60", "slot": "T2", "tier": 2, "board_fingerprint": "b",
                 "deal_fingerprint": f"{batch_id}-d2", "sd": "8", "sc": "5",
                 "ratios": "1,1,1,10,1", "of": "0.2", "win_rate": first_wr - 0.2,
                 "total_games": 400},
            ]
            plan = execution_plan_hash(artifacts, "logic-v1")
            receipt = {
                "status": "accepted", "batch_receipt_id": receipt_id,
                "run_id": run_id, "attempt_id": "attempt-1", "batch_id": batch_id,
                "request_plan_hash": plan, "executed_plan_hash": plan,
                "logic_version": "logic-v1",
                "expected_artifact_set_hash": artifact_set_hash(artifacts),
                "accepted_artifact_set_hash": artifact_set_hash(artifacts),
                "identity": {"run_id": run_id, "attempt_id": "attempt-1",
                             "batch_id": batch_id, "request_plan_hash": plan,
                             "executed_plan_hash": plan, "logic_version": "logic-v1"},
                "artifacts": artifacts,
            }
            request = {"run_id": run_id, "attempt_id": "attempt-1",
                       "logic_version": "logic-v1", "levels": ["60"],
                       "tiers": [1, 2], "request_plan_hash": plan}
            runtime = V3RunRuntime(Path(root) / run_id, request)
            runtime.start()
            runtime.submitted()
            runtime.finish(receipt)
            return runtime

        with tempfile.TemporaryDirectory() as temp:
            prior = make_attempt(temp, "run-prior", "batch-prior", "receipt-prior", 0.8)
            current = make_attempt(temp, "run-current", "batch-current", "receipt-current", 0.7)
            records = current.records_for_judge("60", [str(prior.root)])
            self.assertEqual(4, len(records))
            self.assertAlmostEqual(70.0, records[0]["wr"])
            self.assertAlmostEqual(50.0, records[1]["wr"])
            self.assertAlmostEqual(80.0, records[2]["wr"])
            self.assertAlmostEqual(60.0, records[3]["wr"])
            generation_ids = current.consumed_generation_ids("60")
            self.assertEqual(2, len(generation_ids))
            current.judged("60", "不合格", supporting_generation_ids=generation_ids[1:])
            judged = [event for event in current.store.load_events() if event.get("type") == "JUDGED"]
            self.assertEqual(generation_ids[1:], judged[-1]["supporting_generation_ids"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
