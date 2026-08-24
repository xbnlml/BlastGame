#!/usr/bin/env python3
"""Production Coordinator/Guard entry contracts; all blocks must be fail-closed."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

HERMES = Path(__file__).resolve().parents[2]
FIXTURES = HERMES / "tests" / "fixtures"
sys.path.insert(0, str(HERMES))


class RecordingRunner:
    def __init__(self) -> None:
        self.calls = 0

    def run(self, request: dict) -> dict:
        self.calls += 1
        return {
            "status": "submitted", "run_id": request["run_id"],
            "attempt_id": request["attempt_id"], "receipt_id": "receipt-001",
        }


def valid_probe_request() -> dict:
    return {
        "run_id": "run-guard-contract", "attempt_id": "attempt-001", "levels": ["60"],
        "probes": {"60": {
            "P1": {"sd": 5, "sc": 5, "ratios": "1,1,1,1,1", "of": 0.0},
            "P2": {"sd": 8, "sc": 5, "ratios": "1,1,1,1,10", "of": 0.1},
            "P3": {"sd": 12, "sc": 5, "ratios": "1,1,10,1,1", "of": 0.25},
            "P4": {"sd": 16, "sc": 5, "ratios": "1,10,1,1,1", "of": 0.45},
            "P5": {"sd": 20, "sc": 5, "ratios": "10,1,1,1,1", "of": 0.6},
        }},
    }


class GuardEntrypointContractTest(unittest.TestCase):
    def test_production_entry_starts_unity_once_when_preflight_and_guards_pass(self):
        from tools.pipeline.control import build_production_coordinator

        runner = RecordingRunner()
        coordinator = build_production_coordinator(
            runner=runner, preflight=lambda _request: {"returncode": 0, "stdout": "ok"}
        )
        receipt = coordinator.run(valid_probe_request())
        self.assertEqual("submitted", receipt["status"])
        self.assertEqual(1, runner.calls)

    def test_real_w09_duplicate_probe_blocks_before_unity_start(self):
        from tools.pipeline.control import PipelineBlocked, build_production_coordinator

        request = valid_probe_request()
        request["probes"]["60"]["P2"] = dict(request["probes"]["60"]["P1"])
        runner = RecordingRunner()
        coordinator = build_production_coordinator(
            runner=runner, preflight=lambda _request: {"returncode": 0, "stdout": "ok"}
        )
        with self.assertRaises(PipelineBlocked) as caught:
            coordinator.run(request)
        self.assertIn("W09", caught.exception.code)
        self.assertEqual(0, runner.calls)

    def test_preflight_nonzero_or_exception_blocks_before_unity_start(self):
        from tools.pipeline.control import PipelineBlocked, build_production_coordinator

        for name, preflight in (
            ("nonzero", lambda _request: {"returncode": 1, "stdout": "bad config"}),
            ("exception", lambda _request: (_ for _ in ()).throw(RuntimeError("preflight crashed"))),
        ):
            with self.subTest(name=name):
                runner = RecordingRunner()
                coordinator = build_production_coordinator(runner=runner, preflight=preflight)
                with self.assertRaises(PipelineBlocked):
                    coordinator.run(valid_probe_request())
                self.assertEqual(0, runner.calls)

    def test_guard_exception_is_fail_closed(self):
        from tools.pipeline.control import Coordinator, PipelineBlocked

        runner = RecordingRunner()
        coordinator = Coordinator(
            runner=runner, preflight=lambda _request: {"returncode": 0},
            guards=[lambda _request: (_ for _ in ()).throw(RuntimeError("guard crashed"))],
        )
        with self.assertRaises(PipelineBlocked):
            coordinator.run(valid_probe_request())
        self.assertEqual(0, runner.calls)

    def test_l138_asset_db_health_fixture_blocks_before_unity_start(self):
        from tools.pipeline.control import PipelineBlocked, build_production_coordinator

        health = json.loads((FIXTURES / "asset_db_mismatch_l138" / "system_health.json").read_text(encoding="utf-8"))
        runner = RecordingRunner()
        coordinator = build_production_coordinator(
            runner=runner, preflight=lambda _request: {"returncode": 0},
        )
        request = valid_probe_request() | {"system_health": health}
        with self.assertRaises(PipelineBlocked) as caught:
            coordinator.run(request)
        self.assertIn("asset_db_fingerprint_mismatch", caught.exception.code)
        self.assertEqual(0, runner.calls)


if __name__ == "__main__":
    unittest.main(verbosity=2)