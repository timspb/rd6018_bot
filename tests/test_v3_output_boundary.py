import ast
import asyncio
import pathlib
import unittest

from runtime.charge import ChargeIntent
from runtime.output import InvalidOutputIntent, MockOutputAdapter, OutputAction, OutputAdapter, SafeOutputIntent


class V3OutputBoundaryTests(unittest.TestCase):
    def test_safe_intent_and_mock_adapter(self):
        adapter = MockOutputAdapter()
        intent = SafeOutputIntent(OutputAction.ENABLE, 14.4, 2.0)
        result = asyncio.run(adapter.apply(intent))
        self.assertTrue(result.accepted)
        self.assertEqual([intent], adapter.applied)

    def test_invalid_safe_intent_rejected(self):
        with self.assertRaises(InvalidOutputIntent):
            SafeOutputIntent(OutputAction.ENABLE, target_voltage=14.4)
        with self.assertRaises(InvalidOutputIntent):
            SafeOutputIntent(OutputAction.DISABLE, target_voltage=14.4)

    def test_adapter_does_not_accept_charge_intent(self):
        adapter = MockOutputAdapter()
        with self.assertRaises(TypeError):
            asyncio.run(adapter.apply(ChargeIntent(14.4, 2.0)))
        self.assertTrue(issubclass(MockOutputAdapter, OutputAdapter))

    def test_output_layer_has_no_transport_or_actuator_imports(self):
        root = pathlib.Path(__file__).parents[1] / "runtime" / "output"
        forbidden = {"hass_api", "aiogram", "rd_control_mode", "serial", "modbus", "turn_on", "turn_off"}
        for path in root.glob("*.py"):
            text = path.read_text(encoding="utf-8")
            self.assertTrue(forbidden.isdisjoint(text.split()), path.name)
            tree = ast.parse(text, filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    self.assertNotIn((node.module or "").split(".")[0], forbidden)


if __name__ == "__main__":
    unittest.main()
