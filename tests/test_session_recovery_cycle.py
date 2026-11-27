"""Fake-only behavior checks for the extracted per-observation recovery cycle."""

import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from application.session_recovery_guard import SessionRecoveryGuard
from application.session_recovery_service import (
    SessionRecoveryObservation,
    SessionRecoveryService,
)


class FakePort:
    def __init__(self, guard):
        self.session_recovery_guard = guard
        self.calls = []

    async def program_voltage(self, value):
        self.calls.append(("voltage", value))
        return True

    async def program_current(self, value):
        self.calls.append(("current", value))
        return True

    async def request_verified_off(self):
        self.calls.append(("off",))
        return True

    async def request_verified_on(self):
        self.calls.append(("on",))
        return True


class FakeController:
    STAGE_IDLE = "IDLE"
    STAGE_DONE = "DONE"
    STAGE_COOLING = "COOLING"
    STAGE_SAFE_WAIT = "SAFE_WAIT"

    def __init__(self, stage, *, unavailable=False):
        self.current_stage = stage
        self._was_unavailable = unavailable
        self._d125_startup_observation_seen = True
        self._restore_result = (True, "restored")
        self._restore_stage = None
        self._safe_wait_target_v = 12.8
        self._safe_wait_target_i = 1.0

    def _get_target_v_i(self, _temperature):
        return 14.4, 2.0

    def try_restore_session(self, *_args, **_kwargs):
        if self._restore_stage is not None:
            self.current_stage = self._restore_stage
        return self._restore_result


def observation(*, output_on=False, current=0.0, input_v=230.0):
    return SessionRecoveryObservation(
        output_on=output_on,
        current_a=current,
        temperature_available=True,
        battery_voltage_v=12.5,
        temperature_c=25.0,
        amp_hours=0.0,
        is_cv=False,
        is_cc=False,
        input_voltage_v=input_v,
    )


class SessionRecoveryCycleTests(unittest.IsolatedAsyncioTestCase):
    async def _run(self, controller, observed, *, guard=None, session_exists=True):
        guard = guard or SessionRecoveryGuard()
        port = FakePort(guard)
        getter_calls = []

        def get_port():
            getter_calls.append("get")
            return port

        persistence = SimpleNamespace(restore_allows_auto_enable=lambda _c: True)
        startup = SimpleNamespace(apply_restore_time_corrections=lambda *_a, **_k: None)
        with patch.dict(sys.modules, {
            "runtime.charge.persistence": persistence,
            "runtime.startup_recovery": startup,
        }), patch("application.session_recovery_service.os.path.isfile", return_value=session_exists):
            result = await SessionRecoveryService.run_cycle(
                observation=observed,
                controller=controller,
                live={},
                session_path="charge_session.json",
                minimum_input_voltage_v=float("-inf"),
                execution_port_getter=get_port,
                cap_current=lambda value: min(10.0, value),
            )
        return result, port, getter_calls

    async def test_active_link_only_route_that_requests_verified_on(self):
        controller = FakeController("MAIN", unavailable=True)
        result, port, getters = await self._run(controller, observation())
        self.assertEqual([call[0] for call in port.calls], ["voltage", "current", "on"])
        self.assertTrue(result.output_on)
        self.assertEqual(getters, ["get", "get"])
        self.assertEqual(controller._last_known_output_on, True)
        self.assertEqual(result.effects[0].message, "RESTORE")

    async def test_idle_link_and_already_on_routes_keep_distinct_execution(self):
        idle = FakeController("IDLE", unavailable=True)
        result_b, port_b, _ = await self._run(idle, observation())
        self.assertEqual([call[0] for call in port_b.calls], ["voltage", "current", "on"])
        self.assertFalse(result_b.output_on)

        retained = FakeController("IDLE")
        result_c, port_c, _ = await self._run(
            retained, observation(output_on=True, current=1.0)
        )
        self.assertEqual([call[0] for call in port_c.calls], ["voltage", "current"])
        self.assertTrue(result_c.output_on)
        self.assertIn("Output ON отдельно не подтверждался.", result_c.effects[1].message)

    async def test_restored_safe_wait_preserves_route_specific_off_order(self):
        idle_link = FakeController("IDLE", unavailable=True)
        idle_link._restore_stage = "SAFE_WAIT"
        _, port_b, _ = await self._run(idle_link, observation())
        self.assertEqual(
            [call[0] for call in port_b.calls], ["voltage", "current", "off"]
        )

        output_already_on = FakeController("IDLE")
        output_already_on._restore_stage = "SAFE_WAIT"
        _, port_c, _ = await self._run(
            output_already_on, observation(output_on=True, current=1.0)
        )
        self.assertEqual(
            [call[0] for call in port_c.calls], ["off", "voltage", "current"]
        )

    async def test_quarantine_and_cold_start_suppress_restoration(self):
        guard = SessionRecoveryGuard()
        guard.quarantine("prior")
        quarantined = FakeController("MAIN", unavailable=True)
        result, port, _ = await self._run(quarantined, observation(), guard=guard)
        self.assertTrue(guard.quarantined)
        self.assertEqual(port.calls, [])
        self.assertEqual(result.effects[0].kind, "warning")

        cold = FakeController("MAIN", unavailable=True)
        cold._d125_startup_observation_seen = False
        result, port, _ = await self._run(cold, observation())
        self.assertTrue(cold._d125_startup_observation_seen)
        self.assertEqual(port.calls, [])
        self.assertIsNone(result.last_checkpoint_time)

        no_route = FakeController("DONE", unavailable=True)
        no_route._d125_startup_observation_seen = False
        result, port, getters = await self._run(no_route, observation())
        self.assertTrue(no_route._d125_startup_observation_seen)
        self.assertEqual(result.route.value, "none")
        self.assertEqual(port.calls, [])
        self.assertEqual(getters, ["get"])


if __name__ == "__main__":
    unittest.main()
