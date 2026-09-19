import unittest

from application.safety import SafetyContext, SafetyPolicy, SafetyState


POLICY = SafetyPolicy(max_voltage_v=16.5, max_current_a=12.0, max_temperature_c=45.0, emergency_codes=("EMERGENCY",))


def context(**changes):
    values = dict(voltage_v=14.5, current_a=3.0, temperatures_c=(23.0,), protection_codes=(), telemetry_fresh=True, telemetry_present=True, timestamp=10.0)
    values.update(changes)
    return SafetyContext(**values)


class SafetyDomainTests(unittest.TestCase):
    def test_normal_allow(self):
        self.assertEqual(POLICY.evaluate(context()).state, SafetyState.ALLOW)

    def test_voltage_current_and_temperature_deny(self):
        for changes, rule in (({"voltage_v": 17.0}, "OVP"), ({"current_a": 13.0}, "OCP"), ({"temperatures_c": (46.0,)}, "OTP")):
            with self.subTest(rule=rule):
                decision = POLICY.evaluate(context(**changes))
                self.assertEqual(decision.state, SafetyState.DENY)
                self.assertIn(rule, decision.triggered_rules)

    def test_stale_and_missing_telemetry_deny(self):
        self.assertIn("stale_telemetry", POLICY.evaluate(context(telemetry_fresh=False)).triggered_rules)
        self.assertIn("missing_telemetry", POLICY.evaluate(context(telemetry_present=False)).triggered_rules)

    def test_emergency_has_priority(self):
        decision = POLICY.evaluate(context(emergency=True, voltage_v=17.0))
        self.assertEqual(decision.state, SafetyState.EMERGENCY)
        self.assertIn("emergency", decision.triggered_rules)

    def test_policy_is_data_only(self):
        import application.safety.policy as module
        with open(module.__file__, encoding="utf-8") as handle:
            source = handle.read()
        self.assertNotIn("turn_on", source)
        self.assertNotIn("turn_off", source)
        self.assertNotIn("HA", source)
        self.assertNotIn("ESPHome", source)


if __name__ == "__main__":
    unittest.main()
