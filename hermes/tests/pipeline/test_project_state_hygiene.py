#!/usr/bin/env python3
"""Regression checks for public workflow-state semantics."""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path


HERMES = Path(__file__).resolve().parents[2]
BOARD = HERMES / "project-state" / "board.md"
TIMELINE = HERMES / "project-state" / "timeline.md"
ROUNDS = HERMES / "project-state" / "_rounds.json"
WARDEN_MEMORY = HERMES / "agents" / "warden" / "memory.md"
CURATOR_MEMORY = HERMES / "agents" / "curator" / "memory.md"



class ProjectStateHygieneTest(unittest.TestCase):
    def _rows(self):
        rows = {}
        for line in BOARD.read_text(encoding="utf-8").splitlines():
            match = re.match(
                r"^\|\s*(\d{2,3})\s*\|\s*([^|]+)\|\s*([^|]+)\|\s*([^|]+)\|\s*([^|]+)\|\s*([^|]+)\|",
                line,
            )
            if match:
                rows[int(match.group(1))] = [part.strip() for part in match.groups()[1:]]
        return rows

    def test_board_has_one_current_row_per_level(self):
        board = BOARD.read_text(encoding="utf-8")
        rows = self._rows()
        self.assertEqual(set(range(51, 201)), set(rows))
        board_date = re.search(r"\*\*最后更新：\*\*\s*(\d{4}-\d{2}-\d{2})", board)
        timeline_dates = re.findall(
            r"^(\d{4}-\d{2}-\d{2})\s*\|",
            TIMELINE.read_text(encoding="utf-8"),
            flags=re.MULTILINE,
        )
        self.assertIsNotNone(board_date)
        self.assertTrue(timeline_dates)
        self.assertEqual(max(timeline_dates), board_date.group(1))
        self.assertNotIn("已入库 99 关", board)


    def test_imported_levels_have_no_round_budget(self):
        rows = self._rows()
        imported = {level for level, row in rows.items() if row[1] == "✅已入库"}
        rounds = {int(level): value for level, value in json.loads(ROUNDS.read_text()).items()}
        self.assertEqual(set(), imported & set(rounds))
        self.assertTrue(all(0 <= int(value) <= 6 for value in rounds.values()))

    def test_curator_parser_bugs_do_not_survive_as_agent_facts(self):
        warden = WARDEN_MEMORY.read_text(encoding="utf-8")
        curator = CURATOR_MEMORY.read_text(encoding="utf-8")
        self.assertNotRegex(warden, r"- 监督发现违规:.*阶段顺序异常")
        self.assertNotIn("### 本轮结果", curator)
        self.assertNotIn("- 通过入库:", curator)


if __name__ == "__main__":
    unittest.main(verbosity=2)
