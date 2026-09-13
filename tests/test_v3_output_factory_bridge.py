import asyncio
import unittest

from runtime.charge import ChargeIntent, Measurements
from runtime.output import OutputAction, OutputIntentFactory, SafeOutputIntent
from runtime.output.bridge import ShadowOutputBridge
from runtime.safety import SafetyContext, SafetyEngine, SafetyLimits


class V3OutputFactoryBridgeTests(unittest.TestCase):
    def setUp(self):
        self.safety = SafetyEngine(SafetyLimits(max_voltage=15.0, max_current=8.0))
        self.measurements = Measurements(14.4, 2.0, 25.0, 1.0)
        self.factory = OutputIntentFactory()

    def test_allowed_decision_becomes_safe_output_intent(self):
        decision = self.safety.evaluate(ChargeIntent(14.4, 2.0, "main"), self.measurements, SafetyContext())
        intent = self.factory.create(decision)
        self.assertEqual(OutputAction.ENABLE, intent.action)
        self.assertEqual(14.4, intent.target_voltage)
        self.assertEqual(2.0, intent.target_current)

    def test_denied_decision_cannot_become_output_intent(self):
        decision = self.safety.evaluate(ChargeIntent(16.0, 2.0, "main"), self.measurements, SafetyContext())
        with self.assertRaises(ValueError):
            self.factory.create(decision)

    def test_disable_and_setpoint_mapping(self):
        bridge = ShadowOutputBridge()
        for intent, expected in (
            (SafeOutputIntent(OutputAction.ENABLE, 14.4, 2.0), {"voltage": 14.4, "current": 2.0}),
            (SafeOutputIntent(OutputAction.DISABLE), {}),
            (SafeOutputIntent(OutputAction.SET_VOLTAGE, target_voltage=14.4), {"voltage": 14.4}),
            (SafeOutputIntent(OutputAction.SET_CURRENT, target_current=2.0), {"current": 2.0}),
        ):
            record = bridge.map(intent)
            self.assertEqual(intent.action.value, record.mapped.command)
            self.assertEqual(expected, dict(record.mapped.parameters))
            self.assertFalse(record.executed)
            self.assertEqual("shadow_only", record.reason)

    def test_factory_and_bridge_have_no_physical_execution(self):
        decision = self.safety.evaluate(ChargeIntent(completed=True, next_stage="done"), self.measurements, SafetyContext())
        record = ShadowOutputBridge().map(self.factory.create(decision))
        self.assertEqual(OutputAction.DISABLE, record.intent.action)
        self.assertFalse(record.executed)


if __name__ == "__main__":
    unittest.main()
