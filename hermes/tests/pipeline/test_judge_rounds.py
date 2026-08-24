#!/usr/bin/env python3
"""Judge round-budget regression contracts."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

HERMES = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERMES))


class JudgeRoundBudgetTest(unittest.TestCase):
    def test_close_consumes_round_and_hits_max_budget(self):
        from tools import judge_level

        records = []
        for index, wr in enumerate([50.5, 34.2, 28.8, 13.5, 9.3], start=1):
            records.append({
                "level": "128",
                "slot": f"T{index}",
                "tier": index,
                "board_fingerprint": "board-128",
                "deal_fingerprint": f"deal-128-{index}",
                "sd": str(index * 10),
                "sc": "5",
                "ratios": f"{index},1,1,1,1",
                "of": "0.5",
                "wr": wr,
                "totalGames": 400,
                "source": "summary",
                "created_at": "2026-08-21T00:00:00+00:00",
            })

        with tempfile.TemporaryDirectory() as temp:
            rounds_file = str(Path(temp) / "rounds.json")
            with patch.object(judge_level, "ROUNDS_FILE", rounds_file):
                results = [
                    judge_level.judge_with_rounds(128, records_override=records)
                    for _ in range(6)
                ]

            self.assertEqual(["接近"] * 6, [item[1] for item in results])
            self.assertEqual([1, 2, 3, 4, 5, 6], [item[3]["round"] for item in results])
            self.assertEqual(
                ["继续调优(接近)"] * 5 + ["改关卡"],
                [item[3]["action"] for item in results],
            )
            self.assertEqual({"128": 6}, json.loads(Path(rounds_file).read_text(encoding="utf-8")))


if __name__ == "__main__":
    unittest.main(verbosity=2)
