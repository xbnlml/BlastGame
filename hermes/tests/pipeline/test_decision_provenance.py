#!/usr/bin/env python3
"""Decision provenance binding and fail-closed replay contracts."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

HERMES = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERMES))


def probes():
    return {
        "T1": {"sd": 7, "sc": 5, "ratios": "1,1,1,1,10", "of": 0.1},
        "T2": {"sd": 8, "sc": 5, "ratios": "1,1,1,10,1", "of": 0.2},
    }


class DecisionProvenanceTest(unittest.TestCase):
    def test_provenance_hash_binds_exact_probe_configs(self):
        from tools.pipeline.provenance import (
            build_decision_provenance,
            validate_decision_provenance,
        )

        provenance = build_decision_provenance(
            level="60", round_num=2, probes=probes(),
            metadata={
                "decision_source": "deterministic_planner",
                "designer": "planner",
                "actual_llm_calls": 0,
            },
        )
        self.assertTrue(provenance["decision_id"].startswith("DEC-"))
        validate_decision_provenance(provenance, level="60", round_num=2, probes=probes())
        changed = dict(probes())
        changed["T2"] = dict(changed["T2"], sd=9)
        with self.assertRaises(ValueError):
            validate_decision_provenance(provenance, level="60", round_num=2, probes=changed)

    def test_runstore_replay_contains_decision_and_tamper_blocks(self):
        from tools.pipeline.control import reduce_events
        from tools.pipeline.provenance import build_decision_provenance

        provenance = build_decision_provenance(
            level="60", round_num=1, probes=probes(),
            metadata={"decision_source": "deterministic_planner", "actual_llm_calls": 0},
        )

        def event(kind, key, **extra):
            return {
                "type": kind,
                "run_id": "run-1",
                "level": "60",
                "attempt_id": "attempt-1",
                "idempotency_key": key,
                "payload_hash": "payload-" + key,
                **extra,
            }

        events = [
            event("CREATED", "created"),
            event("SNAPSHOT_READY", "snapshot"),
            event("DECISION_VALIDATED", "decision", **provenance),
            event(
                "SUBMITTED", "submitted",
                request_plan_hash="plan-1",
                decision_id="DEC-tampered",
                context_hash=provenance["context_hash"],
                catalog_id=provenance["catalog_id"],
                probe_config_hash=provenance["probe_config_hash"],
            ),
        ]
        state = reduce_events(events)["levels"]["60"]
        self.assertEqual("ERROR_BLOCKED", state["status"])
        self.assertEqual("decision_id_mismatch", state["block_reason"])

    def test_runtime_run_spec_and_decision_event_are_immutable_artifacts(self):
        from tools.pipeline.runtime import V3RunRuntime
        from tools.pipeline.unity_request import artifact_set_hash, execution_plan_hash
        from tools.pipeline.provenance import build_decision_provenance

        artifacts = [
            {"level": "60", "slot": "T1", "tier": 1, "board_fingerprint": "b", "deal_fingerprint": "d1",
             "sd": "7", "sc": "5", "ratios": "1,1,1,1,10", "of": "0.1", "win_rate": 0.8, "total_games": 400},
            {"level": "60", "slot": "T2", "tier": 2, "board_fingerprint": "b", "deal_fingerprint": "d2",
             "sd": "8", "sc": "5", "ratios": "1,1,1,10,1", "of": "0.2", "win_rate": 0.6, "total_games": 400},
        ]
        plan = execution_plan_hash(artifacts, "logic-v1")
        provenance = build_decision_provenance(
            level="60", round_num=1, probes=probes(),
            metadata={"decision_source": "deterministic_planner", "actual_llm_calls": 0},
        )
        request = {
            "run_id": "run-prov", "attempt_id": "attempt-prov", "logic_version": "logic-v1",
            "levels": ["60"], "tiers": [1, 2], "request_plan_hash": plan,
            "probes": {"60": probes()}, "require_decision_provenance": True,
            "decision_provenance": {"60": provenance},
        }
        receipt = {
            "status": "accepted", "batch_receipt_id": "receipt-prov",
            "run_id": "run-prov", "attempt_id": "attempt-prov", "batch_id": "batch-prov",
            "request_plan_hash": plan, "executed_plan_hash": plan, "logic_version": "logic-v1",
            "expected_artifact_set_hash": artifact_set_hash(artifacts),
            "accepted_artifact_set_hash": artifact_set_hash(artifacts),
            "artifacts": artifacts,
        }
        with tempfile.TemporaryDirectory() as tmp:
            runtime = V3RunRuntime(Path(tmp) / "run-prov", request)
            runtime.start()
            spec = runtime.store.read_run_spec()
            self.assertEqual(provenance, spec["decision_provenance"]["60"])
            self.assertTrue(any(e["type"] == "DECISION_VALIDATED" for e in runtime.store.load_events()))


if __name__ == "__main__":
    unittest.main(verbosity=2)
