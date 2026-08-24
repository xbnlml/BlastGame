#!/usr/bin/env python3
"""质量分回归：q 必须表示距离理想档位组合的远近。

本测试只验证组合排序，不修改 Judge 的合格/接近/不合格规则。
"""
import math
import os
import sys
import unittest

HERMES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERMES)

from tools.find_best_combo import (
    _experience_gap_error,
    _gap_score,
    _quality_score,
    _quality_target_score,
    find_best_monotonic,
)


class QualityScoreTest(unittest.TestCase):
    def test_exact_target_is_zero_distance(self):
        targets = [85, 85, 65, 50, 50]
        wrs = [85, 85, 65, 50, 50]
        self.assertEqual(0.0, _quality_target_score(wrs, targets, "normal"))
        self.assertEqual(0.0, _gap_score(wrs, "normal", targets))

    def test_gap_surplus_is_distance_not_reward(self):
        targets = [85, 85, 65, 50, 50]
        exact = [85, 85, 65, 50, 50]
        wide = [93.33, 93.33, 65.56, 47.0, 47.0]
        self.assertGreater(_gap_score(wide, "normal", targets), 0.0)
        self.assertGreaterEqual(_gap_score(wide, "normal", targets), _gap_score(exact, "normal", targets))

    def test_low_wr_same_pp_gap_has_larger_experience_distance(self):
        # 20%->10% 的尝试次数比明显大于 90%->80%。
        low = _experience_gap_error(20, 10, 10, 10)
        high = _experience_gap_error(90, 80, 10, 10)
        self.assertGreater(low, high)
        self.assertAlmostEqual(100.0, low, places=6)

    def test_l53_target_closer_combo_beats_overwide_gap(self):
        targets = [85, 85, 65, 50, 50]
        overwide = [93.33, 93.33, 65.56, 47.0, 47.0]
        target_closer = [80.8, 80.8, 65.56, 47.0, 47.0]
        q_overwide = _quality_score(overwide, targets, "normal")
        q_target_closer = _quality_score(target_closer, targets, "normal")
        self.assertLess(q_target_closer, q_overwide)

    def test_gap_remains_primary_over_target_deviation(self):
        targets = [85, 85, 65, 50, 50]
        less_target_error = [74.19, 74.19, 61.84, 54.0, 54.0]
        better_gap = [93.08, 93.08, 74.19, 61.84, 61.84]
        self.assertLess(
            _quality_score(better_gap, targets, "normal"),
            _quality_score(less_target_error, targets, "normal"),
        )

    def test_normal_target_penalty_counts_three_effective_configs(self):
        targets = [85, 85, 65, 50, 50]
        wrs = [90, 90, 65, 50, 50]
        # T1/T2 是同一配置，不应把同一物理配置重复计权。
        self.assertEqual(5.0, _quality_target_score(wrs, targets, "normal"))

    def test_selector_prefers_target_closer_normal_combo(self):
        targets = [85, 85, 65, 50, 50]
        records = [
            {"wr": 93.33, "sd": "23", "sc": 5, "ratios": "10,1,1,1,1", "of": "0.5", "source": "summary", "totalGames": 400},
            {"wr": 80.8, "sd": "20", "sc": 5, "ratios": "1,1,1,1,1", "of": "0.5", "source": "summary", "totalGames": 400},
            {"wr": 65.56, "sd": "17", "sc": 5, "ratios": "1,1,1,10,10", "of": "0.5", "source": "summary", "totalGames": 400},
            {"wr": 47.0, "sd": "40", "sc": 5, "ratios": "0,10,0,10,0", "of": "1.0", "source": "summary", "totalGames": 400},
        ]
        result = find_best_monotonic(records, targets, top_n=1, difficulty="normal")
        self.assertTrue(result)
        q, _, chosen = result[0]
        self.assertAlmostEqual(80.8, chosen[0]["wr"], places=6)
        self.assertLess(q, 40.0)

    def test_hard_exact_target_remains_best(self):
        targets = [70, 55, 40, 30, 20]
        records = []
        for i, wr in enumerate(targets):
            records.append({
                "wr": wr,
                "sd": str(10 + i),
                "sc": 5,
                "ratios": ",".join(str(j + i + 1) for j in range(5)),
                "of": "0.5",
                "source": "summary",
                "totalGames": 400,
            })
        result = find_best_monotonic(records, targets, top_n=1, difficulty="hard")
        self.assertTrue(result)
        q, _, chosen = result[0]
        self.assertEqual(targets, [r["wr"] for r in chosen])
        self.assertAlmostEqual(0.0, q, places=6)


if __name__ == "__main__":
    unittest.main(verbosity=2)
