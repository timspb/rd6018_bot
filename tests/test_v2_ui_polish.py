import types
import unittest

from v2_ui_polish import (
    build_operator_dashboard_keyboard,
    format_active_evidence_pretty,
    install_dashboard_polish,
)


class V2UiPolishTests(unittest.TestCase):
    def test_zero_startup_minimum_is_not_shown_as_real_imin(self):
        text = format_active_evidence_pretty(
            {
                "authoritative": True,
                "intent": "recovery",
                "is_cv": True,
                "is_cc": False,
                "decision": "continue",
                "metrics": {
                    "current_min_a": 0.0,
                    "delta_current_from_min_a": 0.0,
                    "reversal_threshold_a": 0.03,
                    "seconds_since_current_min": 0,
                    "d_current_a_per_min": None,
                    "d_temp_c_per_min": None,
                },
            }
        )
        self.assertIn("Imin: ищем", text)
        self.assertIn("Хвост тока ещё не сформирован", text)
        self.assertNotIn("0.000", text)
        self.assertNotIn("decision", text)
        self.assertNotIn("Факт:", text)

    def test_cv_card_is_compact_and_current_specific(self):
        text = format_active_evidence_pretty(
            {
                "authoritative": True,
                "intent": "recovery",
                "is_cv": True,
                "is_cc": False,
                "decision": "continue",
                "metrics": {
                    "current_min_a": 0.41,
                    "delta_current_from_min_a": 0.07,
                    "reversal_threshold_a": 0.123,
                    "seconds_since_current_min": 3600,
                    "d_temp_c_per_min": 0.01,
                    "voltage_max_v": 16.5,
                },
            }
        )
        self.assertIn("CV", text)
        self.assertIn("Imin 0.410 A", text)
        self.assertIn("ΔI +0.070 / 0.123 A · 1ч 00м", text)
        self.assertIn("Температура: стабильно", text)
        self.assertNotIn("Vmax", text)
        self.assertNotIn("decision", text)

    def test_cc_card_is_voltage_specific(self):
        text = format_active_evidence_pretty(
            {
                "authoritative": True,
                "intent": "recovery",
                "is_cv": False,
                "is_cc": True,
                "decision": "finish_stage",
                "finish_hold_started_at": 1.0,
                "metrics": {
                    "voltage_max_v": 16.47,
                    "delta_voltage_from_max_v": 0.05,
                    "voltage_reversal_threshold_v": 0.03,
                    "seconds_since_voltage_max": 900,
                    "current_min_a": 0.1,
                    "d_temp_c_per_min": 0.02,
                },
            }
        )
        self.assertIn("CC", text)
        self.assertIn("Vmax 16.470 V", text)
        self.assertIn("ΔV +0.050 / 0.030 V · 15м", text)
        self.assertIn("финальная выдержка 2 ч", text)
        self.assertNotIn("Imin", text)

    def test_main_dashboard_is_operator_card_not_developer_dump(self):
        snapshot = {
            "authoritative": True,
            "intent": "recovery",
            "is_cv": True,
            "is_cc": False,
            "decision": "continue",
            "metrics": {
                "current_min_a": 0.41,
                "delta_current_from_min_a": 0.02,
                "reversal_threshold_a": 0.123,
                "seconds_since_current_min": 1200,
                "d_temp_c_per_min": 0.01,
            },
        }
        controller = types.SimpleNamespace(
            is_active=True,
            current_stage="Main Charge",
            STAGE_MAIN="Main Charge",
            STAGE_MIX="Mix Mode",
            battery_type="Ca/Ca",
            ah_capacity=72,
            v2_ui_snapshot=lambda: snapshot,
            get_timers=lambda: {"total_time": "03:12", "stage_time": "03:12", "remaining_time": "68:48"},
        )
        app = types.SimpleNamespace(
            charge_controller=controller,
            _stage_label=lambda stage, short=True: "Основной" if short else "Основной заряд",
            _chart_label=lambda mode: "30м",
            _format_manual_off_for_dashboard=lambda: "",
            _format_stage_progress_line=lambda live: "",
        )
        ui_module = types.SimpleNamespace(format_active_evidence=None)
        install_dashboard_polish(app, ui_module)

        text = app._compact_dashboard_caption(
            {
                "battery_voltage": 14.72,
                "current": 0.84,
                "power": 12.4,
                "ah": 16.4,
                "temp_ext": 24.8,
                "temp_int": 33.0,
                "set_voltage": 14.72,
                "set_current": 7.2,
                "switch": "on",
                "ovp_triggered": "off",
                "ocp_triggered": "off",
            },
            "30m",
            "CV",
            "",
        )
        self.assertIn("RD6018 · Ca/Ca 72 Ah · Восстановление", text)
        self.assertIn("<b>Основной</b> · CV · 03:12 · Output ON", text)
        self.assertIn("14.72 V", text)
        self.assertIn("0.84 A", text)
        self.assertIn("Уставки 14.72 V / 7.20 A", text)
        self.assertIn("Защита: норма · График 30м", text)
        self.assertNotIn("Лимит этапа", text)
        self.assertNotIn("🧭", text)
        self.assertNotIn("decision", text)
        self.assertIs(ui_module.format_active_evidence, format_active_evidence_pretty)

    def test_operator_keyboard_has_one_primary_action_and_icons(self):
        controller = types.SimpleNamespace(is_active=False)
        app = types.SimpleNamespace(
            charge_controller=controller,
            CHART_RANGE_30M="30m",
            CHART_RANGE_2H="2h",
            CHART_RANGE_SESSION="session",
            _chart_range_for_user=lambda user_id: "30m",
        )
        idle = build_operator_dashboard_keyboard(app, False, 1)
        callbacks = [
            button.callback_data
            for row in idle.inline_keyboard
            for button in row
            if button.callback_data
        ]
        texts = [button.text for row in idle.inline_keyboard for button in row]
        self.assertEqual(idle.inline_keyboard[0][0].text, "▶️ Новая программа")
        self.assertIn("charge_modes", callbacks)
        self.assertNotIn("power_toggle", callbacks)
        self.assertIn("v2_batteries", callbacks)
        self.assertIn("entities_status", callbacks)
        self.assertIn("🔄 Обновить", texts)
        self.assertIn("ℹ️ Подробнее", texts)
        self.assertIn("🔋 АКБ", texts)
        self.assertIn("📋 События", texts)
        self.assertIn("🎛 Контроллер", texts)
        self.assertIn("🩺 Диагностика", texts)
        self.assertIn("⏱ Условие OFF", texts)
        self.assertTrue(any("📈 30м" in text for text in texts))

        controller.is_active = True
        active = build_operator_dashboard_keyboard(app, True, 1)
        self.assertEqual(active.inline_keyboard[0][0].text, "🛑 Остановить заряд")
        self.assertEqual(active.inline_keyboard[0][0].callback_data, "power_toggle")

    def test_secondary_screen_keyboard_is_only_back_to_panel(self):
        app = types.SimpleNamespace(charge_controller=types.SimpleNamespace(is_active=True))
        markup = build_operator_dashboard_keyboard(app, True, 1, back_to_dashboard=True)
        self.assertEqual(len(markup.inline_keyboard), 1)
        self.assertEqual(markup.inline_keyboard[0][0].callback_data, "dash_back")
        self.assertEqual(markup.inline_keyboard[0][0].text, "⬅️ К панели")


if __name__ == "__main__":
    unittest.main()
