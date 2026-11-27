import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from runtime.operator.off_conditions import OperatorOffConditions


class OperatorOffConditionsTests(unittest.TestCase):
    def test_named_preset_operation_owns_values_clear_and_errors(self):
        state = OperatorOffConditions(voltage_ge=10.0, start_time=99.0)
        self.assertEqual(
            state.apply_preset("time_2h", now_s=100.0),
            "✅ Preset применён: выключение через 2 часа.",
        )
        self.assertEqual((state.time_sec, state.start_time), (7200.0, 100.0))
        self.assertEqual(
            state.apply_preset("i_le_030", now_s=101.0),
            "✅ Preset применён: выключение при I≤0.30 A.",
        )
        self.assertEqual(state.current_le, 0.30)
        self.assertEqual(
            state.apply_preset("v_ge_162", now_s=102.0),
            "✅ Preset применён: выключение при V≥16.2 V.",
        )
        self.assertEqual(state.voltage_ge, 16.2)
        self.assertEqual(state.apply_preset("clear", now_s=103.0), "✅ Условие выключения сброшено.")
        self.assertFalse(state.has_condition())
        for preset, error in (("unknown", "unknown_off_preset"), ("v_ge_162", "invalid_off_preset")):
            with self.subTest(preset=preset):
                state.voltage_ge = 10.0
                if error == "invalid_off_preset":
                    state.update_from_document = lambda _document: False
                with self.assertRaisesRegex(ValueError, error):
                    state.apply_preset(preset, now_s=104.0)
                self.assertFalse(state.has_condition())

    def test_evaluate_reason_is_read_only_and_preserves_priority_and_text(self):
        state = OperatorOffConditions(
            voltage_ge=16.2, voltage_le=16.2, current_le=0.3,
            current_ge=0.3, time_sec=10.0, start_time=100.0,
        )
        before = state.to_document()
        self.assertEqual(state.evaluate_reason(16.2, 0.3, now_s=110.0, reach_eps=0.02),
                         "напряжение достигло 16.20 В (сейчас 16.20 В)")
        self.assertEqual(state.to_document(), before)

    def test_evaluate_reason_empty_and_exact_or_close_reach_thresholds(self):
        self.assertIsNone(OperatorOffConditions().evaluate_reason(0.0, 0.0, now_s=0.0, reach_eps=0.02))
        voltage = OperatorOffConditions(voltage_ge=16.2, voltage_le=16.2)
        self.assertEqual(voltage.evaluate_reason(16.18, 9.0, now_s=0.0, reach_eps=0.02),
                         "напряжение достигло 16.20 В (сейчас 16.18 В)")
        self.assertIsNone(voltage.evaluate_reason(16.179, 9.0, now_s=0.0, reach_eps=0.02))
        current = OperatorOffConditions(current_le=0.3, current_ge=0.3)
        self.assertEqual(current.evaluate_reason(12.0, 0.319, now_s=0.0, reach_eps=0.02),
                         "ток достиг 0.30 А (сейчас 0.32 А)")
        self.assertIsNone(current.evaluate_reason(12.0, 0.321, now_s=0.0, reach_eps=0.02))

    def test_evaluate_reason_comparison_ties_and_voltage_current_timer_priority(self):
        self.assertEqual(OperatorOffConditions(voltage_ge=16.2).evaluate_reason(
            16.2, 0.0, now_s=0.0, reach_eps=0.02), "напряжение 16.20 В ≥ 16.2 В")
        self.assertEqual(OperatorOffConditions(voltage_le=12.0).evaluate_reason(
            12.0, 0.0, now_s=0.0, reach_eps=0.02), "напряжение 12.00 В ≤ 12.0 В")
        self.assertEqual(OperatorOffConditions(current_le=0.3, current_ge=0.3).evaluate_reason(
            12.0, 0.3, now_s=0.0, reach_eps=0.02), "ток достиг 0.30 А (сейчас 0.30 А)")
        self.assertEqual(OperatorOffConditions(current_le=0.3, current_ge=1.0).evaluate_reason(
            12.0, 0.3, now_s=0.0, reach_eps=0.02), "ток 0.30 А ≤ 0.30 А")
        self.assertEqual(OperatorOffConditions(current_ge=1.0).evaluate_reason(
            12.0, 1.0, now_s=0.0, reach_eps=0.02), "ток 1.00 А ≥ 1.00 А")
        timer = OperatorOffConditions(time_sec=10.0, start_time=100.0)
        self.assertIsNone(timer.evaluate_reason(12.0, 1.0, now_s=109.999, reach_eps=0.02))
        self.assertEqual(timer.evaluate_reason(12.0, 1.0, now_s=110.0, reach_eps=0.02), "таймер 0.0 ч")

    def test_six_key_legacy_document_roundtrip(self):
        state = OperatorOffConditions(16.2, 12.1, 0.3, 1.0, 7200.0, 1234.5)
        expected = {
            "voltage_ge": 16.2,
            "voltage_le": 12.1,
            "current_le": 0.3,
            "current_ge": 1.0,
            "time_sec": 7200.0,
            "start_time": 1234.5,
        }
        self.assertEqual(state.to_document(), expected)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manual_off_state.json"
            state.save(path)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), expected)
            self.assertEqual(set(json.loads(path.read_text(encoding="utf-8"))), set(expected))

    def test_empty_state_removes_file_and_has_legacy_defaults(self):
        state = OperatorOffConditions()
        self.assertEqual(state.to_document(), {
            "voltage_ge": None, "voltage_le": None, "current_le": None,
            "current_ge": None, "time_sec": None, "start_time": 0.0,
        })
        self.assertFalse(state.has_condition())
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manual_off_state.json"
            path.write_text("old", encoding="utf-8")
            state.save(path)
            self.assertFalse(path.exists())

    def test_active_load_roundtrip(self):
        document = {"voltage_ge": 16.2, "voltage_le": None, "current_le": None,
                    "current_ge": None, "time_sec": 7200, "start_time": 100.5}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            state = OperatorOffConditions()
            self.assertTrue(state.load(path))
            self.assertEqual(state.to_document(), {
                "voltage_ge": 16.2, "voltage_le": None, "current_le": None,
                "current_ge": None, "time_sec": 7200.0, "start_time": 100.5,
            })

    def test_valid_empty_mapping_returns_false(self):
        state = OperatorOffConditions(voltage_ge=1.0, start_time=2.0)
        self.assertFalse(state.update_from_document({}))
        self.assertFalse(state.has_condition())
        self.assertEqual(state.start_time, 0.0)

    def test_invalid_non_mappings_clear_state(self):
        for document in ([], "bad", None, 3):
            with self.subTest(document=document):
                state = OperatorOffConditions(voltage_ge=1.0, start_time=2.0)
                self.assertFalse(state.update_from_document(document))
                self.assertFalse(state.has_condition())
                self.assertEqual(state.start_time, 0.0)

    def test_malformed_numeric_discards_whole_document(self):
        state = OperatorOffConditions(voltage_le=9.0, start_time=7.0)
        self.assertFalse(state.update_from_document({"voltage_ge": 16.0, "current_le": "bad"}))
        self.assertEqual(state.to_document(), {
            "voltage_ge": None, "voltage_le": None, "current_le": None,
            "current_ge": None, "time_sec": None, "start_time": 0.0,
        })
        for value in (float("nan"), float("inf"), -1):
            with self.subTest(value=value):
                self.assertFalse(state.update_from_document({"time_sec": value}))

    def test_corrupted_json_unarms_state(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            path.write_text("{broken", encoding="utf-8")
            state = OperatorOffConditions(voltage_ge=12.0)
            self.assertFalse(state.load(path))
            self.assertFalse(state.has_condition())

    def test_missing_file_unarms_state(self):
        with tempfile.TemporaryDirectory() as directory:
            state = OperatorOffConditions(voltage_ge=12.0)
            self.assertFalse(state.load(Path(directory) / "missing.json"))
            self.assertFalse(state.has_condition())

    def test_atomic_replace_preserves_only_complete_document_and_leaves_no_temp(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            path.write_text("previous", encoding="utf-8")
            state = OperatorOffConditions(voltage_ge=16.2)
            state.save(path)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["voltage_ge"], 16.2)
            self.assertEqual(list(Path(directory).glob("*.tmp")), [])
            self.assertEqual(list(Path(directory).glob(".*.tmp")), [])

    def test_failed_replace_keeps_previous_file_and_cleans_temporary_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            path.write_text("previous", encoding="utf-8")
            state = OperatorOffConditions(voltage_ge=16.2)
            with patch("runtime.operator.off_conditions.os.replace", side_effect=OSError("replace failed")):
                state.save(path)
            self.assertEqual(path.read_text(encoding="utf-8"), "previous")
            self.assertEqual(list(Path(directory).glob(".*.tmp")), [])

    def test_clear_removes_file_and_tolerates_missing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            path.write_text("state", encoding="utf-8")
            state = OperatorOffConditions(voltage_ge=10.0)
            state.clear(path)
            self.assertFalse(path.exists())
            state.clear(path)
            self.assertFalse(state.has_condition())


if __name__ == "__main__":
    unittest.main()
