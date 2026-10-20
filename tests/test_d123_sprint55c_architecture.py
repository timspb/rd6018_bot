import ast
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path

from charge_controller import ManagedChargeController
from production_controller import (
    configure_production_charge_host,
    create_production_charge_host,
)
from runtime.charge.host_configuration import PRODUCTION_CHARGE_HOST_CONFIGURATION

ROOT = Path(__file__).resolve().parents[1]


class Sprint55CArchitectureTests(unittest.TestCase):
    def test_no_production_controller_classes_or_active_subclasses_remain(self):
        for relative in ("production_controller.py", "auto_strategy.py", "diagnostic_controller.py"):
            tree = ast.parse((ROOT / relative).read_text())
            self.assertFalse(any(isinstance(node, ast.ClassDef) for node in tree.body), relative)
        for path in (ROOT / "runtime").rglob("*.py"):
            tree = ast.parse(path.read_text())
            self.assertFalse(any(
                isinstance(node, ast.ClassDef) and any(
                    (isinstance(base, ast.Name) and base.id == "ManagedChargeController")
                    or (isinstance(base, ast.Attribute) and base.attr == "ManagedChargeController")
                    for base in node.bases
                ) for node in tree.body
            ), str(path))

    def test_runtime_constructs_exactly_one_canonical_host(self):
        tree = ast.parse((ROOT / "runtime/production_runtime.py").read_text())
        constructors = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
                        and isinstance(node.func, ast.Name)
                        and node.func.id in {"ManagedChargeController", "create_production_charge_host"}]
        self.assertEqual(len(constructors), 1)
        self.assertEqual(constructors[0].func.id, "create_production_charge_host")
        runtime = (ROOT / "runtime/production_runtime.py").read_text()
        self.assertIn("from production_controller import create_production_charge_host", runtime)

    def test_configuration_is_frozen_and_contains_no_runtime_state(self):
        self.assertEqual(PRODUCTION_CHARGE_HOST_CONFIGURATION.__dataclass_params__.frozen, True)
        for name in ("_current_stage", "session_id", "stage_start_time", "fsm", "session"):
            self.assertNotIn(name, PRODUCTION_CHARGE_HOST_CONFIGURATION.__dataclass_fields__)
        with self.assertRaises(FrozenInstanceError):
            PRODUCTION_CHARGE_HOST_CONFIGURATION.production_extensions_enabled = False

    def test_factory_and_bootstrap_preserve_one_canonical_host_identity(self):
        host = create_production_charge_host(None)
        self.assertIs(type(host), ManagedChargeController)
        self.assertIs(configure_production_charge_host(host), host)
        source = (ROOT / "production_bootstrap.py").read_text()
        self.assertNotIn("isinstance(app.charge_controller, ProductionChargeController)", source)
        self.assertIn("configure_production_charge_host(app.charge_controller)", source)

    def test_restore_and_writer_owners_remain_single_and_ordered(self):
        source = (ROOT / "charge_controller.py").read_text()
        guard = source.index("read_guard(", source.index("def try_restore_session"))
        extension = source.index("restore_production_session_state(", guard)
        self.assertLess(guard, extension)
        atomic = ast.parse((ROOT / "runtime/charge/session_atomic.py").read_text())
        self.assertEqual(sum(isinstance(node, ast.FunctionDef) and node.name == "atomic_session_write"
                             for node in ast.walk(atomic)), 1)
        for relative in ("application/production_session_extensions.py", "runtime/charge/host_configuration.py"):
            text = (ROOT / relative).read_text()
            self.assertNotIn("safe_enable_output(", text)
            self.assertNotIn("turn_on(", text)


if __name__ == "__main__":
    unittest.main()
