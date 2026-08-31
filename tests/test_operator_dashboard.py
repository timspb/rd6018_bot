import types
import unittest

from operator_dashboard import build_truthful_hmi_state, render_truthful_panel
from operator_hmi import HmiProcessState, build_operator_keyboard


class FakeApp:
    def __init__(self):
        self.rd_control_mode_manager = types.SimpleNamespace(hands_off=False)
        self.rd_live_mix_observer = None
        self.charge_controller = types.SimpleNamespace(
            is_active=False,
            current_stage="Idle",
            battery_type="",
            ah_capacity=0,
        )
        self.manual_session_manager = types.SimpleNamespace(is_active=False)
        self.CHART_RANGE_30M = "30m"
        self.CHART_RANGE_2H = "2h"
        self.CHART_RANGE_SESSION = "session"


def _live(**overrides):
    data = {
        "switch": "off",
        "battery_voltage": 13.10,
        "current": 0.0,
        "power": 0.0,
        "temp_ext": 25.0,
        "temp_int": 35.0,
        "set_voltage": 14.8,
        "set_current": 5.0,
        "is_cv": "off",
        "is_cc": "off",
        "ovp_triggered": "off",
        "ocp_triggered": "off",
    }
    data.update(overrides)
    return data


class OperatorDashboardTruthTests(unittest.TestCase):
    def test_unknown_output_is_containment_not_idle_or_off(self):
        app = FakeApp()
        state = build_truthful_hmi_state(app, _live(switch="unavailable"))
        text = render_truthful_panel(state)
        callbacks = {
            button.callback_data
            for row in build_operator_keyboard(app, state).inline_keyboard
            for button in row
            if button.callback_data
        }

        self.assertEqual(state.process_state, HmiProcessState.CONTAINMENT)
        self.assertEqual(state.attention, "output_unknown")
        self.assertIn("OUTPUT НЕ ПОДТВЕРЖДЁН", text)
        self.assertIn("Output <b>UNKNOWN</b>", text)
        self.assertNotIn("Output <b>OFF</b>", text)
        self.assertNotIn("charge_modes", callbacks)
        self.assertNotIn("v2_manual_choose", callbacks)

    def test_missing_protection_status_is_not_reported_normal(self):
        app = FakeApp()
        live = _live()
        live.pop("ocp_triggered")
        state = build_truthful_hmi_state(app, live)
        text = render_truthful_panel(state)

        self.assertEqual(state.process_state, HmiProcessState.IDLE)
        self.assertEqual(state.attention, "warning")
        self.assertIn("Статус защит RD6018 не подтверждён", text)
        self.assertNotIn("Защита: норма", text)

    def test_confirmed_off_and_protections_remain_normal_idle(self):
        app = FakeApp()
        state = build_truthful_hmi_state(app, _live())
        text = render_truthful_panel(state)

        self.assertEqual(state.process_state, HmiProcessState.IDLE)
        self.assertIn("Output <b>OFF</b>", text)
        self.assertIn("Защита: норма", text)

    def test_unknown_protection_while_output_on_is_alarm(self):
        app = FakeApp()
        state = build_truthful_hmi_state(
            app,
            _live(switch="on", ovp_triggered="unknown"),
        )

        self.assertEqual(state.process_state, HmiProcessState.CONTAINMENT)
        self.assertEqual(state.attention, "alarm")
        self.assertIn("Статус защит RD6018 не подтверждён", state.safety)


if __name__ == "__main__":
    unittest.main()
