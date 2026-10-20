import ast
import pathlib
import unittest

from application.production_target_policy import bound_target, recipe_envelope
from pb_domain import BatteryCondition, ChargeIntent
from production_controller import ProductionChargeController


ROOT = pathlib.Path(__file__).resolve().parents[1]


class ProductionRecipeTargetPolicyTests(unittest.TestCase):
    def test_production_adapters_are_owned_by_the_single_base_host(self):
        moved = {
            "__init__", "_new_runtime", "_bound_recipe_target", "_prep_target",
            "_main_target", "_desulf_target", "_mix_target", "_get_target_v_i",
            "_session_document_extensions",
        }
        self.assertTrue(moved.isdisjoint(ProductionChargeController.__dict__))
        self.assertNotIn("try_restore_session", ProductionChargeController.__dict__)
        production = ast.parse((ROOT / "production_controller.py").read_text())
        cls = next(node for node in production.body if isinstance(node, ast.ClassDef))
        methods = {
            node.name for node in cls.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        self.assertEqual(methods, set())
        extensions = ast.parse((ROOT / "application/production_session_extensions.py").read_text())
        self.assertFalse(any(isinstance(node, ast.ClassDef) for node in extensions.body))
        atomic = (ROOT / "runtime/charge/session_atomic.py").read_text()
        self.assertIn("session_document_extensions(host", atomic)
        self.assertNotIn("_session_document_extensions", atomic)

    def test_recipe_policy_is_application_owned_and_no_longer_a_facade_method(self):
        self.assertNotIn("_recipe_envelope", ProductionChargeController.__dict__)
        self.assertNotIn("_bound_target", ProductionChargeController.__dict__)
        self.assertNotIn("_current_stage_is_hv", ProductionChargeController.__dict__)
        source = (ROOT / "production_controller.py").read_text()
        base = (ROOT / "charge_controller.py").read_text()
        self.assertNotIn("from application.production_target_policy import", source)
        self.assertIn("from application.production_target_policy import", base)
        policy = ast.parse((ROOT / "application/production_target_policy.py").read_text())
        names = {node.name for node in policy.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
        self.assertEqual(
            names,
            {"recipe_envelope", "bound_target", "is_production_host", "bound_host_target"},
        )

    def test_policy_preserves_diagnostic_voltage_and_stage_current_bounds(self):
        envelope = recipe_envelope(
            profile="EFB", capacity_ah=100, battery_id="fixture",
            intent=ChargeIntent.DIAGNOSTIC, condition=BatteryCondition.UNKNOWN,
        )
        self.assertEqual(bound_target((16.5, 8.0), envelope, hv=True), (14.8, 3.0))

    def test_custom_profile_keeps_existing_unbounded_policy_bypass(self):
        envelope = recipe_envelope(
            profile="Custom", capacity_ah=100, battery_id="fixture",
            intent=ChargeIntent.NORMAL, condition=BatteryCondition.UNKNOWN,
        )
        target = (17.0, 10.5)
        self.assertIsNone(envelope)
        self.assertEqual(bound_target(target, envelope, hv=True), target)

    def test_runtime_still_constructs_one_production_host_and_no_second_state_owner(self):
        source = (ROOT / "runtime/production_runtime.py").read_text()
        tree = ast.parse(source)
        constructors = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in {"ProductionChargeController", "ManagedChargeController"}
        ]
        self.assertEqual(len(constructors), 1)
        self.assertEqual(constructors[0].func.id, "ProductionChargeController")

    def test_canonical_restore_owner_has_one_ordered_restore_path(self):
        base = ast.parse((ROOT / "charge_controller.py").read_text())
        production = ast.parse((ROOT / "production_controller.py").read_text())
        methods = [
            node for node in ast.walk(base)
            if isinstance(node, ast.FunctionDef) and node.name == "try_restore_session"
        ]
        self.assertEqual(len(methods), 1)
        self.assertFalse(any(
            isinstance(node, ast.FunctionDef) and node.name == "try_restore_session"
            for node in ast.walk(production)
        ))
        owner_source = (ROOT / "charge_controller.py").read_text()
        positions = [owner_source.index(token) for token in (
            "restore_session(\n            self,",
            "if GUARD_KEY in trace_document:",
            "restore_production_session_state(",
        )]
        self.assertEqual(positions, sorted(positions))
        atomic = ast.parse((ROOT / "runtime/charge/session_atomic.py").read_text())
        writers = [
            node for node in ast.walk(atomic)
            if isinstance(node, ast.FunctionDef) and node.name == "atomic_session_write"
        ]
        self.assertEqual(len(writers), 1)
        forbidden = {"safe_enable_output", "turn_on", "set_voltage", "set_current", "set_ovp", "set_ocp"}
        calls = {
            node.func.attr for node in ast.walk(methods[0])
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }
        self.assertTrue(forbidden.isdisjoint(calls))


if __name__ == "__main__":
    unittest.main()
