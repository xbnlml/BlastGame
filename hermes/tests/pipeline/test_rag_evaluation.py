#!/usr/bin/env python3
"""RAG evaluation must measure current-source retrieval, not generic words."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class RagEvaluationContractTest(unittest.TestCase):
    def test_wrong_source_keyword_and_archive_do_not_count_as_hits(self):
        from rag.eval import _hit

        self.assertFalse(
            _hit(
                {"source": "MainGame/Unrelated.md", "text": "这里也包含玩法规则"},
                "Gameplay_Rules",
                "规则",
            )
        )
        self.assertTrue(
            _hit(
                {"source": "MainGame/Gameplay_Rules_Logic.md", "text": "正文"},
                "Gameplay_Rules",
                "规则",
            )
        )
        self.assertFalse(
            _hit(
                {"source": "MainGame/archive/Gameplay_Rules_Archive.md", "text": "规则"},
                "Gameplay_Rules",
                "规则",
            )
        )

    def test_chunker_excludes_archive_directories(self):
        from rag.chunker import chunk_corpus

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            current = root / "MainGame" / "current.md"
            archived = root / "MainGame" / "archive" / "old.md"
            current.parent.mkdir(parents=True)
            archived.parent.mkdir(parents=True)
            current.write_text("# Current\ncurrent text", encoding="utf-8")
            archived.write_text("# Old\narchived text", encoding="utf-8")
            chunks = chunk_corpus(root, ["MainGame"])
        self.assertEqual(["MainGame/current.md"], [chunk.source for chunk in chunks])

    def test_ops_chunks_are_marked_as_historical_records(self):
        from rag.chunker import chunk_corpus

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "Ops" / "incident.md"
            path.parent.mkdir(parents=True)
            path.write_text("# Incident\nold rule text", encoding="utf-8")
            chunks = chunk_corpus(root, ["Ops"])
        self.assertEqual(1, len(chunks))
        self.assertTrue(chunks[0].text.startswith("[历史复盘]"))
        self.assertIn("project-state/rules.json", chunks[0].text)

    def test_checked_in_rag_corpus_passes_safety_gate(self):
        from rag import config
        from rag.safety import scan_corpus

        self.assertEqual([], scan_corpus(config.CORPUS_ROOT, config.CORPUS_SUBDIRS))

    def test_positive_recall_and_negative_rejection_are_reported_separately(self):
        from rag.eval import evaluate
        from rag.query import Hit

        qa = [
            {"question": "correct", "expected_source": "Right", "expected_keyword": "规则"},
            {"question": "wrong", "expected_source": "Right", "expected_keyword": "规则"},
            {"question": "negative", "expected_source": "__NONE__", "expected_keyword": "__NONE__"},
        ]

        def fake_search(question, top_k, threshold):
            if question == "correct":
                return [Hit(0.9, "MainGame/Right_Logic.md", "", "正文")]
            if question == "wrong":
                return [Hit(0.9, "MainGame/Wrong.md", "", "也有规则")]
            return []

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "qa.json"
            path.write_text(json.dumps(qa, ensure_ascii=False), encoding="utf-8")
            with patch("rag.eval.search", side_effect=fake_search):
                result = evaluate(path, top_k_values=(1,))

        self.assertEqual(2, result["n"])
        self.assertEqual(0.5, result["recall"][1])
        self.assertEqual(1, result["negative"]["n"])
        self.assertEqual(1.0, result["negative"]["rejection_rate"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
