import types
import unittest

from operator_hmi import (
    HmiProcessState,
    build_operator_hmi_state,
    build_operator_keyboard,
    render_operator_details,
    render_operator_panel,
)


class FakeObserver:
    def __init__(self, state="active"):
        self.state = types.SimpleNamespace(value=state)
        self.battery_id = "Baic72"
        self.chemistry = types.SimpleNamespace(value="Ca/Ca")
        self.capacity_ah = 72.0
        self.fingerprint = types.SimpleNamespace(
            set_voltage_v=16.54,
            set_current_a=1.01,
            ovp_v=16.7,
            ocp_a=0.0,
        )
        self.finish_hold_started_at_s = None
        self.last_status = "fresh post-activation Delta epoch started"


class FakeApp:
    def __init__(self, *, hands_off=True, observer=None, controller_active=False):
        self.rd_control_mode_manager = types.SimpleNamespace(hands_off=hands_off)
        self.rd_live_mix_observer = observer
        self.charge_controller = types.SimpleNamespace(
            is_active=controller_active,
            current_stage="Mix Mode",
            battery_type="Ca/Ca",
            ah_capacity=72,
        )
        self.manual_session_manager = types.SimpleNamespace(is_active=False)
        self.CHART_RANGE_30M = "30m"
        self.CHART_RANGE_2H = "2h"
        self.CHART_RANGE_SESSION = "session"
        self._stage_label = lambda stage, short=True: "Mix"
        self._format_stage_progress_line = lambda live: ""


def live(*, output="on"):
    return {
        "switch": output,
        "battery_voltage": 16.55,
        "current": 0.90,
        "power": 15.0,
        "temp_ext": 27.0,
        "temp_int": 40.0,
        "set_voltage": 16.54,
        "set_current": 1.01,
        "ovp": 16.7,
        "ocp": 0.0,
        "is_cv": "on",
        "is_cc": "off",
        "ovp_triggered": "off",
        "ocp_triggered": "off",
    }


class OperatorHmiTests(unittest.TestCase):
    def test_active_external_mix_is_presented_as_adopted_not_hands_off(self):
        app = FakeApp(observer=FakeObserver())
        state = build_operator_hmi_state(app, live())
        text = render_operator_panel(state)

        self.assertEqual(state.process_state, HmiProcessState.ADOPTED_MIX)
        self.assertIn("MIX ПОДХВАЧЕН", text)
        self.assertIn("Baic72 · Ca/Ca · 72 Ah", text)
        self.assertIn("Output <b>ON</b> · CV", text)
        self.assertIn("16.55 V", text)
        self.assertIn("0.90 A", text)
        self.assertIn("Цель 16.54 V · лимит 1.01 A", text)
        self.assertIn("свежий Imin", text)
        self.assertNotIn("РЕЖИМ РД", text)
        self.assertNotIn("НЕ ЛЕЗЬ", text)
        self.assertNotIn("OCP 0.00", text)

    def test_adopted_mix_top_level_controls_are_small_and_do_not_expose_pb_restore(self):
        app = FakeApp(observer=FakeObserver())
        state = build_operator_hmi_state(app, live())
        keyboard = build_operator_keyboard(app, state)
        callbacks = [
            button.callback_data
            for row in keyboard.inline_keyboard
            for button in row
            if button.callback_data
        ]
        texts = [button.text for row in keyboard.inline_keyboard for button in row]

        self.assertEqual(texts[0], "⏹ Остановить Mix")
        self.assertIn("operator_adopted_stop", callbacks)
        self.assertIn("operator_details", callbacks)
        self.assertIn("operator_graph", callbacks)
        self.assertIn("v2_batteries", callbacks)
        self.assertIn("operator_more", callbacks)
        self.assertNotIn("rd_hands_off_disable", callbacks)
        self.assertNotIn("chart_30m", callbacks)
        self.assertNotIn("chart_2h", callbacks)
        self.assertNotIn("chart_session", callbacks)
        self.assertNotIn("v2_status", callbacks)
        self.assertNotIn("entities_status", callbacks)

    def test_unadopted_external_output_has_clear_pickup_action(self):
        app = FakeApp(observer=None, hands_off=True)
        state = build_operator_hmi_state(app, live())
        text = render_operator_panel(state)
        keyboard = build_operator_keyboard(app, state)
        callbacks = [button.callback_data for row in keyboard.inline_keyboard for button in row]

        self.assertEqual(state.process_state, HmiProcessState.HANDS_OFF)
        self.assertIn("РУЧНОЕ УПРАВЛЕНИЕ", text)
        self.assertIn("Внешняя сессия", text)
        self.assertIn("rd_live_mix", callbacks)
        self.assertIn("rd_hands_off_output_off", callbacks)
        self.assertNotIn("rd_hands_off_disable", callbacks)

    def test_idle_panel_matches_operator_hierarchy(self):
        app = FakeApp(observer=None, hands_off=False)
        state = build_operator_hmi_state(app, live(output="off"))
        keyboard = build_operator_keyboard(app, state)
        callbacks = [button.callback_data for row in keyboard.inline_keyboard for button in row]
        texts = [button.text for row in keyboard.inline_keyboard for button in row]

        self.assertEqual(state.process_state, HmiProcessState.IDLE)
        self.assertEqual(texts[0], "▶ Новая программа")
        self.assertIn("charge_modes", callbacks)
        self.assertIn("v2_manual_choose", callbacks)
        self.assertIn("operator_graph", callbacks)
        self.assertIn("v2_batteries", callbacks)
        self.assertIn("operator_more", callbacks)
        self.assertNotIn("v2_status", callbacks)
        self.assertNotIn("entities_status", callbacks)
        self.assertNotIn("chart_30m", callbacks)

    def test_adopted_details_are_truthful_about_low_level_authority(self):
        app = FakeApp(observer=FakeObserver())
        live_data = live()
        state = build_operator_hmi_state(app, live_data)
        text = render_operator_details(app, state, live_data)

        self.assertIn("Mix подхвачен", text)
        self.assertIn("не переписывал текущие V/I/OVP/OCP", text)
        self.assertIn("остаётся HANDS_OFF", text)
        self.assertIn("не имеет валидированного live-adopt handshake", text)
        self.assertNotIn("PB_MANAGED владеет", text)

    def test_interrupted_adoption_is_not_misrepresented_as_active(self):
        app = FakeApp(observer=FakeObserver("interrupted"))
        state = build_operator_hmi_state(app, live())
        text = render_operator_panel(state)
        keyboard = build_operator_keyboard(app, state)
        callbacks = [button.callback_data for row in keyboard.inline_keyboard for button in row]

        self.assertEqual(state.process_state, HmiProcessState.INTERRUPTED)
        self.assertIn("ТРЕБУЕТ ПОДТВЕРЖДЕНИЯ", text)
        self.assertIn("Подхват прерван", text)
        self.assertIn("rd_live_mix", callbacks)
        self.assertNotIn("operator_adopted_stop", callbacks)


if __name__ == "__main__":
    unittest.main()
