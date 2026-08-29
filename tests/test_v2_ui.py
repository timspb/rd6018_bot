import unittest

from battery_registry import BatteryRecord
from pb_domain import (
    BatteryChemistry,
    BatteryCondition,
    BatteryIdentity,
    BatteryLifecycle,
    ChargeIntent,
)
from v2_ui import (
    battery_button_label,
    build_program_preview,
    format_active_evidence,
    format_battery_card,
)


class V2UiTests(unittest.TestCase):
    def test_normal_preview_explicitly_forbids_high_voltage_stage(self):
        preview = build_program_preview(
            profile="AGM",
            capacity_ah=70,
            intent=ChargeIntent.NORMAL,
            condition=BatteryCondition.HEALTHY,
        )
        self.assertIn("Высоковольтный этап: запрещён", preview.text)
        self.assertIn("Ограничение профиля: <b>15.00 V</b>", preview.text)
        self.assertNotIn("Mix: до <b>16.3 V</b>", preview.text)

    def test_recovery_preview_exposes_hv_and_mode_specific_finish(self):
        preview = build_program_preview(
            profile="EFB",
            capacity_ah=80,
            intent=ChargeIntent.RECOVERY,
            condition=BatteryCondition.SULFATED_SUSPECTED,
        )
        self.assertIn("Высоковольтный этап", preview.text)
        self.assertIn("16.5 V", preview.text)
        self.assertIn("20 ч", preview.text)
        self.assertIn("Imin → ΔI", preview.text)
        self.assertIn("Vmax → ΔV", preview.text)
        self.assertIn("финальная выдержка 2 ч", preview.text)

    def test_cv_detail_uses_current_evidence_only(self):
        text = format_active_evidence(
            {
                "authoritative": True,
                "intent": "recovery",
                "is_cv": True,
                "is_cc": False,
                "decision": "continue",
                "finish_hold_started_at": None,
                "metrics": {
                    "current_min_a": 0.41,
                    "delta_current_from_min_a": 0.07,
                    "reversal_threshold_a": 0.123,
                    "seconds_since_current_min": 3600,
                    "voltage_max_v": 16.5,
                    "delta_voltage_from_max_v": 0.05,
                    "d_temp_c_per_min": 0.01,
                },
            }
        )
        self.assertIn("CV · анализ по току", text)
        self.assertIn("Imin", text)
        self.assertNotIn("Vmax", text)

    def test_cc_detail_uses_voltage_evidence_only(self):
        text = format_active_evidence(
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
                    "delta_current_from_min_a": 0.2,
                    "d_temp_c_per_min": 0.02,
                },
            }
        )
        self.assertIn("CC · анализ по напряжению", text)
        self.assertIn("Vmax", text)
        self.assertNotIn("Imin", text)
        self.assertIn("финальная выдержка 2 ч", text)

    def test_battery_card_surfaces_longitudinal_state_without_dev_labels(self):
        lifecycle = BatteryLifecycle(
            condition=BatteryCondition.REHYDRATED,
            water_added_total_ml=240,
            cycles_since_refill=2,
            measured_capacity_ah=61,
            cca_a=610,
            internal_resistance_mohm=6.3,
        )
        record = BatteryRecord(
            identity=BatteryIdentity(
                "varta-70",
                BatteryChemistry.AGM,
                70,
                manufacturer="Varta",
                model="AGM 70",
            ),
            lifecycle=lifecycle,
        )
        card = format_battery_card(record)
        self.assertIn("rehydrated", card)
        self.assertIn("240 мл", card)
        self.assertIn("Ёмкость 61 Ah", card)
        self.assertIn("CCA 610 A", card)
        self.assertIn("Ri 6.3 mΩ", card)
        self.assertNotIn("Capacity", card)
        self.assertIn("Varta", battery_button_label(record))


if __name__ == "__main__":
    unittest.main()
