#!/usr/bin/env python3
"""Regression for target-vs-gap selection weighting."""
from __future__ import annotations

import unittest

from tools.find_best_combo import _quality_score


class SelectionWeightRegressionTest(unittest.TestCase):
    def test_target_aligned_candidate_beats_non_green_gap_tradeoff(self):
        targets = [70.0, 55.0, 40.0, 30.0, 20.0]
        target_aligned = [75.0, 55.0, 40.0, 30.0, 20.0]
        gap_favored = [80.0, 63.0, 40.0, 30.0, 20.0]
        self.assertLess(
            _quality_score(target_aligned, targets, "hard"),
            _quality_score(gap_favored, targets, "hard"),
        )


if __name__ == "__main__":
    unittest.main()
