import unittest
from pathlib import Path
from types import SimpleNamespace

from application.execution_port import ExecutionPort, get_or_create_execution_port

from application.session_recovery_guard import SessionRecoveryGuard


class SessionRecoveryGuardTests(unittest.TestCase):
    def test_sticky_until_operator_rearm_with_positive_off_confirmation(self):
        guard = SessionRecoveryGuard()
        self.assertTrue(guard.may_run_automatic_control())
        state = guard.quarantine("verified_off")
        self.assertTrue(state.quarantined)
        self.assertEqual(state.reason, "verified_off")
        self.assertFalse(guard.operator_rearm(confirmed_output_off=False))
        self.assertFalse(guard.may_run_automatic_control())
        self.assertTrue(guard.operator_rearm(confirmed_output_off=True))
        self.assertTrue(guard.may_run_automatic_control())

    def test_first_ambiguous_failure_reason_is_stable(self):
        guard = SessionRecoveryGuard()
        guard.quarantine("current")
        guard.quarantine("verified_on")
        self.assertEqual(guard.state.reason, "current")

    def test_canonical_start_rejects_quarantine_before_live_io_or_rollback(self):
        source = Path("application/start_transaction_service.py").read_text(encoding="utf-8")
        start = source.index("async def start_profile_transactional")
        end = source.index("live = await app.hass.get_all_live()", start)
        preflight = source[start:end]
        self.assertIn("session_recovery_guard.quarantined", preflight)
        self.assertNotIn("_confirm_failed_start_is_off", preflight)


class ExecutionPortQuarantineTests(unittest.IsolatedAsyncioTestCase):
    async def test_guard_survives_execution_owner_rebind(self):
        app = SimpleNamespace(hass=object())
        first = get_or_create_execution_port(app)
        first.session_recovery_guard.quarantine("verified_off")
        app.hass = object()
        second = get_or_create_execution_port(app)
        self.assertIsNot(first, second)
        self.assertIs(first.session_recovery_guard, second.session_recovery_guard)
        self.assertTrue(second.session_recovery_guard.quarantined)

    async def test_blocks_on_and_manual_setters_but_keeps_verified_off(self):
        class Owner:
            def __init__(self):
                self.calls = []

            async def turn_on(self):
                self.calls.append("on")
                return True

            async def turn_off(self):
                self.calls.append("off")
                return True

            async def set_voltage(self, value):
                self.calls.append(("voltage", value))
                return True

            async def set_current(self, value):
                self.calls.append(("current", value))
                return True

        owner = Owner()
        port = ExecutionPort(owner)
        port.session_recovery_guard.quarantine("verified_on")
        self.assertFalse(await port.request_verified_on())
        self.assertFalse(await port.program_voltage(14.4))
        self.assertFalse(await port.program_current(2.0))
        self.assertEqual(await port.program_voltage_current(14.4, 2.0), (False, False))
        self.assertTrue(await port.request_verified_off())
        self.assertEqual(owner.calls, ["off"])

    async def test_controller_batch_cannot_smuggle_on_or_setpoints(self):
        class Owner:
            def __init__(self):
                self.calls = []

            async def turn_off(self):
                self.calls.append("off")
                return True

            async def turn_on(self):
                self.calls.append("on")
                return True

        owner = Owner()
        port = ExecutionPort(owner)
        port.session_recovery_guard.quarantine("current")
        result = await port.execute_controller_actions(
            {"turn_on": True, "set_voltage": 14.4, "set_current": 2.0}, {},
            max_stage_current_a=20.0, ocp_offset_a=1.0, idle_safe_ocp_a=1.0,
            stabilize_delay_s=0.0, recipe_voltage_ceiling_v=16.5,
            has_ovp=False, has_ocp=False,
        )
        self.assertFalse(result.enabled)
        self.assertEqual(owner.calls, [])


if __name__ == "__main__":
    unittest.main()
