import unittest
from datetime import datetime, timedelta, timezone

from application.decision_cutover_readiness import Stage1SafetyGates
from application.operator_authority_interface import OperatorAuthorityInterface
from application.start_activation_policy import StartExecutionMode
from application.start_authority_provider import StartAuthorityProvider
from application.start_authority_runtime import StartAuthorityRuntime


def _gates() -> Stage1SafetyGates:
    return Stage1SafetyGates(True, True, True, True, True)


class OperatorAuthorityInterfaceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 9, 21, tzinfo=timezone.utc)
        self.runtime = StartAuthorityRuntime()
        self.interface = OperatorAuthorityInterface(self.runtime)
        self.provider = StartAuthorityProvider(self.runtime, now=lambda: self.now)

    def _ready(self) -> None:
        self.interface.update_evidence(
            _gates(), bench_validation_passed=True,
            rollback_validation_passed=True, physical_gate_passed=True,
            timestamp=self.now,
        )

    def test_operator_approve_creates_authority(self):
        self._ready()
        result = self.interface.approve(
            operator="operator-1", source="telegram", scope="battery-1",
            expires_in=timedelta(minutes=5), timestamp=self.now,
        )
        self.assertTrue(result.accepted)
        self.assertEqual(result.window.scope, "battery-1")
        self.assertTrue(self.provider.current_policy().evaluate(StartExecutionMode.ACTIVE).allowed)

    def test_no_approval_stays_dry_run(self):
        self._ready()
        self.assertFalse(self.provider.current_policy().evaluate(StartExecutionMode.ACTIVE).allowed)

    def test_approval_requires_existing_evidence(self):
        result = self.interface.approve(
            operator="operator-1", source="telegram", scope="battery-1",
            expires_in=timedelta(minutes=5), timestamp=self.now,
        )
        self.assertFalse(result.accepted)
        self.assertFalse(self.provider.current_policy().evaluate(StartExecutionMode.ACTIVE).allowed)

    def test_expiry_removes_active(self):
        self._ready()
        self.interface.approve(
            operator="operator-1", source="telegram", scope="battery-1",
            expires_in=timedelta(minutes=5), timestamp=self.now,
        )
        self.now += timedelta(minutes=5)
        self.assertFalse(self.provider.current_policy().evaluate(StartExecutionMode.ACTIVE).allowed)

    def test_revoke_removes_active(self):
        self._ready()
        self.interface.approve(
            operator="operator-1", source="telegram", scope="battery-1",
            expires_in=timedelta(minutes=5), timestamp=self.now,
        )
        self.interface.revoke(source="telegram", reason="operator_revoke", timestamp=self.now)
        self.assertFalse(self.provider.current_policy().evaluate(StartExecutionMode.ACTIVE).allowed)

    def test_restart_has_no_authority(self):
        self._ready()
        self.interface.approve(
            operator="operator-1", source="telegram", scope="battery-1",
            expires_in=timedelta(minutes=5), timestamp=self.now,
        )
        restarted = StartAuthorityProvider(StartAuthorityRuntime(), now=lambda: self.now)
        self.assertFalse(restarted.current_policy().evaluate(StartExecutionMode.ACTIVE).allowed)

    def test_telegram_start_does_not_create_approval(self):
        with open("v2_bootstrap.py", encoding="utf-8") as handle:
            source = handle.read()
        start_block = source[source.index('F.data == "v2_battery_start"'):]
        self.assertNotIn(".approve(", start_block)


if __name__ == "__main__":
    unittest.main()
