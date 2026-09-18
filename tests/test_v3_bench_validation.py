import unittest

from runtime.bench import (
    BenchRunner, controlled_enable_scenario, discovery_scenario,
    validate_bench_environment,
    verified_off_scenario,
)
from runtime.config.loader import load_config


class V3BenchValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = load_config("config")

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

    def test_environment_requires_explicit_role_and_existing_credentials(self):
        result = validate_bench_environment(self.config, environ={})
        self.assertFalse(result.allowed)
        self.assertEqual(result.missing_environment, (
            "RD_ENV_ROLE", "HA_URL", "HA_TOKEN", "ESPHOME_API_HOST",
            "ESPHOME_API_PORT", "ESPHOME_API_KEY",
        ))

    def test_environment_requires_read_only_evidence(self):
        env = {
            "RD_ENV_ROLE": "bench", "HA_URL": "http://ha.example:8123",
            "HA_TOKEN": "ha", "ESPHOME_API_HOST": "esp.example",
            "ESPHOME_API_PORT": "6053", "ESPHOME_API_KEY": "esp",
        }
        result = validate_bench_environment(self.config, environ=env)
        self.assertFalse(result.allowed)
        self.assertIn("read_only_connectivity_not_verified", result.reasons)
        self.assertIn("read_only_hardware_readback_not_verified", result.reasons)

    def test_environment_passes_only_after_read_only_evidence(self):
        env = {
            "RD_ENV_ROLE": "bench", "HA_URL": "http://ha.example:8123",
            "HA_TOKEN": "ha", "ESPHOME_API_HOST": "esp.example",
            "ESPHOME_API_PORT": "6053", "ESPHOME_API_KEY": "esp",
        }
        result = validate_bench_environment(self.config, environ=env, read_only_connectivity=True, readback_valid=True)
        self.assertTrue(result.allowed)

    def test_production_role_is_rejected(self):
        env = {
            "RD_ENV_ROLE": "production", "HA_URL": "http://ha.example:8123",
            "HA_TOKEN": "ha", "ESPHOME_API_HOST": "esp.example",
            "ESPHOME_API_PORT": "6053", "ESPHOME_API_KEY": "esp",
        }
        result = validate_bench_environment(self.config, environ=env, read_only_connectivity=True, readback_valid=True)
        self.assertFalse(result.allowed)
        self.assertIn("RD_ENV_ROLE", result.missing_environment)

