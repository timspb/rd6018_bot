import unittest

from runtime.bench import (
    BenchRunner, controlled_enable_scenario, discovery_scenario,
    verified_off_scenario,
)


class V3BenchValidationTests(unittest.TestCase):
    def test_scenarios_have_required_order(self):
        self.assertEqual([step.name for step in verified_off_scenario("op").expected_steps], [
            "disable_output", "verify_off", "verify_current", "reset_protection"
        ])
        self.assertEqual(discovery_scenario("op").expected_steps[0].name, "discover_capabilities")
        self.assertEqual(controlled_enable_scenario("op").expected_steps[-1].name, "verify_on")

    def test_preflight_failure_is_fail_closed(self):
        result = BenchRunner().run(verified_off_scenario("op"))
        self.assertFalse(result.passed)
        self.assertEqual(result.evidence[0].command, "preflight")

    def test_planning_does_not_execute_transport(self):
        calls = []
        result = BenchRunner().run(discovery_scenario("op"), executor=lambda command: calls.append(command))
        self.assertTrue(result.passed)
        self.assertEqual(calls, [])

