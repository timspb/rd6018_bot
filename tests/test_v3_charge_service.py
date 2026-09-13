import ast
import pathlib
import unittest

from runtime import RuntimeApp, RuntimeDependencies
from runtime.charge import (
    BatteryProfile,
    ChargeIntent,
    ChargeState,
    ChemistryProfile,
    ManualProgram,
    ManualTargets,
    Measurements,
    ProgramRegistry,
)


class V3ChargeServiceTests(unittest.TestCase):
    def test_runtime_app_creates_charge_service(self):
        app = RuntimeApp(RuntimeDependencies(clock=lambda: 10.0))

        self.assertIsNotNone(app.charge_service)
        self.assertEqual(("delta", "manual", "minimum"), app.charge_service.registry.available())
        self.assertIsNotNone(app.state_provider)

    def test_service_selects_program_and_returns_snapshot(self):
        battery = BatteryProfile(ChemistryProfile.AGM, 80.0)
        app = RuntimeApp(RuntimeDependencies(clock=lambda: 42.0))
        snapshot = app.charge_service.evaluate(
            battery,
            "manual",
            ManualTargets(14.4, 2.0),
            ChargeState(stage="manual"),
            Measurements(12.6, 0.0, 25.0, 1.0),
        )

        self.assertEqual("manual", snapshot.active_program)
        self.assertEqual(ChargeIntent(14.4, 2.0, "manual", False, "manual targets"), snapshot.intent)
        self.assertEqual(42.0, snapshot.timestamp)
        self.assertIs(snapshot.battery_profile, battery)

    def test_runtime_service_has_no_actuator_surface(self):
        path = pathlib.Path(__file__).parents[1] / "runtime" / "charge" / "service.py"
        text = path.read_text(encoding="utf-8")
        forbidden = {"bot_legacy", "hass_api", "aiogram", "rd_control_mode", "safe_output", "turn_on", "turn_off", "set_voltage", "set_current"}
        self.assertTrue(forbidden.isdisjoint(text.split()))
        tree = ast.parse(text, filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                self.assertNotIn((node.module or "").split(".")[0], forbidden)

    def test_custom_registry_is_used_by_runtime_app(self):
        registry = ProgramRegistry()
        registry.register("manual", ManualProgram)
        app = RuntimeApp(RuntimeDependencies(clock=lambda: 1.0, program_registry=registry))

        self.assertEqual(("manual",), app.charge_service.registry.available())

    def test_runtime_shadow_tick_returns_snapshot_and_comparison(self):
        from runtime.charge import ChargeDecisionCase, DecisionValidationStatus
        case = ChargeDecisionCase(
            "service-manual",
            BatteryProfile(ChemistryProfile.AGM, 80.0),
            Measurements(12.6, 0.0, 25.0, 1.0),
            ChargeState(stage="manual"),
            {"program": "manual"},
            ChargeIntent(14.4, 2.0, "manual", False, "manual targets"),
        )
        app = RuntimeApp(RuntimeDependencies(clock=lambda: 99.0))

        snapshot, comparison = app.shadow_tick(case, ManualTargets(14.4, 2.0))

        self.assertEqual("manual", snapshot.active_program)
        self.assertEqual(99.0, snapshot.timestamp)
        self.assertIs(DecisionValidationStatus.MATCH, comparison.status)


if __name__ == "__main__":
    unittest.main()
