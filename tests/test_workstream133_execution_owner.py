from __future__ import annotations

import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ExecutionOwnershipInvariantTests(unittest.TestCase):
    def test_no_independent_executor_surface(self):
        bridge = (ROOT / "runtime" / "output" / "bridge" / "__init__.py").read_text(encoding="utf-8")
        executor = (ROOT / "runtime" / "output" / "bridge" / "executor.py").read_text(encoding="utf-8")
        self.assertNotIn("PhysicalBridgeExecutor", bridge)
        self.assertNotIn("class PhysicalBridgeExecutor", executor)

    def test_connectors_and_transports_are_read_only(self):
        for path in (
            ROOT / "runtime" / "physical" / "connectors" / "esp_direct.py",
            ROOT / "runtime" / "physical" / "connectors" / "ha_esp.py",
            ROOT / "runtime" / "physical" / "transports" / "esp128.py",
            ROOT / "runtime" / "physical" / "transports" / "ha102.py",
        ):
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("number_command(", text, path.name)
            self.assertNotIn("switch_command(", text, path.name)
            self.assertNotIn("/api/services/", text, path.name)

    def test_manual_mode_has_no_direct_hardware_calls(self):
        tree = ast.parse((ROOT / "manual_mode.py").read_text(encoding="utf-8"))
        forbidden = {"turn_on", "turn_off", "set_voltage", "set_current", "safe_enable_output"}
        calls = [node.func.attr for node in ast.walk(tree)
                 if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                 and node.func.attr in forbidden]
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
