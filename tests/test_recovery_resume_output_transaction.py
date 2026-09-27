import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

os.environ.setdefault("TG_TOKEN", "123456:ABCDEFGHIJKLMNOPQRSTUVWXYZ123456789")

from runtime import v2_runtime as runtime


class FakeHass:
    def __init__(self, *, enable=True, final_verify=True):
        self.enable = enable
        self.final_verify = final_verify
        self.calls = []

    async def set_ovp(self, value):
        self.calls.append(("set_ovp", float(value)))
        return True

    async def set_voltage(self, value):
        self.calls.append(("set_voltage", float(value)))
        return True

    async def set_ocp(self, value):
        self.calls.append(("set_ocp", float(value)))
        return True

    async def set_current(self, value):
        self.calls.append(("set_current", float(value)))
        return True

    async def turn_on(self, *_args):
        self.calls.append(("turn_on",))
        return self.enable

    async def turn_off(self, *_args):
        self.calls.append(("turn_off",))
        return True

    async def verify_live_programming(self, **kwargs):
        self.calls.append(("verify_live_programming", dict(kwargs)))
        return self.final_verify


class FakeController:
    def __init__(self):
        self._last_known_output_on = False
        self.current_stage = "SAFE_WAIT"
        self.commits = []

    def commit_verified_enable_transition(self, transition, **kwargs):
        self.commits.append((dict(transition), dict(kwargs)))
        self.current_stage = "MAIN"
        return {
            "log_event": "START | RECOVERY_SAFE_WAIT_TO_MAIN",
            "notify": "resume verified",
        }


class RecoveryResumeOutputTransactionTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _actions():
        return {
            "set_voltage": 14.8,
            "set_current": 9.0,
            "set_ovp": 14.9,
            "set_ocp": 9.1,
            "turn_on": True,
            "verified_enable_transition": {
                "kind": "recovery_safe_wait_to_main",
                "session_id": "session-1",
                "started_at": 1000.0,
                "reason": "threshold",
            },
        }

    async def _run(self, hass):
        controller = FakeController()
        events = []
        notices = []
        live = {"set_current": 1.8}
        with patch.object(runtime, "hass", hass), patch.object(
            runtime, "charge_controller", controller
        ), patch.object(runtime.asyncio, "sleep", new=AsyncMock()), patch.object(
            runtime, "log_event", side_effect=lambda *args: events.append(args)
        ), patch.object(
            runtime, "_charge_notify", side_effect=lambda *args, **kwargs: notices.append((args, kwargs))
        ), patch.object(runtime.time, "time", return_value=2000.0):
            result = await runtime._apply_controller_output_actions(
                self._actions(),
                live,
                battery_v=14.3,
                current=0.0,
                temp=25.0,
                ah=12.0,
            )
        return result, controller, events, notices

    async def test_agm_resume_orders_ovp_ocp_and_commits_only_after_final_readback(self):
        hass = FakeHass(enable=True, final_verify=True)
        enabled, controller, events, notices = await self._run(hass)
        self.assertTrue(enabled)
        self.assertEqual(
            [call[0] for call in hass.calls],
            [
                "set_ovp",
                "set_voltage",
                "set_ocp",
                "set_current",
                "turn_on",
                "set_ocp",
                "verify_live_programming",
            ],
        )
        self.assertEqual(hass.calls[0][1], 14.9)
        self.assertEqual(hass.calls[1][1], 14.8)
        self.assertEqual(hass.calls[2][1], runtime.IDLE_SAFE_OCP)
        self.assertEqual(hass.calls[3][1], 9.0)
        self.assertEqual(hass.calls[5][1], 9.1)
        verify = hass.calls[6][1]
        self.assertEqual(verify["voltage_v"], 14.8)
        self.assertEqual(verify["current_a"], 9.0)
        self.assertEqual(verify["ovp_v"], 14.9)
        self.assertEqual(verify["ocp_a"], 9.1)
        self.assertEqual(len(controller.commits), 1)
        self.assertTrue(controller._last_known_output_on)
        self.assertEqual(len(events), 1)
        self.assertEqual(len(notices), 1)

    async def test_failed_turn_on_never_commits_safe_wait_to_main(self):
        hass = FakeHass(enable=False, final_verify=True)
        enabled, controller, events, notices = await self._run(hass)
        self.assertFalse(enabled)
        self.assertEqual(controller.commits, [])
        self.assertFalse(controller._last_known_output_on)
        self.assertEqual(events, [])
        self.assertEqual(notices, [])
        self.assertNotIn("verify_live_programming", [call[0] for call in hass.calls])
        # Final OCP is still restored while Output remains OFF so the next attempt
        # starts from the intended protection envelope rather than the wide settle OCP.
        self.assertEqual(hass.calls[-1], ("set_ocp", 9.1))

    async def test_failed_final_ocp_readback_forces_off_and_withholds_stage_commit(self):
        hass = FakeHass(enable=True, final_verify=False)
        enabled, controller, events, notices = await self._run(hass)
        self.assertFalse(enabled)
        self.assertEqual(controller.commits, [])
        self.assertFalse(controller._last_known_output_on)
        names = [call[0] for call in hass.calls]
        self.assertEqual(names[-2:], ["verify_live_programming", "turn_off"])
        self.assertEqual(events, [])
        self.assertEqual(notices, [])


if __name__ == "__main__":
    unittest.main()
