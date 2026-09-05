import types
import unittest

from operator_dashboard import build_truthful_hmi_state
from operator_hmi import HmiAuthority, HmiProcessState, build_operator_keyboard


class FakeApp:
    def __init__(self):
        self.rd_control_mode_manager = types.SimpleNamespace(hands_off=False)
        self.rd_live_mix_observer = None
        self.charge_controller = types.SimpleNamespace(
            is_active=False,
            current_stage="Main Charge",
            battery_type="Ca/Ca",
            ah_capacity=72,
        )
        self.manual_session_manager = types.SimpleNamespace(is_active=False)
        self.CHART_RANGE_30M = "30m"
        self.CHART_RANGE_2H = "2h"
        self.CHART_RANGE_SESSION = "session"


def _live(*, switch="on"):
    return {
        "switch": switch,
        "battery_voltage": 14.8,
        "current": 1.0,
        "power": 14.8,
        "temp_ext": 25.0,
        "temp_int": 35.0,
        "set_voltage": 16.5,
        "set_current": 1.0,
        "is_cv": "on",
        "is_cc": "off",
        "ovp_triggered": "off",
        "ocp_triggered": "off",
    }


def _callbacks(app, state):
    return {
        button.callback_data
        for row in build_operator_keyboard(app, state).inline_keyboard
        for button in row
        if button.callback_data
    }


def _observer(state="active"):
    return types.SimpleNamespace(
        state=state,
        battery_id="Baic72",
        chemistry="Ca/Ca",
        capacity_ah=72,
        fingerprint=None,
        finish_hold_started_at_s=None,
        last_status="",
    )


class OperatorAuthorityConflictTests(unittest.TestCase):
    def test_auto_and_manual_claims_are_containment_not_display_precedence(self):
        app = FakeApp()
        app.charge_controller.is_active = True
        app.manual_session_manager.is_active = True

        state = build_truthful_hmi_state(app, _live())
        callbacks = _callbacks(app, state)

        self.assertEqual(state.process_state, HmiProcessState.CONTAINMENT)
        self.assertEqual(state.authority, HmiAuthority.CONTAINMENT)
        self.assertEqual(state.attention, "alarm")
        self.assertIn("КОНФЛИКТ OWNERSHIP", state.title)
        self.assertIn("AUTO и MANUAL", state.progress)
        self.assertNotIn("power_toggle", callbacks)
        self.assertNotIn("charge_modes", callbacks)
        self.assertNotIn("v2_manual_choose", callbacks)

    def test_live_observer_without_hands_off_is_containment(self):
        app = FakeApp()
        app.rd_live_mix_observer = _observer("active")

        state = build_truthful_hmi_state(app, _live())

        self.assertEqual(state.process_state, HmiProcessState.CONTAINMENT)
        self.assertEqual(state.authority, HmiAuthority.CONTAINMENT)
        self.assertIn("вне HANDS_OFF", state.progress)

    def test_live_observer_with_hands_off_is_valid_adopted_mix_pair(self):
        app = FakeApp()
        app.rd_control_mode_manager.hands_off = True
        app.rd_live_mix_observer = _observer("active")

        state = build_truthful_hmi_state(app, _live())
        callbacks = _callbacks(app, state)

        self.assertEqual(state.process_state, HmiProcessState.ADOPTED_MIX)
        self.assertEqual(state.authority, HmiAuthority.ADOPTED_MIX)
        self.assertIn("operator_adopted_stop", callbacks)

    def test_managed_auto_cannot_coexist_with_hands_off(self):
        app = FakeApp()
        app.rd_control_mode_manager.hands_off = True
        app.charge_controller.is_active = True

        state = build_truthful_hmi_state(app, _live())

        self.assertEqual(state.process_state, HmiProcessState.CONTAINMENT)
        self.assertEqual(state.authority, HmiAuthority.CONTAINMENT)
        self.assertIn("AUTO активен при HANDS_OFF", state.progress)

    def test_managed_owner_cannot_hide_live_observer(self):
        app = FakeApp()
        app.rd_control_mode_manager.hands_off = True
        app.rd_live_mix_observer = _observer("active")
        app.manual_session_manager.is_active = True

        state = build_truthful_hmi_state(app, _live())

        self.assertEqual(state.process_state, HmiProcessState.CONTAINMENT)
        self.assertEqual(state.authority, HmiAuthority.CONTAINMENT)
        self.assertIn("MANUAL конфликтует с подхваченным Mix", state.progress)


if __name__ == "__main__":
    unittest.main()
