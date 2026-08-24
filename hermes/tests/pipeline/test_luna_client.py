#!/usr/bin/env python3
"""Hermes-only current-model client contracts."""
from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

HERMES = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERMES))


class LunaClientTest(unittest.TestCase):
    def test_command_pins_provider_model_reasoning_and_never_reads_http_keys(self):
        import tools.llm_client as client
        seen = {}

        def fake_run(command, **kwargs):
            seen["command"] = command
            seen["kwargs"] = kwargs
            return subprocess.CompletedProcess(command, 0, '{"selected": []}', "")

        with patch.object(client, "available", return_value=True), \
             patch.object(client, "_log_usage"), patch("subprocess.run", side_effect=fake_run):
            result = client.ask("system", "user")
        self.assertEqual({"selected": []}, result)
        command = seen["command"]
        self.assertEqual("chat", command[1])
        self.assertEqual("-q", command[2])
        self.assertIn("--quiet", command)
        self.assertEqual("tool", command[command.index("--source") + 1])
        self.assertNotIn("--provider", command)
        self.assertNotIn("--model", command)
        self.assertIn("--reasoning", command); self.assertIn("max", command)
        self.assertFalse(seen["kwargs"].get("shell", True))
        source = Path(client.__file__).read_text(encoding="utf-8")
        self.assertNotIn("urllib", source)
        self.assertNotIn("Authorization", source)
        self.assertNotIn("API_KEY", source)

    def test_nonzero_and_timeout_are_fail_open_without_retry(self):
        import tools.llm_client as client
        calls = []

        def nonzero(command, **kwargs):
            calls.append(command)
            return subprocess.CompletedProcess(command, 403, "", "forbidden")

        with patch.object(client, "available", return_value=True), patch.object(client, "_log_usage"), \
             patch("subprocess.run", side_effect=nonzero):
            self.assertIsNone(client.ask("s", "u"))
        self.assertEqual(1, len(calls))

        with patch.object(client, "available", return_value=True), \
             patch.object(client, "_log_usage"), \
             patch("subprocess.run", side_effect=subprocess.TimeoutExpired("hermes", 1)):
            self.assertIsNone(client.ask("s", "u"))

    def test_disabled_mode_does_not_spawn_hermes(self):
        import tools.llm_client as client
        with patch.object(client, "available", return_value=False), \
             patch.object(client, "_log_usage"), \
             patch("subprocess.run") as run:
            self.assertIsNone(client.ask("s", "u"))
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
