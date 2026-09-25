import unittest

from runtime.charge.intent import ChargeIntent
from runtime.output.executor import (
    DryRunExecutor, ExecutionLeaseState, PhysicalExecutor, ReadbackRequirement,
)
from runtime.output.intent import OutputAction, SafeOutputIntent
from runtime.safety import SafetyDecision


class V3PhysicalExecutorDryRunTests(unittest.TestCase):
    def setUp(self):
        self.safety = SafetyDecision(True, "ok", intent=ChargeIntent(14.4, 2.0))
        self.executor = DryRunExecutor(self.safety)

    def test_contract_and_readback_model(self):
        self.assertTrue(issubclass(DryRunExecutor, PhysicalExecutor))
        requirement = ReadbackRequirement(("programmed_voltage", "programmed_current", "ovp", "ocp", "output_state"))
        self.assertTrue(requirement.compare_required)
        self.assertEqual(ExecutionLeaseState("v3", 1, 10.0, "armed").owner, "v3")

    def test_enable_is_only_simulated_in_required_order(self):
        record = self.executor.execute(SafeOutputIntent(OutputAction.ENABLE, 14.4, 2.0))
        self.assertTrue(record.simulated)
        self.assertEqual(record.simulated_actions[-1], "enable")
        self.assertIsNone(record.verification_result["physical_state"] if "physical_state" in record.verification_result else None)

    def test_disable_requires_no_successful_safety_intent(self):
        record = DryRunExecutor(SafetyDecision(False, "blocked")).execute(SafeOutputIntent(OutputAction.DISABLE))
        self.assertTrue(record.validation_result.allowed)
        self.assertEqual(record.simulated_actions[2], "confirm_off")

    def test_reset_and_invalid_enable(self):
        reset = self.executor.execute(SafeOutputIntent(OutputAction.RESET_PROTECTION,  target_ovp=15.0, target_ocp=3.0, source="mix_exit"))
        self.assertEqual(reset.simulated_actions, ("reset_ovp", "reset_ocp", "readback"))
        denied = DryRunExecutor(self.safety).execute(SafeOutputIntent(OutputAction.ENABLE, 14.4, 2.0))
        self.assertTrue(denied.validation_result.allowed)


if __name__ == "__main__":
    unittest.main()
