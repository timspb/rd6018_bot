import ast
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class D123P2bSessionWriterArchitectureTests(unittest.TestCase):
    def test_controller_has_no_session_identity_read_or_writer_helpers(self):
        tree = ast.parse((ROOT / "charge_controller.py").read_text(encoding="utf-8"))
        methods = {
            node.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        self.assertNotIn("_write_trace_identity_to_session_file", methods)
        self.assertNotIn("_read_legacy_session_document", methods)
        self.assertNotIn("_restore_trace_identity", methods)
        self.assertNotIn("_begin_trace_identity", methods)

    def test_no_production_session_patch_writer_or_v2_temp_path(self):
        for filename in ("charge_controller.py", "production_controller.py"):
            source = (ROOT / filename).read_text(encoding="utf-8")
            self.assertNotIn(".v2.tmp", source)
            self.assertNotIn(".cooling.tmp", source)
            self.assertNotIn(".finish-state.tmp", source)
            self.assertNotIn(".runtime-signal.tmp", source)
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                    self.assertFalse(
                        node.func.attr == "replace" and isinstance(node.func.value, ast.Name)
                        and node.func.value.id == "os",
                        f"{filename} owns an independent os.replace call",
                    )


if __name__ == "__main__":
    unittest.main()
