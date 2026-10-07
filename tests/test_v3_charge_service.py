import ast
import pathlib
import unittest

from runtime.charge import (
    BatteryProfile,
    ChargeDecisionCase,
    ChargeIntent,
    ChargeService,
    ChargeState,
    ChemistryProfile,
    DecisionValidationResult,
    DecisionValidationStatus,
    ManualProgram,
    ManualTargets,
    Measurements,
    ProgramRegistry,
)
from runtime.charge.state_provider import ChargeStateProvider


class V3ChargeServiceTests(unittest.TestCase):
    def test_leaf_services_construct_without_runtime_container(self):
        service = ChargeService(ProgramRegistry.with_defaults(), lambda: 10.0)
        provider = ChargeStateProvider()
        self.assertEqual(("delta", "manual", "minimum"), service.registry.available())
        self.assertIsInstance(provider, ChargeStateProvider)

    def test_service_selects_program_and_returns_snapshot(self):
        battery = BatteryProfile(ChemistryProfile.AGM, 80.0)
        service = ChargeService(ProgramRegistry.with_defaults(), lambda: 42.0)
        snapshot = service.evaluate(
            battery, "manual", ManualTargets(14.4, 2.0),
            ChargeState(stage="manual"), Measurements(12.6, 0.0, 25.0, 1.0),
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

    def test_custom_registry_is_used_by_charge_service(self):
        registry = ProgramRegistry()
        registry.register("manual", ManualProgram)
        service = ChargeService(registry, lambda: 1.0)
        self.assertEqual(("manual",), service.registry.available())

    def test_decision_validation_is_independent_of_runtime_container(self):
        case = ChargeDecisionCase(
            "service-manual",
            BatteryProfile(ChemistryProfile.AGM, 80.0),
            Measurements(12.6, 0.0, 25.0, 1.0),
            ChargeState(stage="manual"),
            {"program": "manual"},
            ChargeIntent(14.4, 2.0, "manual", False, "manual targets"),
        )
        service = ChargeService(ProgramRegistry.with_defaults(), lambda: 99.0)
        snapshot = service.evaluate(
            case.battery_profile, "manual", ManualTargets(14.4, 2.0),
            case.charge_state, case.measurements,
        )
        comparison = DecisionValidationResult.compare(case, snapshot.intent)
        self.assertEqual("manual", snapshot.active_program)
        self.assertEqual(99.0, snapshot.timestamp)
        self.assertIs(DecisionValidationStatus.MATCH, comparison.status)


if __name__ == "__main__":
    unittest.main()
