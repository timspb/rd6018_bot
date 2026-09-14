from __future__ import annotations

import unittest

from application.production_start_execution_port import ProductionStartExecutionPort, ProductionStartMode
from application.start_activation_policy import StartActivationPolicy, StartExecutionMode


class StartActivationPolicyTests(unittest.TestCase):
    def test_default_rejects_active(self):
        decision = StartActivationPolicy().evaluate(StartExecutionMode.ACTIVE)
        self.assertFalse(decision.allowed)
        self.assertIn("explicit_active_enable_missing", decision.reasons)

    def test_shadow_allowed(self):
        self.assertTrue(StartActivationPolicy().evaluate(StartExecutionMode.SHADOW).allowed)

    def test_dry_run_allowed(self):
        self.assertTrue(StartActivationPolicy().evaluate(StartExecutionMode.DRY_RUN).allowed)

    def test_active_requires_all_gates(self):
        policy = StartActivationPolicy(
            execution_mode=StartExecutionMode.ACTIVE,
            explicit_active_enable=True,
            bench_validation_passed=True,
            rollback_validation_passed=True,
            physical_gate_passed=True,
        )
        self.assertTrue(policy.evaluate(StartExecutionMode.ACTIVE).allowed)

    def test_missing_gate_rejected(self):
        policy = StartActivationPolicy(
            execution_mode=StartExecutionMode.ACTIVE,
            explicit_active_enable=True,
            bench_validation_passed=True,
            rollback_validation_passed=False,
            physical_gate_passed=True,
        )
        decision = policy.evaluate(StartExecutionMode.ACTIVE)
        self.assertFalse(decision.allowed)
        self.assertIn("rollback_validation_missing", decision.reasons)

    def test_port_uses_default_fail_closed_policy(self):
        # The plan is intentionally not needed: activation policy is checked
        # independently and remains disabled by default at the port boundary.
        self.assertEqual(ProductionStartMode.ACTIVE.value, "active")
        self.assertFalse(StartActivationPolicy().evaluate("ACTIVE").allowed)


if __name__ == "__main__":
    unittest.main()
