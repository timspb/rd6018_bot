import unittest

from runtime.output.executor import BenchExecutionShadow, BenchObservation, build_command_plan
from runtime.output.intent import OutputAction, SafeOutputIntent


class V3CommandPlanShadowTests(unittest.TestCase):
    def test_enable_plan_is_non_executable_and_ordered(self):
        plan = build_command_plan(SafeOutputIntent(OutputAction.ENABLE, 14.4, 2.0))
        self.assertFalse(plan.execution_allowed)
        self.assertEqual(plan.steps[-1].name, "enable")
        self.assertEqual(plan.steps[-2].name, "readback_compare")

    def test_disable_requires_confirmed_off_without_protection_reset(self):
        plan = build_command_plan(SafeOutputIntent(OutputAction.DISABLE))
        names = tuple(step.name for step in plan.steps)
        self.assertEqual(names, ("disable", "read_output_state", "confirm_off"))

    def test_shadow_reports_incomplete_off_observation(self):
        plan = build_command_plan(SafeOutputIntent(OutputAction.DISABLE))
        result = BenchExecutionShadow().compare(plan, BenchObservation(("disable",), readback_valid=False))
        self.assertEqual(result.status, "MISMATCH")
        self.assertEqual(result.missing_steps, ("read_output_state", "confirm_off"))

    def test_shadow_match_is_only_observation_comparison(self):
        plan = build_command_plan(SafeOutputIntent(OutputAction.SET_CURRENT, target_current=2.0))
        result = BenchExecutionShadow().compare(plan, BenchObservation(("set_current",), readback_valid=True))
        self.assertEqual(result.status, "MATCH")


if __name__ == "__main__":
    unittest.main()
