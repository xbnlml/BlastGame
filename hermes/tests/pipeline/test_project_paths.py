#!/usr/bin/env python3
"""Portable Unity workspace path resolution contracts."""
from __future__ import annotations

import tempfile
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

HERMES = Path(__file__).resolve().parents[2]


class ProjectPathsTest(unittest.TestCase):
    def test_repository_text_has_no_personal_machine_paths(self):
        forbidden = (
            "C:\\Users\\Administrator",
            "C:/" + "Users/Administrator",
            "D:\\download\\BlastGame",
            "D:/" + "download/BlastGame",
        )
        findings = []
        for suffix in ("*.md", "*.py", "*.mjs"):
            for path in HERMES.rglob(suffix):
                text = path.read_text(encoding="utf-8", errors="replace")
                if any(token in text for token in forbidden):
                    findings.append(path.relative_to(HERMES).as_posix())
        self.assertEqual([], sorted(findings))

    def test_environment_override_wins(self):
        from tools.project_paths import resolve_unity_repo

        with tempfile.TemporaryDirectory() as tmp:
            explicit = Path(tmp) / "explicit"
            resolved = resolve_unity_repo(
                hermes_dir=Path(tmp) / "checkout" / "hermes",
                environ={"BLASTGAME_REPO": str(explicit)},
                home=Path(tmp) / "home",
            )
            self.assertEqual(explicit.resolve(), resolved)

    def test_discovers_repo_parent_or_current_users_documents(self):
        from tools.project_paths import resolve_unity_repo

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            checkout = root / "checkout"
            hermes = checkout / "hermes"
            (checkout / "Assets").mkdir(parents=True)
            (checkout / "ProjectSettings").mkdir()
            (checkout / "ProjectSettings" / "ProjectVersion.txt").write_text("m_EditorVersion: test")
            self.assertEqual(checkout.resolve(), resolve_unity_repo(hermes, {}, root / "home"))

            (checkout / "ProjectSettings" / "ProjectVersion.txt").unlink()
            live = root / "home" / "Documents" / "BlastGame"
            (live / "Assets").mkdir(parents=True)
            (live / "ProjectSettings").mkdir()
            (live / "ProjectSettings" / "ProjectVersion.txt").write_text("m_EditorVersion: test")
            self.assertEqual(live.resolve(), resolve_unity_repo(hermes, {}, root / "home"))

    def test_missing_live_workspace_falls_back_to_checkout_root(self):
        from tools.project_paths import resolve_unity_repo

        with tempfile.TemporaryDirectory() as tmp:
            hermes = Path(tmp) / "checkout" / "hermes"
            hermes.mkdir(parents=True)
            self.assertEqual(hermes.parent.resolve(), resolve_unity_repo(hermes, {}, Path(tmp) / "home"))

    def test_live_tools_derive_every_path_from_the_same_explicit_workspace(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "portable-unity"
            env = os.environ.copy()
            env["BLASTGAME_REPO"] = str(workspace)
            probe = (
                "import json; "
                "from tools import compare_asset_snapshots as a, compare_level_db as c, verify_asset_db_match as v, pipeline_stats as p, stage_status as s; "
                "print(json.dumps({'workspace':[a.OPT_DIR,c.RUN_PATH,c.ASSET_ROOT,v.RUN_PATH,v.ASSET_ROOT,p.OPT_ROOT,s.TARGETS],"
                "'helpers':[c.FP_HELPER,v.FP_HELPER]}))"
            )
            result = subprocess.run(
                [sys.executable, "-c", probe],
                cwd=HERMES,
                env=env,
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertEqual(0, result.returncode, result.stderr)
            paths = json.loads(result.stdout)
            for value in paths["workspace"]:
                with self.subTest(path=value):
                    path = Path(value).resolve()
                    self.assertTrue(path == workspace.resolve() or workspace.resolve() in path.parents)
            for value in paths["helpers"]:
                with self.subTest(helper=value):
                    self.assertTrue(Path(value).resolve().is_relative_to(HERMES.resolve()))

            node = subprocess.run(
                [
                    "node",
                    "--input-type=module",
                    "-e",
                    "import { resolveRepo } from './tools/leveldb_sync/repo_paths.mjs'; console.log(resolveRepo())",
                ],
                cwd=HERMES,
                env=env,
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertEqual(0, node.returncode, node.stderr)
            self.assertEqual(workspace.resolve(), Path(node.stdout.strip()).resolve())


if __name__ == "__main__":
    unittest.main(verbosity=2)
