#!/usr/bin/env python3
"""Legacy stage-data shapes remain readable after three-file pool refresh."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

HERMES = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERMES))


class PoolLegacyShapeTest(unittest.TestCase):
    def test_legacy_empty_list_is_a_valid_empty_pool(self):
        from tools.data import pool

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "stage-data" / "89"
            root.mkdir(parents=True)
            (root / "89.json").write_text("[]", encoding="utf-8")
            with patch.object(pool, "STAGE_DIR", str(Path(tmp) / "stage-data")):
                self.assertEqual([], pool.get_all_records("89"))

    def test_legacy_list_records_are_reliable_records(self):
        from tools.data import pool

        record = {
            "wr": 72.5, "sd": "10", "sc": "5", "ratios": "1,1,1,1,1",
            "of": "0.5", "source": "phase0", "totalGames": 400,
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "stage-data" / "89"
            root.mkdir(parents=True)
            (root / "89.json").write_text(json.dumps([record]), encoding="utf-8")
            with patch.object(pool, "STAGE_DIR", str(Path(tmp) / "stage-data")):
                self.assertEqual([record], pool.get_all_records("89"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
