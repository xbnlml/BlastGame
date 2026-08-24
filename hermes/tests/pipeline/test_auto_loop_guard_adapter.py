#!/usr/bin/env python3
"""Legacy auto_loop Phase-3 adapter must be fail-closed before Unity submission."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

HERMES = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERMES))


class Log:
    def __init__(self):
        self.lines = []

    def log(self, message):
        self.lines.append(message)


class RecordingRunner:
    def __init__(self):
        self.calls = 0
        self.last_request = None

    def run(self, request):
        self.calls += 1
        self.last_request = request
        return {"status": "submitted", "request": request}


def probes(duplicate=False):
    p = {
        "60": {
            "P1": {"sd": 5, "sc": 5, "ratios": "1,1,1,1,1", "of": 0.0},
            "P2": {"sd": 8, "sc": 5, "ratios": "1,1,1,1,10", "of": 0.1},
            "P3": {"sd": 12, "sc": 5, "ratios": "1,1,10,1,1", "of": 0.25},
            "P4": {"sd": 16, "sc": 5, "ratios": "1,10,1,1,1", "of": 0.45},
            "P5": {"sd": 20, "sc": 5, "ratios": "10,1,1,1,1", "of": 0.6},
        }
    }
    if duplicate:
        p["60"]["P2"] = dict(p["60"]["P1"])
    return p


class AutoLoopGuardAdapterTest(unittest.TestCase):
    def invoke(self, *, preflight, warden, probe_map, runner, decision_metadata=None):
        from scripts.auto_loop import phase_submit_guarded
        return phase_submit_guarded(
            Log(), ["60"], [1, 2, 3, 4, 5], probe_map,
            games=400, strategy="scoring_opt_vg", adaptive_stop=False,
            round_num=1, preflight_fn=preflight, warden_fn=warden,
            runner=runner, run_id="test-run", decision_metadata=decision_metadata,
        )

    def test_preflight_failure_starts_unity_zero_times(self):
        runner = RecordingRunner()
        ok = self.invoke(
            preflight=lambda _request: {"returncode": 1, "stdout": "broken"},
            warden=lambda _request: (True, ""), probe_map=probes(), runner=runner,
        )
        self.assertFalse(ok)
        self.assertEqual(0, runner.calls)

    def test_warden_failure_starts_unity_zero_times(self):
        runner = RecordingRunner()
        ok = self.invoke(
            preflight=lambda _request: {"returncode": 0},
            warden=lambda _request: (False, "W06 hash mismatch"),
            probe_map=probes(), runner=runner,
        )
        self.assertFalse(ok)
        self.assertEqual(0, runner.calls)

    def test_w09_duplicate_probe_starts_unity_zero_times(self):
        runner = RecordingRunner()
        ok = self.invoke(
            preflight=lambda _request: {"returncode": 0},
            warden=lambda _request: (True, ""), probe_map=probes(duplicate=True), runner=runner,
        )
        self.assertFalse(ok)
        self.assertEqual(0, runner.calls)

    def test_missing_probe_level_starts_unity_zero_times(self):
        runner = RecordingRunner()
        ok = self.invoke(
            preflight=lambda _request: {"returncode": 0},
            warden=lambda _request: (True, ""), probe_map={}, runner=runner,
        )
        self.assertFalse(ok)
        self.assertEqual(0, runner.calls)

    def test_all_guards_pass_starts_unity_once(self):
        runner = RecordingRunner()
        ok = self.invoke(
            preflight=lambda _request: {"returncode": 0},
            warden=lambda _request: (True, ""), probe_map=probes(), runner=runner,
        )
        self.assertTrue(ok)
        self.assertEqual(1, runner.calls)
        request = runner.last_request
        self.assertTrue(request["require_decision_provenance"])
        self.assertEqual("deterministic_planner", request["decision_provenance"]["60"]["decision_source"])
        self.assertTrue(request["decision_provenance"]["60"]["decision_id"].startswith("DEC-"))

    def test_decision_config_tamper_blocks_before_unity(self):
        from tools.pipeline.provenance import build_decision_provenance

        original = probes()["60"]
        provenance = build_decision_provenance(
            level="60", round_num=1, probes=original,
            metadata={"decision_source": "llm_original", "selected_candidate_ids": ["C1", "C2", "C3", "C4", "C5"], "actual_llm_calls": 1},
        )
        tampered = probes()
        tampered["60"]["P1"] = dict(tampered["60"]["P1"], sd=99)
        runner = RecordingRunner()
        ok = self.invoke(
            preflight=lambda _request: {"returncode": 0},
            warden=lambda _request: (True, ""),
            probe_map=tampered,
            runner=runner,
            decision_metadata={"60": {"decision_provenance": provenance}},
        )
        self.assertFalse(ok)
        self.assertEqual(0, runner.calls)


if __name__ == "__main__":
    unittest.main(verbosity=2)
