#!/usr/bin/env python3
"""Approved planner lessons are filtered, stable, and never read from memory.md."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERMES = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERMES))


def entry(entry_id, *, role="planner", status="active", level="176", difficulty="normal",
          logic_version="logic-v1", evidence=True, expires_at=None, note=None):
    return {
        "entry_id": entry_id,
        "role": role,
        "status": status,
        "logic_version": logic_version,
        "evidence_refs": ["run-1/event-1"] if evidence else [],
        "applicable_when": {"level": level, "difficulty": difficulty},
        "observation": note or f"observation-{entry_id}",
        "recommendation": f"recommendation-{entry_id}",
        "confidence": 0.8,
        "created_at": "2026-08-20T10:00:00+00:00",
        "expires_at": expires_at,
    }


class ApprovedLessonsTest(unittest.TestCase):
    def write_lessons(self, root, rows):
        path = root / "project-state" / "approved_lessons" / "planner.jsonl"
        path.parent.mkdir(parents=True)
        path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
        return path

    def test_filters_role_status_scope_evidence_and_expiry(self):
        from tools.pipeline.approved_lessons import load_approved_lessons

        expired = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        rows = [
            entry("good"),
            entry("inactive", status="proposed"),
            entry("wrong-role", role="warden"),
            entry("wrong-level", level="136"),
            entry("no-evidence", evidence=False),
            entry("expired", expires_at=expired),
            entry("wildcard", logic_version="*", level="*", difficulty="*"),
            entry("wrong-logic", logic_version="logic-old"),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_lessons(root, rows)
            result = load_approved_lessons(
                "planner", root=root, level="176", difficulty="normal", logic_version="logic-v1",
                enabled=True, limit=8,
            )
        self.assertEqual(["good", "wildcard"], [row["entry_id"] for row in result["entries"]])
        self.assertTrue(result["snapshot_hash"].startswith("LES-"))
        self.assertEqual("ok", result["status"])

    def test_disabled_and_missing_file_are_empty_without_reading_legacy_memory(self):
        from tools.pipeline.approved_lessons import load_approved_lessons

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            memory = root / "agents" / "planner" / "memory.md"
            memory.parent.mkdir(parents=True)
            memory.write_text("SECRET-OLD-MEMORY-SENTINEL", encoding="utf-8")
            disabled = load_approved_lessons("planner", root=root, level="176", enabled=False)
            missing = load_approved_lessons("planner", root=root, level="176", enabled=True)
        self.assertEqual([], disabled["entries"])
        self.assertEqual("disabled", disabled["status"])
        self.assertEqual([], missing["entries"])
        self.assertEqual("missing", missing["status"])
        self.assertNotIn("SECRET-OLD-MEMORY-SENTINEL", json.dumps(missing))

    def test_duplicate_entry_id_is_not_loaded(self):
        from tools.pipeline.approved_lessons import load_approved_lessons

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_lessons(root, [entry("dup", note="a"), entry("dup", note="b"), entry("good")])
            result = load_approved_lessons("planner", root=root, level="176", enabled=True)
        self.assertEqual(["good"], [row["entry_id"] for row in result["entries"]])
        self.assertIn("duplicate_entry_id:dup", result["diagnostics"])

    def test_context_v3_includes_lessons_only_when_explicitly_enabled(self):
        from tools.pipeline.probe_decision import build_candidate_catalog, build_context_v3

        snapshot = {
            "level": "176", "board_fingerprint": "board", "logic_version": "logic-v1",
            "verified": [], "phase1": [], "phase2": [], "generated": [],
        }
        catalog = build_candidate_catalog(snapshot)
        base = build_context_v3(snapshot, catalog)
        enabled = build_context_v3(snapshot, catalog, approved_lessons=[{"entry_id": "good"}])
        self.assertNotIn("approved_lessons", base)
        self.assertEqual([{"entry_id": "good"}], enabled["approved_lessons"])
        self.assertNotEqual(base["context_hash"], enabled["context_hash"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
