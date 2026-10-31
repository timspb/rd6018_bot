import os
import json
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

os.environ.setdefault("TG_TOKEN", "123456:ABCDEFGHIJKLMNOPQRSTUVWXYZ123456789")

from runtime import production_runtime as runtime
from application.controller_action_execution import execute_controller_action_batch
from application.execution_port import get_or_create_execution_port
from production_controller import create_production_charge_host
from pb_domain import ChargeIntent
from runtime.charge.strategy.main_current_guard import MainCurrentGuard
from runtime.charge.strategy.recovery_safe_wait import RecoverySafeWaitContinuation


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
        self.stopped = []

    def stop(self, clear_session=True):
        self.stopped.append(clear_session)
        self.current_stage = "IDLE"

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
        self.assertIn(("set_ocp", 9.1), hass.calls)
        self.assertEqual(hass.calls[-1], ("turn_off",))
        self.assertEqual(controller.stopped, [True])

    async def test_failed_final_ocp_readback_forces_off_and_withholds_stage_commit(self):
        hass = FakeHass(enable=True, final_verify=False)
        enabled, controller, events, notices = await self._run(hass)
        self.assertFalse(enabled)
        self.assertEqual(controller.commits, [])
        self.assertFalse(controller._last_known_output_on)
        names = [call[0] for call in hass.calls]
        self.assertEqual(names[-3:], ["verify_live_programming", "turn_off", "turn_off"])
        self.assertEqual(controller.stopped, [True])
        self.assertEqual(events, [])
        self.assertEqual(notices, [])

    async def test_production_guarded_desulfation_return_restores_and_persists_main_limit(self):
        class NativeOwner:
            def __init__(self):
                self.output = 0
                self.v = 14.8
                self.i = 5.0
                self.ovp = 14.9
                self.ocp = 5.1
                self.stamp = 1.0
                self.calls = []

            def snapshot(self):
                self.stamp += 1
                vals = {
                    "output_state_code_v2": self.output, "current": 0.0,
                    "set_current_readback_v2": self.i, "ocp_readback_v2": self.ocp,
                    "protection_code": 0,
                }
                vals["_meta"] = {
                    key: {"source": "esp_native_api", "native_type": "SensorState",
                          "subscription_timestamp_monotonic": self.stamp, "age_s": 0}
                    for key in ("output_state_code_v2", "current", "set_current_readback_v2",
                                "ocp_readback_v2", "protection_code")
                }
                return vals

            async def get_all_live(self): return self.snapshot()
            async def turn_off(self): self.calls.append(("off",)); self.output = 0; return True
            async def turn_on(self): self.calls.append(("on",)); self.output = 1; return True
            async def set_ovp(self, value): self.calls.append(("ovp", value)); self.ovp = value; return True
            async def set_voltage(self, value): self.calls.append(("voltage", value)); self.v = value; return True
            async def set_ocp(self, value): self.calls.append(("ocp", value)); self.ocp = value; return True
            async def set_current(self, value): self.calls.append(("current", value)); self.i = value; return True
            async def verify_live_programming(self, **kwargs):
                self.calls.append(("verify", kwargs))
                return (self.v == kwargs["voltage_v"] and self.i == kwargs["current_a"]
                        and self.ovp == kwargs["ovp_v"] and self.ocp == kwargs["ocp_a"])

        owner = NativeOwner()
        controller = create_production_charge_host(owner)
        controller.start("EFB", 72)
        controller.current_stage = controller.STAGE_SAFE_WAIT
        controller._v2_intent = ChargeIntent.RECOVERY
        controller._v2_battery_id = "battery-return-test"
        controller._recovery_safe_wait = RecoverySafeWaitContinuation(
            source_stage=controller.STAGE_DESULFATION, next_stage=controller.STAGE_MAIN,
            target_voltage_v=14.8, target_current_a=7.2, started_at=1000.0,
            session_id=controller._v2_trace_session_id, recovery_attempt=1,
            agm_stage_idx=0, session_generation=controller._v2_trace_started_at,
        )
        controller._safe_wait_next_stage = controller.STAGE_MAIN
        controller._safe_wait_target_v = 14.8
        controller._safe_wait_target_i = 7.2
        controller._safe_wait_start = 1000.0
        controller._device_set_voltage = 14.8
        controller._device_set_current = 5.0
        old = MainCurrentGuard.start(
            session_id=controller._v2_trace_session_id,
            battery_id=controller._v2_battery_id, segment_id="main-before-desulfation",
            capacity_ah=72, recipe_initial_current_a=7.2, now_s=1.0,
        )
        from dataclasses import replace
        controller._main_current_guard = replace(old, hardware_limit_a=5.0)
        controller._main_current_guard_revision = None
        port = get_or_create_execution_port(SimpleNamespace(hass=owner))
        with tempfile.TemporaryDirectory() as temp_dir, patch(
            "charge_controller.SESSION_FILE", os.path.join(temp_dir, "charge_session.json")
        ):
            controller._save_session(14.3, 0.0, 12.0)
            actions = {
                "set_voltage": 14.8, "set_current": 7.2, "set_ovp": 14.9,
                "set_ocp": 7.3, "turn_on": True,
                "verified_enable_transition": {
                    "kind": "recovery_safe_wait_to_main",
                    "session_id": controller._v2_trace_session_id,
                    "session_generation": controller._v2_trace_started_at,
                    "started_at": 1000.0, "reason": "threshold",
                },
            }
            result = await execute_controller_action_batch(
                actions, owner.snapshot(), execution_port=port, controller=controller,
                battery_v=14.3, current=0.0, temp=25.0, ah=12.0,
                max_stage_current_a=12.0, ocp_offset_a=0.1, idle_safe_ocp_a=12.0,
                stabilize_delay_s=0.0, recipe_voltage_ceiling_v=17.5,
                has_ovp=True, has_ocp=True, notify=lambda *a, **k: None,
                log_event=lambda *a: None, logger=__import__("logging").getLogger("test"),
            )
            self.assertTrue(result)
            names = [call[0] for call in owner.calls]
            self.assertIn(("current", 7.2), owner.calls)
            self.assertIn(("ocp", 7.3), owner.calls)
            self.assertLess(names.index("off"), names.index("current"))
            self.assertLess(names.index("ocp"), names.index("current"))
            self.assertEqual(controller.current_stage, controller.STAGE_MAIN)
            self.assertEqual(controller._main_current_guard.hardware_limit_a, 7.2)
            self.assertEqual(controller._main_current_guard.accrued_output_on_s, 0.0)
            self.assertEqual(controller._main_current_guard.next_deadline_s, 1800.0)
            with open(os.path.join(temp_dir, "charge_session.json"), encoding="utf-8") as stream:
                document = json.load(stream)
            self.assertEqual(document["stage"], controller.STAGE_MAIN)
            self.assertEqual(document["main_current_guard_v1"]["snapshot"]["hardware_limit_a"], 7.2)

    async def test_guarded_desulfation_return_never_programs_if_output_is_on(self):
        class Owner:
            def __init__(self): self.calls = []
            async def get_all_live(self):
                return {
                    "output_state_code_v2": 1, "current": 1.0,
                    "set_current_readback_v2": 5.0, "ocp_readback_v2": 5.1,
                    "protection_code": 0,
                    "_meta": {key: {"source": "esp_native_api", "native_type": "SensorState",
                                   "subscription_timestamp_monotonic": float(i), "age_s": 0}
                              for i, key in enumerate(("output_state_code_v2", "current",
                                  "set_current_readback_v2", "ocp_readback_v2", "protection_code"), 1)},
                }
            async def turn_off(self): self.calls.append(("off",)); return True
            async def set_ovp(self, value): self.calls.append(("ovp", value)); return True
            async def set_voltage(self, value): self.calls.append(("voltage", value)); return True
            async def set_ocp(self, value): self.calls.append(("ocp", value)); return True
            async def set_current(self, value): self.calls.append(("current", value)); return True

        owner = Owner()
        controller = create_production_charge_host(owner)
        controller.current_stage = controller.STAGE_SAFE_WAIT
        controller._v2_trace_session_id = "a" * 32
        controller._v2_battery_id = "battery-return-test"
        controller._v2_trace_started_at = 1000.0
        controller._main_current_guard = MainCurrentGuard.start(
            session_id=controller._v2_trace_session_id,
            battery_id=controller._v2_battery_id, segment_id="main-on-1",
            capacity_ah=72, recipe_initial_current_a=7.2, now_s=1.0,
        )
        controller._recovery_safe_wait = RecoverySafeWaitContinuation(
            source_stage=controller.STAGE_DESULFATION, next_stage=controller.STAGE_MAIN,
            target_voltage_v=14.8, target_current_a=7.2, started_at=1000.0,
            session_id=controller._v2_trace_session_id, recovery_attempt=0,
            agm_stage_idx=0, session_generation=1000.0,
        )
        port = get_or_create_execution_port(SimpleNamespace(hass=owner))
        actions = self._actions()
        actions["verified_enable_transition"].update(
            session_id=controller._v2_trace_session_id, session_generation=1000.0,
        )
        result = await execute_controller_action_batch(
            actions, {}, execution_port=port, controller=controller,
            battery_v=14.3, current=1.0, temp=25.0, ah=12.0,
            max_stage_current_a=12.0, ocp_offset_a=0.1, idle_safe_ocp_a=12.0,
            stabilize_delay_s=0.0, recipe_voltage_ceiling_v=17.5,
            has_ovp=True, has_ocp=True, notify=lambda *a, **k: None,
            log_event=lambda *a: None, logger=__import__("logging").getLogger("test"),
        )
        self.assertFalse(result)
        self.assertFalse(any(call[0] in {"ovp", "voltage", "ocp", "current", "on"}
                             for call in owner.calls))

    async def test_desulfation_return_failures_durably_compensate_and_allow_retry(self):
        class NativeOwner:
            def __init__(self, failure):
                self.failure = failure
                self.output, self.v, self.i, self.ovp, self.ocp = 0, 14.8, 5.0, 14.9, 5.1
                self.stamp = 1.0
                self.calls = []

            def snapshot(self):
                self.stamp += 1
                values = {"output_state_code_v2": self.output, "current": 0.0,
                          "set_current_readback_v2": self.i, "ocp_readback_v2": self.ocp,
                          "protection_code": 0}
                values["_meta"] = {key: {
                    "source": "esp_native_api", "native_type": "SensorState",
                    "subscription_timestamp_monotonic": self.stamp, "age_s": 0,
                } for key in ("output_state_code_v2", "current", "set_current_readback_v2",
                              "ocp_readback_v2", "protection_code")}
                return values

            async def get_all_live(self): return self.snapshot()
            async def turn_off(self): self.calls.append("off"); self.output = 0; return True
            async def turn_on(self):
                self.calls.append("on")
                if self.failure == "enable": return False
                self.output = 1
                return True
            async def set_ovp(self, value): self.ovp = value; return True
            async def set_voltage(self, value): self.v = value; return True
            async def set_ocp(self, value): self.ocp = value; return True
            async def set_current(self, value): self.i = value; return True
            async def verify_live_programming(self, **kwargs):
                return self.failure != "final" and self.output == 1

        actions = {
            "set_voltage": 14.8, "set_current": 7.2, "set_ovp": 14.9,
            "set_ocp": 7.3, "turn_on": True,
            "verified_enable_transition": {"kind": "recovery_safe_wait_to_main"},
        }
        for failure in ("enable", "final"):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as temp_dir:
                owner = NativeOwner(failure)
                controller = create_production_charge_host(owner)
                controller.start("EFB", 72)
                controller.current_stage = controller.STAGE_SAFE_WAIT
                controller._v2_intent = ChargeIntent.RECOVERY
                controller._v2_battery_id = "battery-return-failure"
                sid = controller._v2_trace_session_id
                controller._recovery_safe_wait = RecoverySafeWaitContinuation(
                    source_stage=controller.STAGE_DESULFATION, next_stage=controller.STAGE_MAIN,
                    target_voltage_v=14.8, target_current_a=7.2, started_at=1000.0,
                    session_id=sid, recovery_attempt=1, agm_stage_idx=0,
                    session_generation=controller._v2_trace_started_at,
                )
                controller._safe_wait_next_stage = controller.STAGE_MAIN
                controller._safe_wait_target_v, controller._safe_wait_target_i = 14.8, 7.2
                controller._safe_wait_start = 1000.0
                controller._device_set_voltage, controller._device_set_current = 14.8, 5.0
                from dataclasses import replace
                controller._main_current_guard = replace(MainCurrentGuard.start(
                    session_id=sid, battery_id=controller._v2_battery_id,
                    segment_id="main-before-desulfation", capacity_ah=72,
                    recipe_initial_current_a=7.2, now_s=1.0,
                ), hardware_limit_a=5.0)
                port = get_or_create_execution_port(SimpleNamespace(hass=owner))
                path = os.path.join(temp_dir, "charge_session.json")
                with patch("charge_controller.SESSION_FILE", path):
                    controller._save_session(14.3, 0.0, 12.0)
                    action = dict(actions)
                    action["verified_enable_transition"] = {
                        "kind": "recovery_safe_wait_to_main", "session_id": sid,
                        "session_generation": controller._v2_trace_started_at,
                        "started_at": 1000.0, "reason": "threshold",
                    }
                    kwargs = dict(
                        execution_port=port, controller=controller, battery_v=14.3,
                        current=0.0, temp=25.0, ah=12.0, max_stage_current_a=12.0,
                        ocp_offset_a=0.1, idle_safe_ocp_a=12.0, stabilize_delay_s=0.0,
                        recipe_voltage_ceiling_v=17.5, has_ovp=True, has_ocp=True,
                        notify=lambda *a, **k: None, log_event=lambda *a: None,
                        logger=__import__("logging").getLogger("test"),
                    )
                    self.assertFalse(await execute_controller_action_batch(
                        action, owner.snapshot(), **kwargs))
                    with open(path, encoding="utf-8") as stream:
                        document = json.load(stream)
                    guard_snapshot = document["main_current_guard_v1"]["snapshot"]
                    self.assertEqual(document["stage"], controller.STAGE_SAFE_WAIT)
                    self.assertEqual(guard_snapshot["hardware_limit_a"], 5.0)
                    self.assertEqual(controller.current_stage, controller.STAGE_SAFE_WAIT)
                    self.assertEqual(controller._main_current_guard.hardware_limit_a, 5.0)
                    self.assertEqual(owner.output, 0)
                    self.assertGreaterEqual(owner.calls.count("off"), 1)

                    # The compensated journal and guard remain retryable.
                    owner.failure = ""
                    self.assertTrue(await execute_controller_action_batch(
                        action, owner.snapshot(), **kwargs))
                    with open(path, encoding="utf-8") as stream:
                        document = json.load(stream)
                    self.assertEqual(document["stage"], controller.STAGE_MAIN)
                    self.assertEqual(document["main_current_guard_v1"]["snapshot"]["hardware_limit_a"], 7.2)


if __name__ == "__main__":
    unittest.main()