"""Byte-bound source audit inventory in checkout and source-only release trees."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from source_audit_inventory import source_inventory, production_python_sources


ROOT = Path(__file__).resolve().parents[1]


class SourceAuditInventoryTests(unittest.TestCase):
    def tearDown(self):
        source_inventory.cache_clear()

    def test_checkout_excludes_untracked_files_and_nested_worktrees(self):
        self.assertIn(Path("bot.py"), source_inventory(ROOT))
        self.assertNotIn(Path("untracked_injected.py"), source_inventory(ROOT))
        self.assertTrue(all(".worktrees" not in p.parts for p in source_inventory(ROOT)))
        self.assertTrue(any(p == Path("runtime/production_runtime.py")
                            for p, _ in production_python_sources(ROOT)))

    def _stage(self, folder: Path):
        stage = folder / "release"
        tree = stage / "tree"
        tree.mkdir(parents=True)
        (tree / "bot.py").write_text("pass\n", encoding="utf-8")
        (tree / "charge_controller.py").write_text("pass\n", encoding="utf-8")
        records = [{"path": p} for p in ("bot.py", "charge_controller.py")]
        manifest = json.dumps({"files": records}, sort_keys=True).encode()
        (stage / "RELEASE_MANIFEST.json").write_bytes(manifest)
        (stage / "STAGED_OK").write_text(json.dumps({
            "tree_verified": True,
            "manifest_sha256": hashlib.sha256(manifest).hexdigest(),
        }), encoding="utf-8")
        return tree

    def test_verified_source_only_tree_uses_manifest_not_git(self):
        with tempfile.TemporaryDirectory() as d:
            tree = self._stage(Path(d))
            self.assertEqual(
                (Path("bot.py"), Path("charge_controller.py")),
                source_inventory(tree),
            )

    def test_missing_stage_marker_is_not_accepted(self):
        with tempfile.TemporaryDirectory() as d:
            tree = self._stage(Path(d))
            (tree.parent / "STAGED_OK").unlink()
            with self.assertRaisesRegex(RuntimeError, "source audit requires"):
                source_inventory(tree)

    def test_modified_manifest_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            tree = self._stage(Path(d))
            (tree.parent / "RELEASE_MANIFEST.json").write_text(
                '{"files":[]}', encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "verification"):
                source_inventory(tree)

    def test_missing_and_symlinked_source_are_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            tree = self._stage(Path(d))
            (tree / "bot.py").unlink()
            with self.assertRaisesRegex(RuntimeError, "unsafe source"):
                source_inventory(tree)
            source_inventory.cache_clear()
            (tree / "bot.py").symlink_to(tree / "charge_controller.py")
            with self.assertRaisesRegex(RuntimeError, "unsafe source"):
                source_inventory(tree)

    def test_nested_git_checkout_is_not_accepted_as_root(self):
        with tempfile.TemporaryDirectory() as d:
            tree = Path(d) / "tree"
            tree.mkdir()
            (tree / "bot.py").write_text("pass", encoding="utf-8")
            with patch("source_audit_inventory.subprocess.run") as run:
                run.return_value.returncode = 0
                run.return_value.stdout = str(ROOT)
                with self.assertRaisesRegex(RuntimeError, "verified release stage"):
                    source_inventory(tree)


if __name__ == "__main__":
    unittest.main()
