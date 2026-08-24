#!/usr/bin/env python3
"""Append-only RunStore recovery/idempotency contracts."""
from __future__ import annotations

import tempfile
import sys
import unittest
from pathlib import Path

HERMES = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERMES))


def event(kind: str, key: str, payload_hash: str | None = None) -> dict:
    return {
        "type": kind, "run_id": "run-store-contract", "level": "60",
        "attempt_id": "60-attempt-001", "idempotency_key": key,
        "payload_hash": payload_hash or f"payload-{key}",
        "artifact_paths": [f"attempts/60-attempt-001/{key}.json"],
    }


class RunStoreRecoveryContractTest(unittest.TestCase):
    def test_run_spec_is_immutable_and_persisted_events_gain_audit_metadata(self):
        from tools.pipeline.control import RunSpecImmutable, RunStore

        run_spec = {
            "run_id": "run-store-contract", "logic_version": "2026-08-13T14:36:00+08:00",
            "policy_hash": "p" * 64, "model": "gpt-5.6-luna", "reasoning": "max",
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = RunStore(root)
            self.assertTrue(store.initialize(run_spec))
            self.assertFalse(RunStore(root).initialize(dict(run_spec)))
            with self.assertRaises(RunSpecImmutable):
                RunStore(root).initialize(run_spec | {"policy_hash": "q" * 64})
            self.assertEqual(run_spec, store.read_run_spec())
            store.append(event("CREATED", "created"))
            persisted = store.load_events()[0]
            self.assertEqual(1, persisted["seq"])
            self.assertIsInstance(persisted["ts"], str)
            self.assertEqual(["attempts/60-attempt-001/created.json"], persisted["artifact_paths"])

    def test_truncated_tail_recovers_then_allows_safe_append(self):
        from tools.pipeline.control import RunStore

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = RunStore(root)
            store.append(event("CREATED", "created"))
            store.append(event("SNAPSHOT_READY", "snapshot"))
            with (root / "events.jsonl").open("ab") as fh:
                fh.write(b'{"type":"SUBMITTED"')

            self.assertEqual(["CREATED", "SNAPSHOT_READY"], [e["type"] for e in store.load_events()])
            self.assertEqual("truncated_tail", store.recovery_report()["status"])
            self.assertTrue(store.append(event("SUBMITTED", "submit")))
            self.assertEqual(
                ["CREATED", "SNAPSHOT_READY", "SUBMITTED"],
                [e["type"] for e in RunStore(root).load_events()],
            )

    def test_duplicate_key_survives_restart_and_conflicting_payload_fails_closed(self):
        from tools.pipeline.control import IdempotencyConflict, RunStore

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertTrue(RunStore(root).append(event("CREATED", "same")))
            self.assertFalse(RunStore(root).append(event("CREATED", "same")))
            with self.assertRaises(IdempotencyConflict):
                RunStore(root).append(event("CREATED", "same", "different"))

    def test_projection_rebuilds_from_events_when_summary_is_missing_or_corrupt(self):
        from tools.pipeline.control import RunStore

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = RunStore(root)
            store.append(event("CREATED", "created"))
            store.append(event("SNAPSHOT_READY", "snapshot"))
            (root / "summary.json").write_text("not-json", encoding="utf-8")
            state = RunStore(root).load_state()
            self.assertEqual("SNAPSHOT_READY", state["levels"]["60"]["status"])
            (root / "summary.json").unlink(missing_ok=True)
            self.assertEqual(state, RunStore(root).load_state())

    def test_middle_corruption_fails_closed(self):
        from tools.pipeline.control import EventStoreCorrupt, RunStore

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = RunStore(root)
            store.append(event("CREATED", "created"))
            with (root / "events.jsonl").open("ab") as fh:
                fh.write(b'not-json\n')
                fh.write(b'{"type":"SNAPSHOT_READY"}\n')
            with self.assertRaises(EventStoreCorrupt):
                RunStore(root).load_events()


if __name__ == "__main__":
    unittest.main(verbosity=2)