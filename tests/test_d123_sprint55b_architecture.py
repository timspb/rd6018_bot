import ast
import unittest
from pathlib import Path

from auto_strategy import AutoStrategyProductionChargeController
from diagnostic_controller import DiagnosticProductionChargeController
from mix_active_authority import MixActiveTimeAuthority
from production_controller import ProductionChargeController


ROOT = Path(__file__).resolve().parents[1]


class Sprint55BArchitectureTests(unittest.TestCase):
    def test_legacy_controller_names_are_non_host_aliases(self):
        self.assertIs(DiagnosticProductionChargeController, ProductionChargeController)
        self.assertEqual(AutoStrategyProductionChargeController.__dict__.keys() & {
            "__init__", "tick", "try_restore_session", "update_diagnostic_context",
            "_refresh_stored_diagnostics", "_update_live_diagnostic_evidence",
            "_diagnostic_hv_veto", "_enter_mix",
        }, set())
        self.assertIsNot(MixActiveTimeAuthority, ProductionChargeController)

    def test_production_diagnostic_and_mix_state_share_the_canonical_host(self):
        source = (ROOT / "charge_controller.py").read_text()
        self.assertIn("initialize_battery_fault_state(self)", source)
        self.assertIn("initialize_production_session_state(self)", source)
        self.assertIn("initialize_mix_active_authority(host)",
                      (ROOT / "application/production_session_extensions.py").read_text())
        self.assertNotIn("class DiagnosticProductionChargeController", source)
        self.assertNotIn("class MixActiveAuthorityMixin", (ROOT / "mix_active_authority.py").read_text())

    def test_hv_veto_precedes_stage_effect_and_mix_load_follows_guard_restore(self):
        stage = (ROOT / "runtime/charge/runtime/main_scaffold.py").read_text()
        veto = stage.index("veto = decision_veto(decision)")
        effect = stage.index("apply_main_mix_entry(")
        self.assertLess(veto, effect)
        controller = (ROOT / "charge_controller.py").read_text()
        guard = controller.index("read_guard(", controller.index("def try_restore_session"))
        extensions = controller.index("restore_production_session_state(", guard)
        self.assertLess(guard, extensions)
        extension = (ROOT / "application/production_session_extensions.py").read_text()
        ordinary = extension.index("restore_production_session_state")
        mix_load = extension.index("restore_mix_active_authority(host)", ordinary)
        self.assertLess(ordinary, mix_load)

    def test_migration_owners_do_not_duplicate_persistence_or_physical_writers(self):
        for relative in (
            "runtime/charge/diagnostics.py", "mix_active_authority.py",
            "application/charge_session_tick.py", "application/charge_stage_tick.py",
            "application/production_session_extensions.py",
        ):
            tree = ast.parse((ROOT / relative).read_text())
            calls = {
                node.func.attr if isinstance(node.func, ast.Attribute)
                else node.func.id if isinstance(node.func, ast.Name) else ""
                for node in ast.walk(tree) if isinstance(node, ast.Call)
            }
            self.assertTrue({"safe_enable_output", "turn_on", "set_voltage", "set_current",
                             "set_ovp", "set_ocp"}.isdisjoint(calls), relative)
            self.assertTrue({"save_session", "atomic_session_write"}.isdisjoint(calls), relative)
        controller = ast.parse((ROOT / "charge_controller.py").read_text())
        saves = [node for node in ast.walk(controller) if isinstance(node, ast.FunctionDef)
                 and node.name == "_save_session"]
        self.assertEqual(len(saves), 1)


if __name__ == "__main__":
    unittest.main()
