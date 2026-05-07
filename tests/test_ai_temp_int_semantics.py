import unittest

from ai_engine import format_ai_snapshot


class AiTempSemanticsTests(unittest.TestCase):
    def test_temp_int_is_marked_as_controller_bp_monitoring(self):
        snapshot = {
            "stage": "Main Charge",
            "profile": "AGM",
            "is_active": True,
            "summary": "Main 14.4V",
            "transition": "Hold running",
            "next_stage": "Mix",
            "previous_stage": "Prep",
            "stage_path": ["Prep", "Main Charge"],
            "last_transition_reason": "startup",
            "targets": {"voltage": 14.4, "current": 7.0},
            "timers": {"total_time": "01:00", "stage_time": "00:30", "remaining_time": "00:30"},
            "hold": None,
            "safety": {
                "current_limit_a": 12,
                "ovp_offset_v": 0.1,
                "ocp_offset_a": 0.1,
                "temp_warning_c": 35,
                "temp_pause_c": 40,
                "temp_critical_c": 45,
                "safe_wait_margin_v": 0.5,
                "safe_wait_max_sec": 7200,
            },
            "temperature_compensation": None,
            "post_charge_relaxation": None,
            "temp_int_now": 41.0,
            "temp_ext_now": 24.0,
        }

        text = format_ai_snapshot(snapshot)
        self.assertIn("Температуры: АКБ=temp_ext | БП=temp_int", text)
        self.assertIn("T_ext=35/40/45C", text)
        self.assertIn("Temp note:", text)

    def test_bank_fault_watch_stays_observation_only(self):
        snapshot = {
            "stage": "Prep",
            "profile": "AGM",
            "is_active": True,
            "summary": "Prep running",
            "transition": "Prep -> Main",
            "next_stage": "Main Charge",
            "previous_stage": "Idle",
            "stage_path": ["Prep"],
            "last_transition_reason": "start",
            "targets": {"voltage": 12.0, "current": 0.7},
            "timers": {"total_time": "01:00", "stage_time": "00:30", "remaining_time": "00:30"},
            "hold": None,
            "safety": {
                "current_limit_a": 12,
                "ovp_offset_v": 0.1,
                "ocp_offset_a": 0.1,
                "temp_warning_c": 35,
                "temp_pause_c": 40,
                "temp_critical_c": 45,
                "safe_wait_margin_v": 0.5,
                "safe_wait_max_sec": 7200,
            },
            "temperature_compensation": None,
            "post_charge_relaxation": None,
            "bank_fault_risk": {
                "status": "watch",
                "score": 45,
                "stage": "Prep",
                "elapsed_text": "02:00:00",
                "start_voltage": 10.7,
                "current_voltage": 11.2,
                "start_temp_c": 24.0,
                "current_temp_c": 25.1,
                "reasons": ["prep_start_low=10.70V", "prep_slow_to_12V=2.00h"],
            },
        }

        text = format_ai_snapshot(snapshot)
        self.assertIn("Риск по банке: наблюдение", text)
        self.assertIn("score=45", text)
        self.assertIn("низкий старт в Подготовке", text)
        self.assertNotIn("Вероятен КЗ банки", text)


if __name__ == "__main__":
    unittest.main()
