from datetime import datetime, timedelta, timezone
import unittest

from application.decision_cutover_operational_readiness import (
    DecisionCutoverOperationalReadinessModel,
)
from application.decision_cutover_readiness import Stage1SafetyGates
from application.start_activation_policy import StartExecutionMode
from application.start_authority_provider import StartAuthorityProvider
from application.start_authority_runtime import StartAuthorityRuntime
from application.production_start_execution_port import ProductionStartExecutionPort


NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def approved_snapshot(*, expires_at=None):
    model = DecisionCutoverOperationalReadinessModel()
    model.evaluate_health(Stage1SafetyGates(True, True, True, True, True), timestamp=NOW)
    model.approve(
        operator="operator",
        source="bench-approval",
        rollback_authority="V2",
        expires_at=expires_at or NOW + timedelta(hours=1),
        timestamp=NOW,
    )
    return model


class StartAuthorityProviderTests(unittest.TestCase):
    def setUp(self):
        self.provider = StartAuthorityProvider(now=lambda: NOW)

    def test_no_approval_denies_active(self):
        policy = self.provider.policy_from_snapshot(None)
        self.assertNotEqual(StartExecutionMode.ACTIVE, policy.execution_mode)
        self.assertFalse(policy.explicit_active_enable)

    def test_expired_approval_denies_active(self):
        model = approved_snapshot(expires_at=NOW + timedelta(seconds=1))
        expired_provider = StartAuthorityProvider(now=lambda: NOW + timedelta(seconds=2))
        policy = expired_provider.policy_from_snapshot(model.snapshot(), bench_validation_passed=True,
                                                       rollback_validation_passed=True,
                                                       physical_gate_passed=True)
        self.assertNotEqual(StartExecutionMode.ACTIVE, policy.execution_mode)

    def test_revoked_approval_denies_active(self):
        model = approved_snapshot()
        model.revoke(source="test", reason="revoked", timestamp=NOW)
        policy = self.provider.policy_from_snapshot(model.snapshot(), bench_validation_passed=True,
                                                    rollback_validation_passed=True,
                                                    physical_gate_passed=True)
        self.assertNotEqual(StartExecutionMode.ACTIVE, policy.execution_mode)

    def test_all_evidence_pass_generates_active_policy(self):
        model = approved_snapshot()
        policy = self.provider.policy_from_snapshot(model.snapshot(), bench_validation_passed=True,
                                                    rollback_validation_passed=True,
                                                    physical_gate_passed=True)
        self.assertEqual(StartExecutionMode.ACTIVE, policy.execution_mode)
        self.assertTrue(policy.explicit_active_enable)
        self.assertTrue(policy.bench_validation_passed)
        self.assertTrue(policy.rollback_validation_passed)
        self.assertTrue(policy.physical_gate_passed)

    def test_physical_gate_failure_denies_active(self):
        model = approved_snapshot()
        policy = self.provider.policy_from_snapshot(model.snapshot(), bench_validation_passed=True,
                                                    rollback_validation_passed=True,
                                                    physical_gate_passed=False)
        self.assertNotEqual(StartExecutionMode.ACTIVE, policy.execution_mode)

    def test_wrong_rollback_authority_denies_active(self):
        model = DecisionCutoverOperationalReadinessModel()
        model.evaluate_health(Stage1SafetyGates(True, True, True, True, True), timestamp=NOW)
        model.approve(operator="operator", source="test", rollback_authority="wrong",
                      expires_at=NOW + timedelta(hours=1), timestamp=NOW)
        policy = self.provider.policy_from_snapshot(model.snapshot(), bench_validation_passed=True,
                                                    rollback_validation_passed=True,
                                                    physical_gate_passed=True)
        self.assertNotEqual(StartExecutionMode.ACTIVE, policy.execution_mode)

    def test_runtime_approval_produces_current_policy(self):
        runtime = StartAuthorityRuntime()
        runtime.update_evidence(
            Stage1SafetyGates(True, True, True, True, True),
            bench_validation_passed=True,
            rollback_validation_passed=True,
            physical_gate_passed=True,
            timestamp=NOW,
        )
        runtime.approve(
            operator="operator", source="bench", scope="one-run",
            correlation_id="corr-1", rollback_authority="V2",
            expires_at=NOW + timedelta(hours=1), timestamp=NOW,
        )
        policy = StartAuthorityProvider(runtime, now=lambda: NOW).current_policy()
        self.assertEqual(StartExecutionMode.ACTIVE, policy.execution_mode)

    def test_runtime_restart_without_persistence_denies_active(self):
        self.assertNotEqual(StartExecutionMode.ACTIVE, StartAuthorityProvider(StartAuthorityRuntime()).current_policy().execution_mode)

    def test_execution_port_reads_generated_runtime_policy(self):
        runtime = StartAuthorityRuntime()
        runtime.update_evidence(
            Stage1SafetyGates(True, True, True, True, True),
            bench_validation_passed=True,
            rollback_validation_passed=True,
            physical_gate_passed=True,
            timestamp=NOW,
        )
        runtime.approve(
            operator="operator", source="bench", scope="one-run",
            correlation_id="corr-port", rollback_authority="V2",
            expires_at=NOW + timedelta(hours=1), timestamp=NOW,
        )
        provider = StartAuthorityProvider(runtime, now=lambda: NOW)
        port = ProductionStartExecutionPort(activation_policy_provider=provider.current_policy)
        self.assertEqual(StartExecutionMode.ACTIVE, port._activation_policy().execution_mode)


if __name__ == "__main__":
    unittest.main()
