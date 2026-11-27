import tempfile
import unittest
from pathlib import Path

from tools.architecture.module_import_audit import scan_file, scan_graph


class ImportAuditTests(unittest.TestCase):
    def test_type_checking_import_is_not_an_eager_cycle(self):
        a = scan_file("a.py", "if TYPE_CHECKING:\n    import b\n", {"a", "b"})
        b = scan_file("b.py", "import a\n", {"a", "b"})
        self.assertEqual([e["kind"] for e in a["edges"]], ["type_checking"])
        self.assertEqual([e["kind"] for e in b["edges"]], ["eager"])
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a.py").write_text("if TYPE_CHECKING:\n    import b\n", encoding="utf-8")
            (root / "b.py").write_text("import a\n", encoding="utf-8")
            result = scan_graph(root, ["a.py", "b.py"])
        self.assertEqual(result["eager_cycles"], [])

    def test_function_local_from_import_is_deferred_not_eager_cycle(self):
        a = scan_file("pkg/a.py", "def load():\n    from . import b\n", {"pkg.a", "pkg.b"})
        b = scan_file("pkg/b.py", "import pkg.a\n", {"pkg.a", "pkg.b"})
        self.assertEqual(a["edges"][0]["kind"], "deferred")
        self.assertEqual(a["edges"][0]["target"], "pkg.b")
        self.assertEqual(b["edges"][0]["kind"], "eager")

    def test_real_eager_two_module_cycle_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a.py").write_text("import b\n", encoding="utf-8")
            (root / "b.py").write_text("from a import VALUE\n", encoding="utf-8")
            result = scan_graph(root, ["a.py", "b.py"])
        self.assertEqual(result["eager_cycles"], [["a", "b"]])

    def test_missing_tracked_file_is_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "kept.py").write_text("VALUE = 1\n", encoding="utf-8")
            result = scan_graph(root, ["kept.py", "removed.py"])
        self.assertEqual(result["modules"], ["kept"])
        self.assertEqual(result["counts"]["tracked_existing_production_py"], 1)

    def test_path_traversal_and_absolute_paths_are_rejected(self):
        for path in ("../outside.py", "/outside.py", "pkg/../../outside.py"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                scan_file(path, "")
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                scan_graph(tmp, ["../outside.py"])

    def test_nested_type_checking_and_dynamic_import_are_observed(self):
        result = scan_file(
            "pkg/a.py",
            "from typing import TYPE_CHECKING\n"
            "if TYPE_CHECKING:\n    if True:\n        from . import b\n"
            "def later():\n    import importlib\n    importlib.import_module('pkg.c')\n",
            {"pkg.a", "pkg.b"},
        )
        self.assertEqual(result["edges"][0]["kind"], "type_checking")
        self.assertEqual(result["dynamic_imports"][0]["target"], "pkg.c")


if __name__ == "__main__":
    unittest.main()
