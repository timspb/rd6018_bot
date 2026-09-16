import ast
import pathlib
import unittest

from runtime.charge import (
    BatteryProfile,
    ChargeEngine,
    ChargeIntent,
    ChargeProgram,
    ChargeState,
    ChemistryProfile,
    Measurements,
)


class RecordingProgram(ChargeProgram):
    def __init__(self):
        self.calls = []

    def evaluate(self, state, measurements):
        self.calls.append((state, measurements))
        return ChargeIntent(next_stage="next", reason="recorded")


class V3ChargeEngineTests(unittest.TestCase):
    def test_engine_accepts_battery_and_calls_program(self):
        battery = BatteryProfile(ChemistryProfile.AGM, 80.0)
        program = RecordingProgram()
        engine = ChargeEngine(battery, program)
        state = ChargeState(stage="main")
        measurements = Measurements(voltage=14.2, current=2.0, temperature=25.0, time=1.0)

        result = engine.evaluate(state, measurements)

        self.assertIs(engine.battery, battery)
        self.assertEqual([(state, measurements)], program.calls)
        self.assertIsInstance(result, ChargeIntent)
        self.assertEqual("recorded", result.reason)

    def test_measurements_are_snapshot_without_history_or_actuator_methods(self):
        measurements = Measurements(voltage=12.5, current=1.0, temperature=24.0, time=10.0)

        self.assertEqual(12.5, measurements.voltage)
        self.assertFalse(any(name in dir(measurements) for name in ("history", "turn_on", "turn_off")))

    def test_engine_boundary_has_no_external_imports(self):
        root = pathlib.Path(__file__).parents[1] / "runtime" / "charge"
        forbidden = {"bot_legacy", "hass_api", "aiogram", "rd_control_mode", "safe_output"}
        for path in (root / "engine.py", root / "measurements.py", root / "program.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    self.assertTrue(forbidden.isdisjoint({a.name.split(".")[0] for a in node.names}))
                elif isinstance(node, ast.ImportFrom):
                    self.assertNotIn((node.module or "").split(".")[0], forbidden)


if __name__ == "__main__":
    unittest.main()
