#!/usr/bin/env python3
"""Contracts for the shared Hermes Planner campaign client."""
from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import llm_client


class LlmClientSharedSessionTest(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.state_path = str(Path(self.tempdir.name) / "planner_session.json")
        self.state_patch = patch.object(llm_client, "PLANNER_SESSION_STATE", self.state_path)
        self.state_patch.start()
        llm_client.configure_campaign("campaign-test", load_saved=False)

    def tearDown(self):
        llm_client.reset_campaign_for_test()
        self.state_patch.stop()
        self.tempdir.cleanup()

    def test_first_call_creates_one_tool_session(self):
        response = subprocess.CompletedProcess(
            ["hermes"], 0, '{"selected": []}', "\nsession_id: 20260821_120000_abcdef\n"
        )
        with patch.object(llm_client.subprocess, "run", return_value=response) as run, \
             patch.object(llm_client, "_log_usage"):
            result = llm_client._ask_via_hermes("system", "user", None, True, "probe")

        self.assertEqual({"selected": []}, result)
        command = run.call_args.args[0]
        self.assertEqual(["hermes", "chat", "-q"], command[:3])
        self.assertIn("--quiet", command)
        self.assertEqual("tool", command[command.index("--source") + 1])
        self.assertNotIn("--resume", command)
        self.assertIn("--continue", command)
        self.assertIn("--create-if-missing", command)
        self.assertEqual("20260821_120000_abcdef", llm_client.session_id())
        saved = json.loads(Path(self.state_path).read_text(encoding="utf-8"))
        self.assertEqual("20260821_120000_abcdef", saved["session_id"])

    def test_next_call_resumes_the_same_session(self):
        first = subprocess.CompletedProcess(
            ["hermes"], 0, '{"selected": []}', "session_id: 20260821_120000_abcdef\n"
        )
        second = subprocess.CompletedProcess(
            ["hermes"], 0, '{"selected": []}', "session_id: 20260821_120000_abcdef\n"
        )
        with patch.object(llm_client.subprocess, "run", side_effect=[first, second]) as run, \
             patch.object(llm_client, "_log_usage"):
            llm_client._ask_via_hermes("system", "first", None, True, "probe")
            llm_client._ask_via_hermes("system", "second", None, True, "probe")

        self.assertEqual(2, run.call_count)
        second_command = run.call_args_list[1].args[0]
        self.assertEqual(
            "20260821_120000_abcdef",
            second_command[second_command.index("--resume") + 1],
        )

    def test_saved_session_from_another_campaign_is_not_reused(self):
        Path(self.state_path).write_text(json.dumps({
            "campaign_id": "old-campaign",
            "session_id": "20260821_120000_saved",
        }), encoding="utf-8")
        llm_client.reset_campaign_for_test()
        llm_client.configure_campaign("new-campaign")
        self.assertIsNone(llm_client.session_id())
        self.assertEqual("new-campaign", llm_client.campaign_id())

    def test_timeout_keeps_named_continuation_for_next_call(self):
        timeout = subprocess.TimeoutExpired(["hermes"], 120, output="", stderr="")
        success = subprocess.CompletedProcess(
            ["hermes"], 0, '{"selected": []}', "session_id: 20260821_120000_named\n"
        )
        with patch.object(llm_client.subprocess, "run", side_effect=[timeout, success]) as run, \
             patch.object(llm_client, "_log_usage"):
            self.assertIsNone(llm_client._ask_via_hermes("system", "first", None, True, "probe"))
            llm_client._ask_via_hermes("system", "second", None, True, "probe")

        second_command = run.call_args_list[1].args[0]
        self.assertIn("--continue", second_command)
        self.assertIn("--create-if-missing", second_command)
        self.assertNotIn("--resume", second_command)

    def test_nonzero_without_session_id_fails_open_without_retry(self):
        response = subprocess.CompletedProcess(["hermes"], 1, "", "provider error")
        with patch.object(llm_client.subprocess, "run", return_value=response) as run, \
             patch.object(llm_client, "_log_usage"):
            result = llm_client._ask_via_hermes("system", "user", None, True, "probe")

        self.assertIsNone(result)
        self.assertEqual(1, run.call_count)

    def test_session_id_parser_accepts_bytes(self):
        self.assertEqual(
            "20260821_120002_cafebabe",
            llm_client._extract_session_id(b"session_id: 20260821_120002_cafebabe\r\n"),
        )


if __name__ == "__main__":
    unittest.main()
