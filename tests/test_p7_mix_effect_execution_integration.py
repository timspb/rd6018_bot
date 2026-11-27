"""Integrated source/fake proof across the existing MIX/effect/execution/HMI owners."""

import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import operator_hmi as hmi
from application.controller_action_execution import execute_controller_action_batch
from application.execution_port import ExecutionPort
from charge_controller import ManagedChargeController
from recovery_policy import RecoveryDecision
from runtime.charge.decisions import AuthorityAction
from runtime.charge.runtime.main_scaffold import apply_main_authority_tick
from runtime.ui.telegram.charge import CHARGE_CALLBACK_DATA


def _live(switch="on", *, stale=False):
    age = timedelta(minutes=5) if stale else timedelta(0)
    stamp = (datetime.now(timezone.utc) - age).isoformat()
    meta = {key: {"last_reported": stamp, "last_updated": stamp}
            for key in ("switch", "current", "battery_voltage", "temp_ext", "temp_int",
                        "is_cv", "is_cc", "regulation_code", "set_voltage", "set_current")}
    return {"switch": switch, "current": 0.9, "battery_voltage": 16.4,
            "temp_ext": 25.0, "temp_int": 30.0, "is_cv": "on", "is_cc": "off",
            "regulation_code": 0, "protection_code": 0,
            "set_voltage": 16.5, "set_current": 1.0,
            "_meta": meta}


def _callbacks(markup):
    return {button.callback_data for row in markup.inline_keyboard
            for button in row if button.callback_data}


class _PhysicalHal:
    """Fake setter target behind the real ExecutionPort; it has no ON method."""
    def __init__(self):
        self.writes = []

    async def set_voltage(self, value):
        self.writes.append(("voltage", value))
        return True

    async def set_current(self, value):
        self.writes.append(("current", value))
        return True


class MixEffectExecutionIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_mix_effect_dispatch_and_app_local_fail_closed_hmi(self):
        controller = ManagedChargeController(object())
        controller.battery_type, controller.ah_capacity = "Ca/Ca", 72
        controller.current_stage = controller.STAGE_MAIN
        # Explicitly activate the established session history owner; the bare
        # test host defaults to history disabled until an actual START.
        controller._stage_tracking_enabled = True
        controller._v2_intent = "conditioning"
        controller.stage_start_time = 0.0
        record = SimpleNamespace(
            decision=SimpleNamespace(decision=RecoveryDecision.CONTINUE),
            analysis=SimpleNamespace(
                metrics=SimpleNamespace(main_stable_hold_s=0.0),
                sample=SimpleNamespace(is_cc=False),
            ),
        )
        actions = {}
        decision = apply_main_authority_tick(
            controller, record=record, first_stage=None, timestamp_s=73 * 3600.0,
            voltage=14.8, current=0.4, temp=25.0, ah=4.0,
            is_cv=True, actions=actions,
        )
        self.assertIs(decision.action, AuthorityAction.ENTER_MIX)
        self.assertTrue(actions["log_event"].startswith("MIX_STARTED |"))
        physical = _PhysicalHal()
        port = ExecutionPort(physical)
        result = await execute_controller_action_batch(
            actions, _live(), execution_port=port, controller=controller,
            battery_v=16.4, current=0.9, temp=25.0, ah=4.0,
            max_stage_current_a=12.0, recipe_voltage_ceiling_v=16.5,
            notify=lambda *_a, **_k: None, log_event=lambda *_a: None,
            logger=SimpleNamespace(warning=lambda *_a: None, error=lambda *_a: None),
        )
        self.assertIsNone(result)
        self.assertEqual(physical.writes, [
            ("voltage", actions["set_voltage"]), ("current", actions["set_current"]),
        ])
        self.assertNotIn("turn_on", actions)
        self.assertEqual(controller.current_stage, controller.STAGE_MIX)
        self.assertEqual(len(controller._stage_history), 1)
        self.assertEqual(controller._stage_history[0]["to"], controller.STAGE_MIX)

        # The real controller derives activity from its stage; MIX is active.
        self.assertTrue(controller.is_active)
        app_a = SimpleNamespace(charge_controller=controller,
                                manual_session_manager=SimpleNamespace(is_active=False))
        app_b = SimpleNamespace(charge_controller=SimpleNamespace(is_active=False),
                                manual_session_manager=SimpleNamespace(is_active=False))
        state_a = hmi.build_operator_hmi_state(app_a, _live("on"))
        state_b = hmi.build_operator_hmi_state(app_b, _live("off"))
        self.assertTrue(state_a.output_on)
        self.assertNotIn(CHARGE_CALLBACK_DATA, _callbacks(hmi.build_operator_keyboard(app_a, state_a)))
        self.assertIn(CHARGE_CALLBACK_DATA, _callbacks(hmi.build_operator_keyboard(app_b, state_b)))

        stale_telemetry = _live("off")
        stale_stamp = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        stale_telemetry["_meta"]["current"] = {
            "last_reported": stale_stamp, "last_updated": stale_stamp,
        }
        for bad_live in (_live("unknown"), _live("on", stale=True)):
            state = hmi.build_operator_hmi_state(app_b, bad_live)
            callbacks = _callbacks(hmi.build_operator_keyboard(app_b, state))
            self.assertNotIn(CHARGE_CALLBACK_DATA, callbacks)
            self.assertFalse(any(item in callbacks for item in (
                "rd_ownership_adopt", "rd_ownership_hands_off", "rd_managed_adopt",
                "rd_live_mix", "rd_managed_mix",
            )))
            self.assertFalse(getattr(state, "_output_state_known", True))

        # The already-approved freshness predicate marks stale current as
        # untrustworthy. With Output independently proven OFF, a navigation
        # button may remain visible; navigation does not execute START or
        # authorize a controller effect. No new physical writes occur.
        from runtime.ui.components.hmi_live_safety import _operator_telemetry_fresh
        self.assertFalse(_operator_telemetry_fresh(stale_telemetry))
        stale_state = hmi.build_operator_hmi_state(app_b, stale_telemetry)
        self.assertTrue(getattr(stale_state, "_output_state_known", False))
        self.assertNotIn("rd_managed_mix", _callbacks(hmi.build_operator_keyboard(app_b, stale_state)))
        self.assertNotIn("rd_live_mix", _callbacks(hmi.build_operator_keyboard(app_b, stale_state)))
        self.assertEqual(physical.writes, [
            ("voltage", actions["set_voltage"]),
            ("current", actions["set_current"]),
        ])
        self.assertIs(app_a.charge_controller, controller)
        self.assertIsNot(app_b.charge_controller, controller)
        self.assertEqual(physical.writes, [
            ("voltage", actions["set_voltage"]), ("current", actions["set_current"]),
        ])


if __name__ == "__main__":
    unittest.main()
