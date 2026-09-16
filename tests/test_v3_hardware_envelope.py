import unittest

from runtime.charge.chemistry import ChemistryProfile
from runtime.output.bridge import HardwareCapability
from runtime.physical.envelope import (
    BatterySafetyEnvelope, EnvelopeValidationStatus, EnvelopeValidator,
    HardwareSafetyEnvelope,
)


def _hardware(chemistry=(ChemistryProfile.AGM,)):
    capability = HardwareCapability(True, True, 10, 18, .01, .1, 12, .01, True, True, True, True, True, True)
    return HardwareSafetyEnvelope(10, 18, 12, 220, ("MAIN", "MIX"), chemistry, capability)


class HardwareEnvelopeTests(unittest.TestCase):
    def setUp(self):
        self.battery = BatterySafetyEnvelope(ChemistryProfile.AGM, 12, (40, 100), 15.0, 8.0, ("AGM",))

    def test_allowed_request(self):
        result = EnvelopeValidator().validate(self.battery, _hardware(), requested_voltage=14.4, requested_current=2, mode="MAIN", profile="AGM")
        self.assertEqual(result.status, EnvelopeValidationStatus.ALLOWED)
        self.assertTrue(result.allowed)

    def test_voltage_current_and_chemistry_limits_block(self):
        validator = EnvelopeValidator()
        result = validator.validate(self.battery, _hardware((ChemistryProfile.EFB,)), requested_voltage=15.1, requested_current=9, mode="MAIN", profile="AGM")
        self.assertEqual(result.status, EnvelopeValidationStatus.BLOCKED)
        self.assertEqual(set(result.violated_limits), {"battery_max_voltage", "battery_max_current", "chemistry_not_supported"})

    def test_gate_rejects_blocked_envelope(self):
        from runtime.output.bridge import PhysicalExecutionConfig, PhysicalExecutionGate
        from runtime.output.executor import ExecutionLeaseState, build_command_plan
        from runtime.output.execution_policy import ExecutionPolicyDecision
        from runtime.output.intent import OutputAction, SafeOutputIntent

        blocked = EnvelopeValidator().validate(self.battery, _hardware(), requested_voltage=16, requested_current=2)
        gate = PhysicalExecutionGate(PhysicalExecutionConfig(enabled=True))
        gate.arm("bench")
        validation = gate.validate(build_command_plan(SafeOutputIntent(OutputAction.DISABLE)), ExecutionPolicyDecision(True, "ok"), ExecutionLeaseState("bench", 1, 1, "active"), _hardware().capabilities, blocked)
        self.assertFalse(validation.allowed)
        self.assertIn("hardware_battery_envelope_blocked", validation.violations)

