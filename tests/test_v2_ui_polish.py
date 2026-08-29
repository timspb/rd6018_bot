import types
import unittest

from v2_ui_polish import format_active_evidence_pretty, install_dashboard_polish


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
        self.assertIn("Imin: <b>ищем…</b>", text)
        self.assertIn("Хвост ещё не сформирован", text)
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
        self.assertIn("Imin <b>0.410 A</b>", text)
        self.assertIn("ΔI <b>+0.070</b> / 0.123 A · 1ч 00м", text)
        self.assertIn("Температура стабильна", text)
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
        self.assertIn("Vmax <b>16.470 V</b>", text)
        self.assertIn("ΔV <b>+0.050</b> / 0.030 V · 15м", text)
        self.assertIn("выдержка 2ч", text)
        self.assertNotIn("Imin", text)

    def test_main_dashboard_drops_legacy_mode_and_hard_limit_line(self):
        controller = types.SimpleNamespace(
            is_active=True,
            current_stage="Main Charge",
            STAGE_MAIN="Main Charge",
            STAGE_MIX="Mix Mode",
        )
        app = types.SimpleNamespace(
            charge_controller=controller,
            _compact_dashboard_caption=lambda live, chart_mode, mode, idle_warning: (
                "<b>📊 RD6018 · Ca/Ca | 72Ah</b>\n"
                "<b>Стадия: Основной</b>\n"
                "V: <b>14.67V</b>   I: <b>0.80A</b>\n"
                "Ah: <b>16.40</b>   АКБ: <b>26.0°C</b>\n"
                "Режим: CV  Лимит этапа: 71ч 59м\n"
                "V2 evidence\n"
                "✅ Норма · 📈 30м"
            ),
        )
        ui_module = types.SimpleNamespace(format_active_evidence=None)
        install_dashboard_polish(app, ui_module)
        text = app._compact_dashboard_caption({}, "30m", "CV", "")
        self.assertNotIn("Лимит этапа", text)
        self.assertNotIn("Режим: CV", text)
        self.assertIn("Стадия: Основной", text)
        self.assertIn("V2 evidence", text)
        self.assertIs(ui_module.format_active_evidence, format_active_evidence_pretty)


if __name__ == "__main__":
    unittest.main()
