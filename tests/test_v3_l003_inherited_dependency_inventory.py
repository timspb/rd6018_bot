from __future__ import annotations

import ast
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
CONTROLLER = ROOT / "charge_controller.py"

EXPECTED_CONTROLLER_CONSTANTS = {
    "PROFILE_AGM", "PROFILE_CA", "PROFILE_CUSTOM", "PROFILE_EFB",
    "STAGE_COOLING", "STAGE_DESULFATION", "STAGE_DONE", "STAGE_IDLE",
    "STAGE_MAIN", "STAGE_MIX", "STAGE_PREP", "STAGE_SAFE_WAIT",
}


def _production_python_paths() -> list[Path]:
    return [
        path for path in ROOT.rglob("*.py")
        if "tests" not in path.parts
        and ".git" not in path.parts
        and "__pycache__" not in path.parts
    ]


class L003InheritedDependencyInventoryTests(unittest.TestCase):
    def test_historical_controller_sources_are_removed(self) -> None:
        self.assertFalse((ROOT / "charge_logic.py").exists())
        self.assertFalse((ROOT / "legacy_safety.py").exists())

    def test_managed_controller_owns_stage_and_profile_constants(self) -> None:
        tree = ast.parse(CONTROLLER.read_text(encoding="utf-8"))
        controller = next(
            node for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "ManagedChargeController"
        )
        constants = {
            node.targets[0].id
            for node in controller.body
            if isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
        }
        self.assertTrue(EXPECTED_CONTROLLER_CONSTANTS <= constants)
        self.assertEqual([], controller.bases)

    def test_production_has_no_historical_controller_import(self) -> None:
        violations = []
        for path in _production_python_paths():
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    names = [node.module or ""]
                else:
                    continue
                for name in names:
                    if name in {"charge_logic", "legacy_safety"}:
                        violations.append(f"{path.relative_to(ROOT)}:{name}")
        self.assertEqual([], violations)

    def test_runtime_support_uses_canonical_limits(self) -> None:
        from charge_controller import ManagedChargeController

        controller = ManagedChargeController(object())
        controller.battery_type = controller.PROFILE_EFB
        controller.current_stage = controller.STAGE_MIX
        controller.stage_start_time = 100.0
        self.assertEqual(controller._get_stage_max_hours(), 24.0)
        self.assertEqual(controller._get_target_finish_time(), 100.0 + 24.0 * 3600.0)
        self.assertIn("Mix 24h", controller._session_rules_summary())
        controller.i_min_recorded = 1.0
        self.assertAlmostEqual(controller._mix_current_delta_threshold(), 0.30)
        self.assertFalse(controller._exit_cv_condition(1.29))
        self.assertTrue(controller._exit_cv_condition(1.30))
        controller.v_max_recorded = 16.5
        self.assertFalse(controller._exit_cc_condition(16.48))
        self.assertTrue(controller._exit_cc_condition(16.47))

    def test_diagnostics_preserve_current_risk_policy(self) -> None:
        from charge_controller import ManagedChargeController

        controller = ManagedChargeController(object())
        controller.battery_type = controller.PROFILE_EFB
        controller.current_stage = controller.STAGE_MIX
        controller.stage_start_time = 1_000.0
        controller.total_start_time = 1_000.0
        snapshot = controller.get_ai_stage_snapshot(25.0)
        self.assertEqual(snapshot["mix_exit_policy"]["fallback_limit_hours"], 24.0)
        controller.current_stage = controller.STAGE_PREP
        now = 1_000_000.0
        controller.stage_start_time = now - 2 * 3600.0
        controller._stage_start_voltage = 10.7
        controller._stage_start_current = 0.45
        controller._stage_start_temp = 24.0
        controller._stage_start_ah = 0.0
        controller._analytics_history.clear()
        risk = controller._bank_fault_risk_snapshot(now, 11.15, 0.32, 25.1, 1.4)
        self.assertIsNotNone(risk)
        self.assertEqual(risk["status"], "high")
        self.assertGreaterEqual(risk["score"], 70)


if __name__ == "__main__":
    unittest.main()
