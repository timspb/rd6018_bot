"""Source and fake-only contracts for the single operator OFF-state owner."""

import ast
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from runtime.operator.off_conditions import OperatorOffConditions


ROOT = Path(__file__).resolve().parents[1]
PRODUCTION = ROOT / "runtime" / "production_runtime.py"
INGRESS = ROOT / "runtime" / "ui" / "telegram" / "ingress.py"
MANUAL = ROOT / "manual_runtime.py"
OLD = {
    "manual_off_voltage", "manual_off_voltage_le", "manual_off_current",
    "manual_off_current_ge", "manual_off_time_sec", "manual_off_start_time",
}
FIELDS = ("voltage_ge", "voltage_le", "current_le", "current_ge", "time_sec", "start_time")


class OperatorOffStateCutoverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = PRODUCTION.read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source)

    def test_no_module_level_legacy_scalar_definition_or_assignment(self):
        for node in self.tree.body:
            if isinstance(node, ast.AnnAssign):
                self.assertFalse(isinstance(node.target, ast.Name) and node.target.id in OLD)
            elif isinstance(node, (ast.Assign, ast.AugAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for target in targets:
                    self.assertFalse(any(isinstance(n, ast.Name) and n.id in OLD for n in ast.walk(target)))
        self.assertFalse(OLD.intersection(n.id for n in ast.walk(self.tree) if isinstance(n, ast.Name)))

    def test_one_active_instance_and_all_live_reads_use_its_fields(self):
        instances = [n for n in self.tree.body if isinstance(n, ast.Assign)
                     and any(isinstance(t, ast.Name) and t.id == "_operator_off_conditions" for t in n.targets)]
        self.assertEqual(len(instances), 1)
        self.assertIsInstance(instances[0].value, ast.Call)
        self.assertEqual(ast.unparse(instances[0].value.func), "OperatorOffConditions")
        attrs = {n.attr for n in ast.walk(self.tree) if isinstance(n, ast.Attribute)
                 and isinstance(n.value, ast.Name) and n.value.id == "_operator_off_conditions"}
        self.assertTrue({"update_from_document", "evaluate_reason", "save", "load", "clear"}.issubset(attrs))
        self.assertNotIn("json.dump", self.source[self.source.index("def _save_manual_off_state"):])

    def test_compatibility_helpers_delegate_to_owner(self):
        expected = {
            "_save_manual_off_state": "_operator_off_conditions.save(MANUAL_OFF_FILE)",
            "_load_manual_off_state": "_operator_off_conditions.load(MANUAL_OFF_FILE)",
            "_clear_manual_off": "_operator_off_conditions.clear(MANUAL_OFF_FILE)",
            "_has_manual_off_condition": "_operator_off_conditions.has_condition()",
        }
        funcs = {n.name: n for n in self.tree.body if isinstance(n, ast.FunctionDef)}
        for name, expression in expected.items():
            with self.subTest(helper=name):
                self.assertEqual(len(funcs[name].body), 1)
                self.assertEqual(ast.unparse(funcs[name].body[0].value), expression)

    def test_preset_values_live_in_existing_owner_and_runtime_delegates(self):
        node = next(n for n in self.tree.body if isinstance(n, ast.FunctionDef) and n.name == "_apply_manual_off_preset")
        source = ast.unparse(node)
        self.assertIn("_operator_off_conditions.apply_preset(preset, now_s=time.time())", source)
        self.assertIn("_save_manual_off_state()", source)
        self.assertNotIn("2 * 3600", source)
        owner_source = (ROOT / "runtime" / "operator" / "off_conditions.py").read_text(encoding="utf-8")
        for expected in ("2 * 3600", "0.30", "16.2", "unknown_off_preset", "invalid_off_preset"):
            self.assertIn(expected, owner_source)
        ingress = INGRESS.read_text(encoding="utf-8")
        self.assertIn('text.strip().lower() == "off"', ingress)

    def test_text_and_preset_updates_delegate_mutation_to_existing_owner(self):
        functions = {n.name: n for n in self.tree.body
                     if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
        preset_source = ast.unparse(functions["_apply_manual_off_preset"])
        self.assertIn("_operator_off_conditions.apply_preset", preset_source)
        ingress_tree = ast.parse(INGRESS.read_text(encoding="utf-8"))
        source = ast.unparse(next(n for n in ast.walk(ingress_tree)
                                  if isinstance(n, ast.AsyncFunctionDef)
                                  and n.name == "text_message_handler"))
        binding = ast.unparse(next(n for n in ast.walk(self.tree)
                                  if isinstance(n, ast.Call)
                                  and isinstance(n.func, ast.Name)
                                  and n.func.id == "install_text_message_handler"))
        self.assertIn("update_condition=_operator_off_conditions.update_from_document", binding)
        self.assertIn("clear_condition=_clear_manual_off", binding)
        for field in FIELDS:
            self.assertNotIn(f"_operator_off_conditions.{field} =", source)
        for method in ("request_verified_off", "request_verified_on", "program_voltage_current"):
            self.assertNotIn(method, source)

    def test_text_off_parser_keeps_persistence_and_no_actuator_call(self):
        handler_tree = ast.parse(INGRESS.read_text(encoding="utf-8"))
        handler = next(n for n in ast.walk(handler_tree) if isinstance(n, ast.AsyncFunctionDef)
                       and n.name == "text_message_handler")
        branches = [n for n in ast.walk(handler) if isinstance(n, ast.If)
                    and isinstance(n.test, ast.Compare)
                    and ast.unparse(n.test) == "text.strip().lower() == 'off'"]
        self.assertEqual(len(branches), 1)
        branch_source = ast.unparse(branches[0])
        self.assertIn("clear_condition()", branch_source)
        self.assertNotIn("request_verified_off", branch_source)
        self.assertNotIn("request_verified_on", branch_source)

    def test_manual_consumer_prefers_owner_and_retains_fake_legacy_fallback(self):
        source = MANUAL.read_text(encoding="utf-8")
        tree = ast.parse(source)
        method = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)
                      and n.name == "_persisted_manual_off_reason")
        method_source = ast.unparse(method)
        self.assertIn("_operator_off_conditions", method_source)
        self.assertIn("state = getattr(self.app", method_source)
        for name in OLD:
            self.assertIn(name, method_source)
        owner_app = SimpleNamespace(_operator_off_conditions=OperatorOffConditions(voltage_ge=16.0))
        self.assertEqual(owner_app._operator_off_conditions.voltage_ge, 16.0)
        legacy_app = SimpleNamespace(manual_off_voltage=16.0)
        self.assertIsNone(getattr(legacy_app, "_operator_off_conditions", None))
        self.assertEqual(legacy_app.manual_off_voltage, 16.0)

    def test_owner_save_and_reload_use_same_six_key_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manual_off_state.json"
            state = OperatorOffConditions(voltage_ge=16.2, time_sec=7200.0, start_time=100.0)
            state.save(path)
            self.assertEqual(set(json.loads(path.read_text(encoding="utf-8"))), set(FIELDS))
            restored = OperatorOffConditions()
            self.assertTrue(restored.load(path))
            self.assertEqual(restored.to_document(), state.to_document())


if __name__ == "__main__":
    unittest.main()
