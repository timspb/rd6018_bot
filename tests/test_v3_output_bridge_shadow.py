import unittest

from runtime.output.intent import OutputAction, SafeOutputIntent
from runtime.output.shadow_bridge import OutputParityComparator, V3OutputBridgeShadow


class V3OutputBridgeShadowTests(unittest.TestCase):
    def test_enable_mapping_preserves_parameters_and_order(self):
        intent = SafeOutputIntent(OutputAction.ENABLE, 14.4, 2.0)
        snapshot = V3OutputBridgeShadow().map(intent)
        self.assertTrue(snapshot.enable)
        self.assertEqual(snapshot.target_voltage, 14.4)
        self.assertEqual(snapshot.execution_order, ("set_voltage", "set_current", "set_protection", "readback", "enable"))

    def test_disable_mapping_is_fail_closed_and_never_executed(self):
        snapshot = V3OutputBridgeShadow().map(SafeOutputIntent(OutputAction.DISABLE, source="safety"))
        self.assertTrue(snapshot.disable)
        self.assertTrue(snapshot.reset_protection)
        self.assertEqual(snapshot.execution_order[0], "disable")

    def test_reset_mapping_preserves_protection_and_readback_order(self):
        intent = SafeOutputIntent(OutputAction.RESET_PROTECTION, target_ovp=15.0, target_ocp=3.0, source="mix_exit")
        snapshot = V3OutputBridgeShadow().map(intent)
        self.assertEqual((snapshot.ovp, snapshot.ocp), (15.0, 3.0))
        self.assertEqual(snapshot.execution_order, ("reset_protection", "readback"))

    def test_mismatch_is_reported(self):
        intent = SafeOutputIntent(OutputAction.SET_CURRENT, target_current=2.0)
        expected = V3OutputBridgeShadow().map(intent)
        changed = type(expected)(**{**expected.__dict__, "target_current": 2.1})
        result = OutputParityComparator.compare(intent, changed)
        self.assertEqual(result.status, "MISMATCH")
        self.assertIn("target_current", result.fields)


if __name__ == "__main__":
    unittest.main()
