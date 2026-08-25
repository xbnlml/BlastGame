#!/usr/bin/env python3
"""Hermetic checks for the public offline replay entry point."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


HERMES = Path(__file__).resolve().parents[2]
DEMO = HERMES / "scripts" / "demo.py"
FIXTURE = HERMES / "tests" / "fixtures" / "demo_replay.json"
EVIDENCE_SHA = "78118aee52e0571177f5df459bb4e64d87cef320283521037b1ac9c5aa9505be"


class OfflineDemoTest(unittest.TestCase):
    def _run(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(DEMO), *args],
            cwd=HERMES,
            capture_output=True,
            text=True,
            timeout=60,
            env={
                **os.environ,
                "PYTHONDONTWRITEBYTECODE": "1",
                "BLASTGAME_REPO": str(HERMES / "__missing_unity_project__"),
            },
        )

    def test_default_demo_replays_checked_in_evidence_without_unity(self):
        proc = self._run()
        self.assertEqual(0, proc.returncode, proc.stderr)
        self.assertIn("OFFLINE REPLAY PASS: 4/4 levels", proc.stdout)
        self.assertIn(f"evidence_sha256={EVIDENCE_SHA}", proc.stdout)
        self.assertTrue(all(f"| L{level} " in proc.stdout for level in (86, 108, 119, 122)))
        self.assertIn("| L86 | normal | 8 | 2090 |", proc.stdout)
        self.assertIn("81.67/81.67/62.7/51.5/51.5 | 接近 | PASS", proc.stdout)
        self.assertIn("84.55/84.55/63.78/49.5/49.5 | 合格 | PASS", proc.stdout)
        self.assertNotIn("Traceback", proc.stdout + proc.stderr)

    def test_missing_fixture_returns_nonzero(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = self._run("--fixture", str(Path(tmp) / "missing.json"))
        self.assertNotEqual(0, proc.returncode)
        self.assertIn("fixture", (proc.stdout + proc.stderr).lower())

    def test_tampered_expected_result_returns_nonzero(self):
        data = json.loads(FIXTURE.read_text(encoding="utf-8"))
        data["levels"][0]["expected"]["wrs"][0] += 1.0
        with tempfile.TemporaryDirectory() as tmp:
            tampered = Path(tmp) / "tampered.json"
            tampered.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            proc = self._run("--fixture", str(tampered))
        self.assertEqual(1, proc.returncode, proc.stdout + proc.stderr)
        self.assertIn("OFFLINE REPLAY FAIL", proc.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
