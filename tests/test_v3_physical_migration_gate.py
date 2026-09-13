import ast
import pathlib
import unittest

from runtime.output import OutputAction, SafeOutputIntent
from runtime.charge.strategy import ResetProtectionIntent, post_mix_reset_intent


ROOT = pathlib.Path(__file__).parents[1]


class V3PhysicalMigrationGateTests(unittest.TestCase):
    def test_safe_output_intent_covers_current_execution_actions(self):
        intents = (
            SafeOutputIntent(OutputAction.ENABLE, 14.4, 2.0),
            SafeOutputIntent(OutputAction.DISABLE),
            SafeOutputIntent(OutputAction.SET_VOLTAGE, target_voltage=14.4),
            SafeOutputIntent(OutputAction.SET_CURRENT, target_current=2.0),
        )
        self.assertEqual({intent.action for intent in intents}, set(OutputAction))

    def test_post_mix_reset_is_data_only_and_explicit(self):
        intent = post_mix_reset_intent(17.5, 12.0, reason="MIX_FINISH")
        self.assertIsInstance(intent, ResetProtectionIntent)
        self.assertEqual("MIX", intent.source_phase)

    def test_v3_domain_has_no_direct_physical_or_transport_imports(self):
        forbidden_modules = {
            "aiogram", "hass_api", "rd_control_mode", "serial", "modbus",
            "gpio", "telegram", "bot_legacy", "lease",
        }
        forbidden_calls = {
            "turn_on", "turn_off", "set_voltage", "set_current", "set_ovp", "set_ocp",
        }
        roots = (ROOT / "runtime" / "charge", ROOT / "runtime" / "safety", ROOT / "runtime" / "output")
        for root in roots:
            for path in root.rglob("*.py"):
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        self.assertTrue(
                            forbidden_modules.isdisjoint({alias.name.split(".")[0] for alias in node.names}),
                            str(path),
                        )
                    elif isinstance(node, ast.ImportFrom):
                        self.assertNotIn((node.module or "").split(".")[0], forbidden_modules, str(path))
                    elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                        self.assertNotIn(node.func.attr, forbidden_calls, str(path))


if __name__ == "__main__":
    unittest.main()
