import unittest

from runtime.safety.output_policy import (
    OutputRequest, SafetySupervisor, TelemetrySnapshot, ProtectionStatus,
)


class IndependentOutputSafeguardTests(unittest.TestCase):
    def setUp(self):
        self.request = OutputRequest(14.4, 2.0, 14.4)
        self.supervisor = SafetySupervisor()

    def test_measured_voltage_above_recipe_ceiling_is_rejected(self):
        telemetry = TelemetrySnapshot(
            battery_voltage_v=12.6, current_a=0.5, temp_ext_c=25.0,
            temp_int_c=30.0, output_on=True, output_voltage_v=15.0,
            set_voltage_v=14.4, set_current_a=2.0,
        )
        decision = self.supervisor.verify_live_output(self.request, telemetry)
        self.assertFalse(decision.allowed)
        self.assertIn("measured_output_over_limit", {v.value for v in decision.violations})

    def test_missing_programmed_v_i_readback_fails_closed(self):
        telemetry = TelemetrySnapshot(
            battery_voltage_v=12.6, current_a=0.5, temp_ext_c=25.0,
            temp_int_c=30.0, output_on=True, output_voltage_v=14.0,
        )
        decision = self.supervisor.verify_programmed(self.request, telemetry)
        self.assertFalse(decision.allowed)

    def test_raw_opp_remains_a_separate_trip(self):
        telemetry = TelemetrySnapshot(
            battery_voltage_v=12.6, current_a=0.5, temp_ext_c=25.0,
            temp_int_c=30.0, output_on=True, output_voltage_v=14.0,
            set_voltage_v=14.4, set_current_a=2.0,
            protection_status=ProtectionStatus.OPP,
        )
        decision = self.supervisor.verify_live_output(self.request, telemetry)
        self.assertFalse(decision.allowed)
        self.assertIn("protection_already_tripped", {v.value for v in decision.violations})
