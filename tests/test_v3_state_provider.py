import ast
import pathlib
import unittest

from runtime import RuntimeApp
from runtime.charge import ChargeState
from runtime.charge.state_provider import ChargeStateProvider


class V3StateProviderTests(unittest.TestCase):
    def test_provider_builds_charge_state_snapshot(self):
        measurements = {"voltage": 14.4, "current": 2.0}
        provider = ChargeStateProvider()
        state = provider.build(
            active_program="minimum",
            mode="managed",
            stage="main",
            targets={"voltage": 14.4, "current": 2.0},
            timers={"stage": 10.0},
            completed=False,
            measurements=measurements,
        )

        self.assertIsInstance(state, ChargeState)
        self.assertEqual("minimum", state.program)
        self.assertEqual("main", state.stage)
        self.assertEqual(10.0, state.timers["stage"])
        self.assertIs(state.measurements, measurements)

    def test_provider_does_not_mutate_inputs_or_expose_actuators(self):
        targets = {"voltage": 14.4}
        timers = {"stage": 1.0}
        provider = ChargeStateProvider()
        state = provider.build(
            active_program="manual", mode=None, stage="manual", targets=targets,
            timers=timers, completed=False, measurements={},
        )
        state.targets["current"] = 2.0

        self.assertEqual({"voltage": 14.4}, targets)
        self.assertEqual({"stage": 1.0}, timers)
        self.assertFalse(any(name in dir(provider) for name in ("turn_on", "turn_off", "set_voltage")))

    def test_runtime_app_owns_provider_without_forbidden_imports(self):
        app = RuntimeApp()
        self.assertIsNotNone(app.state_provider)
        path = pathlib.Path(__file__).parents[1] / "runtime" / "charge" / "state_provider.py"
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        forbidden = {"bot_legacy", "hass_api", "aiogram", "rd_control_mode", "safe_output"}
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                self.assertNotIn((node.module or "").split(".")[0], forbidden)


if __name__ == "__main__":
    unittest.main()
