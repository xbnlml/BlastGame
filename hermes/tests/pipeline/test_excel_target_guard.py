#!/usr/bin/env python3
"""Excel is the only target source for V3 judgment."""
from __future__ import annotations

import sys
import unittest
from unittest.mock import patch
from pathlib import Path

HERMES = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERMES))


class ExcelTargetGuardTest(unittest.TestCase):
    def test_missing_excel_target_blocks_before_pool_or_round_mutation(self):
        from tools import judge_level
        with patch.object(judge_level.et, "get_target", return_value=None), \
             patch.object(judge_level, "load_stage_data", side_effect=AssertionError("pool must not be read")), \
             patch.object(judge_level, "inc_round", side_effect=AssertionError("round must not mutate")), \
             patch.object(judge_level, "reset_round", side_effect=AssertionError("round must not mutate")), \
             patch.object(judge_level, "get_round", return_value=2):
            combo, result, reasons, info = judge_level.judge_with_rounds(60)
        self.assertIsNone(combo)
        self.assertEqual("ERROR_BLOCKED", result)
        self.assertEqual(["Excel target missing for L60"], reasons)
        self.assertEqual({"round": 2, "max": 6, "action": "blocked_missing_excel_target"}, info)

    def test_local_combo_selector_refuses_default_target_fallback(self):
        from tools.judge_level import find_best_combo
        with self.assertRaisesRegex(ValueError, "Excel target"):
            find_best_combo([], "normal", targets=None)


if __name__ == "__main__":
    unittest.main(verbosity=2)
