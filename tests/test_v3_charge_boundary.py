import ast
import pathlib
import unittest

from runtime.charge import ChargeIntent, ChargeProgram, ChargeState


class ExampleProgram(ChargeProgram):
    def evaluate(self, state, measurements):
        return ChargeIntent(
            target_voltage=13.8,
            target_current=1.0,
            next_stage="storage",
            completed=False,
            reason="test",
        )


class V3ChargeBoundaryTests(unittest.TestCase):
    def test_charge_state_is_data_only(self):
        state = ChargeState(
            program="test",
            mode="managed",
            stage="main",
            timers={"stage": 10.0},
            targets={"voltage": 14.4},
            measurements={"voltage": 12.5},
        )

        self.assertEqual("test", state.program)
        self.assertEqual(10.0, state.timers["stage"])
        self.assertFalse(state.completed)
        self.assertFalse(any(name in dir(state) for name in ("turn_on", "turn_off", "set_voltage")))

    def test_charge_intent_is_data_only(self):
        intent = ChargeIntent(14.4, 2.0, "main", False, "advance")

        self.assertEqual(14.4, intent.target_voltage)
        self.assertEqual("main", intent.next_stage)
        self.assertEqual("advance", intent.reason)
        with self.assertRaises(AttributeError):
            intent.reason = "changed"

    def test_program_interface_returns_intent(self):
        result = ExampleProgram().evaluate(ChargeState(stage="main"), {"voltage": 12.5})

        self.assertIsInstance(result, ChargeIntent)

    def test_charge_boundary_has_no_integration_imports(self):
        charge_root = pathlib.Path(__file__).parents[1] / "runtime" / "charge"
        forbidden = {"bot_legacy", "hass_api", "aiogram", "rd_control_mode", "safe_output"}
        for path in charge_root.glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = {alias.name.split(".")[0] for alias in node.names}
                    self.assertTrue(forbidden.isdisjoint(names), path.name)
                elif isinstance(node, ast.ImportFrom):
                    root = (node.module or "").split(".")[0]
                    self.assertNotIn(root, forbidden, path.name)


if __name__ == "__main__":
    unittest.main()
