#!/usr/bin/env python3
"""RAG package import must not pre-load CLI modules."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np


HERMES = Path(__file__).resolve().parents[2]


class RagPackageImportTest(unittest.TestCase):
    def test_package_import_does_not_preload_module_entrypoints(self):
        proc = subprocess.run(
            [
                sys.executable,
                "-c",
                "import rag,sys; assert 'rag.build_index' not in sys.modules; "
                "assert 'rag.query' not in sys.modules",
            ],
            cwd=HERMES,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)

    def test_embedding_dimension_prefers_current_sentence_transformers_api(self):
        from rag import embedder

        class CurrentModel:
            def get_embedding_dimension(self):
                return 512

        with patch.object(embedder, "_get_model", return_value=CurrentModel()):
            self.assertEqual(512, embedder.get_dim())

    def test_default_rag_paths_follow_the_checkout(self):
        from rag import config

        self.assertEqual(HERMES / "rag" / "data" / "corpus", config.CORPUS_ROOT)
        self.assertEqual(HERMES / "rag" / "index", config.INDEX_DIR)
        self.assertEqual(HERMES / "rag" / "data" / "golden_qa.json", config.GOLDEN_QA_PATH)

    def test_build_index_honors_custom_index_dir(self):
        from rag import build_index
        from rag.chunker import Chunk

        class ReadBack:
            ntotal = 1

        def fake_write_index(_index, path):
            Path(path).write_bytes(b"fake-index")

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "custom-index"
            with patch.object(
                build_index, "chunk_corpus", return_value=[Chunk("x.md", "# X", "body")]
            ), patch.object(
                build_index, "encode_passages", return_value=np.array([[1.0, 0.0]], dtype="float32")
            ), patch.object(build_index, "get_dim", return_value=2), patch.object(
                build_index.faiss, "write_index", side_effect=fake_write_index
            ) as write_index, patch.object(
                build_index.faiss, "read_index", return_value=ReadBack()
            ):
                index_path, metadata_path = build_index.build_index(
                    corpus_root=Path(tmp), subdirs=[], index_dir=output
                )

            self.assertEqual(output / "index.faiss", index_path)
            self.assertEqual(output / "metadata.jsonl", metadata_path)
            self.assertEqual(str(output / "index.faiss.tmp"), write_index.call_args.args[1])
            manifest = json.loads((output / "build_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(1, manifest["schema_version"])
            self.assertEqual(1, manifest["chunk_count"])
            self.assertTrue(manifest["model"]["revision"])
            self.assertIn("numpy", manifest["dependencies"])
            self.assertIn("corpus_sha256", manifest)
            self.assertIn("index_sha256", manifest)
            self.assertIn("metadata_sha256", manifest)
            self.assertTrue(manifest["build_id"])
            self.assertEqual([], list(output.glob("*.tmp")))


if __name__ == "__main__":
    unittest.main(verbosity=2)
