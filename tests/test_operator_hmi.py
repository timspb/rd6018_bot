import types
import unittest
from html.parser import HTMLParser

from operator_hmi import (
    HmiProcessState,
    build_operator_hmi_state,
    build_operator_keyboard,
    _more_keyboard,
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
    def test_panel_uses_single_telegram_html_layer_for_charge_status(self):
        state = types.SimpleNamespace(
            title="Восстановление",
            process_state=HmiProcessState.RUNNING,
            authority=types.SimpleNamespace(value="auto"),
            output_on=True,
            regulator="CV",
            battery_label="Ca/Ca · 72 Ah",
            battery_voltage_v=13.86,
            current_a=0.0,
            battery_temp_c=24.0,
            target_voltage_v=14.72,
            current_limit_a=7.20,
            progress="Режим регулятора определяется",
            safety="Защита: норма",
            attention="normal",
        )
        text = render_operator_panel(state)

        self.assertIn("<b>Восстановление · CV</b>", text)
        self.assertIn("<b>13.86 V</b>", text)
        self.assertIn("<b>0.00 A</b>", text)
        self.assertIn("<b>24.0 °C</b>", text)
        self.assertIn("🎯 14.72 V · лимит 7.20 A", text)
        self.assertNotIn("<b>14.72 V</b>", text)
        self.assertNotIn("<b>7.20 A</b>", text)
        self.assertNotIn("Режим регулятора определяется", text)
        self.assertNotIn("&lt;b&gt;", text)

        class _Tags(HTMLParser):
            pass

        parser = _Tags()
        parser.feed(text)
        parser.close()

    def test_preformatted_transition_is_not_double_escaped(self):
        state = types.SimpleNamespace(
            title="Восстановление",
            process_state=HmiProcessState.RUNNING,
            authority=types.SimpleNamespace(value="auto"),
            output_on=True,
            regulator="CV",
            battery_label="",
            battery_voltage_v=13.86,
            current_a=0.0,
            battery_temp_c=24.0,
            target_voltage_v=14.72,
            current_limit_a=7.20,
            progress="<b>Восстановление</b> Температура: стабильно",
            safety="Защита: норма",
            attention="normal",
        )
        text = render_operator_panel(state)
        self.assertIn("➡️ <b>Восстановление</b>", text)
        self.assertNotIn("&lt;b&gt;Восстановление", text)

    def test_preformatted_ordinary_transition_is_not_double_escaped(self):
        state = types.SimpleNamespace(
            title="Обычный заряд",
            process_state=HmiProcessState.RUNNING,
            authority=types.SimpleNamespace(value="auto"),
            output_on=True,
            regulator="CV",
            battery_label="",
            battery_voltage_v=14.14,
            current_a=0.0,
            battery_temp_c=24.0,
            target_voltage_v=16.50,
            current_limit_a=2.16,
            progress="<b>Обычный заряд</b> Температура: стабильно",
            safety="Защита: норма",
            attention="normal",
        )
        text = render_operator_panel(state)
        self.assertIn("➡️ <b>Обычный заряд</b>", text)
        self.assertNotIn("&lt;b&gt;Обычный заряд", text)

    def test_active_external_mix_is_presented_as_adopted_not_hands_off(self):
        app = FakeApp(observer=FakeObserver())
        state = build_operator_hmi_state(app, live())
        text = render_operator_panel(state)

        self.assertEqual(state.process_state, HmiProcessState.ADOPTED_MIX)
        self.assertIn("MIX ПОДХВАЧЕН", text)
        self.assertIn("Baic72 · Ca/Ca · 72 Ah", text)
        self.assertIn("MIX ПОДХВАЧЕН · CV", text)
        self.assertIn("16.55 V", text)
        self.assertIn("0.90 A", text)
        self.assertIn("🎯 16.54 V · лимит 1.01 A", text)
        self.assertIn("FLOAT", text)
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
        self.assertIn("logs", callbacks)
        self.assertNotIn("ai_analysis", callbacks)
        self.assertIn("operator_graph", callbacks)
        self.assertIn("operator_refresh", callbacks)
        self.assertNotIn("v2_batteries", callbacks)
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
        self.assertEqual(texts[0], "⚡ Режимы заряда")
        self.assertIn("charge_modes", callbacks)
        self.assertNotIn("v2_manual_choose", callbacks)
        self.assertIn("logs", callbacks)
        self.assertNotIn("ai_analysis", callbacks)
        self.assertNotIn("operator_graph", callbacks)
        self.assertIn("operator_refresh", callbacks)
        self.assertIn("v2_batteries", callbacks)
        self.assertIn("operator_more", callbacks)
        self.assertNotIn("v2_status", callbacks)
        self.assertNotIn("entities_status", callbacks)
        self.assertNotIn("chart_30m", callbacks)

    def test_more_menu_contains_service_actions_and_manual(self):
        app = FakeApp(observer=None, hands_off=False)
        state = build_operator_hmi_state(app, live(output="off"))
        callbacks = [
            button.callback_data
            for row in _more_keyboard(state).inline_keyboard
            for button in row
        ]
        self.assertIn("ai_analysis", callbacks)
        self.assertIn("v2_status", callbacks)
        self.assertIn("entities_status", callbacks)
        self.assertIn("operator_service_details", callbacks)
        self.assertIn("v2_manual_choose", callbacks)

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

    def test_details_contains_old_bot_stage_statistics_for_active_charge(self):
        controller = types.SimpleNamespace(
            is_active=True,
            current_stage="Mix Mode",
            battery_type="Ca/Ca",
            ah_capacity=72,
            get_timers=lambda: {
                "stage_time": "04:43",
                "total_time": "10:29",
                "remaining_time": "196 мин",
            },
        )
        app = FakeApp(observer=None, hands_off=False, controller_active=True)
        app.charge_controller = controller
        state = build_operator_hmi_state(app, live())
        text = render_operator_details(app, state, {**live(), "ah": 7.26, "uptime": "10:29"})
        self.assertIn("Статистика по этапу", text)
        self.assertIn("Этап: <b>Mix Mode</b>", text)
        self.assertIn("Этап: 04:43", text)
        self.assertIn("Набрано: 7.26 Ah", text)
        self.assertIn("Уставки: 16.54 V · лимит 1.01 A", text)
        self.assertIn("Коды:", text)

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

    def test_compact_panel_omits_power_and_psu_temperature(self):
        state = build_operator_hmi_state(FakeApp(observer=None), live())
        text = render_operator_panel(state)

        self.assertNotIn("W", text)
        self.assertNotIn("БП", text)

    def test_cc_panel_exposes_regulator_and_transition(self):
        values = live()
        values["is_cv"] = "off"
        values["is_cc"] = "on"
        values["power"] = 99.0
        state = build_operator_hmi_state(FakeApp(observer=None), values)
        text = render_operator_panel(state)

        self.assertIn("CC", text)

    def test_cv_panel_exposes_compact_minimum_hold_status(self):
        values = live()
        values["is_cv"] = "on"
        state = types.SimpleNamespace(
            title="Обычный заряд",
            process_state=HmiProcessState.RUNNING,
            authority=types.SimpleNamespace(value="auto"),
            output_on=True,
            regulator="CV",
            battery_label="Ca/Ca · 72 Ah",
            battery_voltage_v=14.71,
            current_a=0.22,
            battery_temp_c=27.0,
            target_voltage_v=16.46,
            current_limit_a=2.16,
            progress="CV · Imin 0.220 A · ΔI 0.010 A / 0.030 A · после Imin 2ч 02м",
            safety="Защита: норма",
            attention="normal",
        )
        text = render_operator_panel(state)
        self.assertIn("✅ Imin 0.220 A · ⏱ 2ч 02м", text)
        self.assertLess(text.index("Imin"), text.index("Защита"))

    def test_cv_panel_shows_unreached_minimum_compactly(self):
        state = types.SimpleNamespace(
            title="Обычный заряд", process_state=HmiProcessState.RUNNING,
            authority=types.SimpleNamespace(value="auto"), output_on=True,
            regulator="CV", battery_label="", battery_voltage_v=14.7,
            current_a=0.7, battery_temp_c=27.0, target_voltage_v=16.46,
            current_limit_a=2.16, progress="CV · Imin: ищем",
            safety="Защита: норма", attention="normal",
        )
        self.assertIn("⏳ Imin не достигнут", render_operator_panel(state))

    def test_cv_panel_never_shows_cc_vmax_status(self):
        state = types.SimpleNamespace(
            title="MIX", process_state=HmiProcessState.RUNNING,
            authority=types.SimpleNamespace(value="auto"), output_on=True,
            regulator="CV", battery_label="Ca/Ca · 72 Ah", battery_voltage_v=16.4,
            current_a=0.7, battery_temp_c=27.0, target_voltage_v=16.5,
            current_limit_a=2.16, progress="CV · Imin: ищем",
            stage_status="⏳ Vmax не достигнут",
            safety="Защита: норма", attention="normal",
        )
        text = render_operator_panel(state)
        self.assertIn("⏳ Imin не достигнут", text)
        self.assertNotIn("Vmax", text)

    def test_active_controller_snapshot_drives_stage_status(self):
        controller = types.SimpleNamespace(
            is_active=True,
            current_stage="Mix Mode",
            battery_type="Ca/Ca",
            ah_capacity=72,
            v2_ui_snapshot=lambda: {
                "metrics": {"current_min_a": 0.22, "seconds_since_current_min": 7320},
                "finish_hold_started_at": None,
            },
        )
        app = FakeApp(observer=None, hands_off=False, controller_active=True)
        app.charge_controller = controller
        app._format_stage_progress_line = lambda live: "<b>Обычный заряд</b>"
        state = build_operator_hmi_state(app, live())
        text = render_operator_panel(state)
        self.assertIn("✅ Imin 0.22 A · ⏱ 2ч 02м", text)
        self.assertLess(text.index("Imin"), text.index("Защита"))

    def test_empty_runtime_after_restore_does_not_claim_imin_missing(self):
        controller = types.SimpleNamespace(
            is_active=True,
            current_stage="Mix Mode",
            battery_type="Ca/Ca",
            ah_capacity=72,
            v2_ui_snapshot=lambda: {
                "is_cv": False, "is_cc": False,
                "runtime_analysis_available": False,
                "finish_hold_started_at": None, "metrics": {},
            },
        )
        app = FakeApp(observer=None, hands_off=False, controller_active=True)
        app.charge_controller = controller
        state = build_operator_hmi_state(app, live())
        text = render_operator_panel(state)
        self.assertIn("Анализ после восстановления недоступен", text)
        self.assertNotIn("Imin не достигнут", text)

    def test_main_actions_are_grouped_and_service_menu_hides_diagnostics(self):
        app = FakeApp(observer=None, hands_off=False, controller_active=True)
        state = build_operator_hmi_state(app, live())
        keyboard = build_operator_keyboard(app, state)
        rows = keyboard.inline_keyboard
        self.assertEqual(len(rows[0]), 2)  # pause + stop
        self.assertEqual(len(rows[1]), 3)  # details, graph, events
        self.assertIn("logs", {button.callback_data for button in rows[1]})
        self.assertIn("operator_graph", {button.callback_data for button in rows[1]})
        self.assertIn("operator_more", {button.callback_data for row in rows for button in row})
        self.assertNotIn("ai_analysis", {button.callback_data for row in rows for button in row})
        self.assertEqual(len(rows[-1]), 1)  # refresh

    def test_paused_charge_has_resume_and_terminal_stop_side_by_side(self):
        app = FakeApp(observer=None, hands_off=False, controller_active=True)
        app._operator_pause_active = lambda: True
        state = build_operator_hmi_state(app, live())
        keyboard = build_operator_keyboard(app, state)
        first_row = keyboard.inline_keyboard[0]
        self.assertEqual([button.text for button in first_row], ["▶️ Продолжить", "🛑 Стоп"])
        self.assertEqual(first_row[0].callback_data, "operator_pause_toggle")
        self.assertEqual(first_row[1].text, "🛑 Стоп")
        self.assertIn(first_row[1].callback_data, {"power_toggle", "operator_managed_stop"})

    def test_fault_panel_keeps_protection_reason(self):
        values = live(output="off")
        values["ovp_triggered"] = "on"
        state = build_operator_hmi_state(FakeApp(observer=None, hands_off=False), values)
        text = render_operator_panel(state)

        self.assertIn("OVP", text)
        self.assertIn("Защита", text)


if __name__ == "__main__":
    unittest.main()
