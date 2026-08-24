#!/usr/bin/env python3
"""Role manifest contracts stay explicit and do not consume legacy memory."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

HERMES = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERMES))


class RoleContractTest(unittest.TestCase):
    def test_all_role_manifests_are_valid(self):
        from tools.pipeline.role_contract import ROLE_NAMES, load_all_role_contracts

        contracts = load_all_role_contracts()
        self.assertEqual(set(ROLE_NAMES), set(contracts))
        for role, contract in contracts.items():
            self.assertEqual(role, contract["role"])
            self.assertTrue(contract["manifest_hash"].startswith("MAN-"))
            self.assertNotIn("memory_path", contract)

    def test_invalid_llm_failure_policy_is_rejected(self):
        from tools.pipeline.role_contract import RoleContractError, load_role_contract

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = root / "agents" / "planner" / "manifest.json"
            manifest.parent.mkdir(parents=True)
            manifest.write_text(json.dumps({
                "schema_version": 1,
                "role": "planner",
                "version": "planner-test-v1",
                "mode": "llm_advisor",
                "input_allowlist": ["candidate_catalog"],
                "output_schema": "PROBE_DECISION_V3",
                "forbidden": ["asset_write"],
                "failure_policy": "fail_closed",
                "memory_policy": "approved_lessons_only",
                "policy_refs": ["project-state/rules.json"],
            }), encoding="utf-8")
            with self.assertRaises(RoleContractError):
                load_role_contract("planner", root=root)


if __name__ == "__main__":
    unittest.main(verbosity=2)
