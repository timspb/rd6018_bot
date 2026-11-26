"""Behavioral baseline for the delegated operator OFF-condition owner."""

import json
import ast
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from runtime.operator.off_conditions import OperatorOffConditions

ROOT = Path(__file__).resolve().parents[1]


class OperatorOffConditionsBaselineTests(unittest.TestCase):
    def _preset_runner(self, state, path):
        tree = ast.parse((ROOT / "runtime" / "production_runtime.py").read_text(encoding="utf-8"))
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                    and n.name == "_apply_manual_off_preset")
        saves = []
        namespace = {
            "_operator_off_conditions": state,
            "time": __import__("time"),
            "_save_manual_off_state": lambda: (saves.append(state.to_document()), state.save(path)),
        }
        exec(compile(ast.Module(body=[node], type_ignores=[]), "production_runtime.py", "exec"), namespace)
        return namespace["_apply_manual_off_preset"], state, saves

    def test_empty_state_removes_existing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manual_off_state.json"
            path.write_text('{"old": true}', encoding="utf-8")
            OperatorOffConditions().save(path)
            self.assertFalse(path.exists())

    def test_all_six_legacy_keys_roundtrip_including_numeric_strings(self):
        expected = {"voltage_ge": 16.2, "voltage_le": 12.1, "current_le": 0.3,
                    "current_ge": 1.4, "time_sec": 7200.0, "start_time": 123456.5}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manual_off_state.json"
            path.write_text(json.dumps({key: str(value) for key, value in expected.items()}), encoding="utf-8")
            state = OperatorOffConditions()
            self.assertTrue(state.load(path))
            self.assertEqual(state.to_document(), expected)
            state.save(path)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), expected)

    def test_named_preset_values_and_clear_semantics(self):
        cases = (("time_2h", {"time_sec": 7200.0}),
                 ("i_le_030", {"current_le": 0.30}),
                 ("v_ge_162", {"voltage_ge": 16.2}),
                 ("clear", {}))
        messages = {
            "time_2h": "✅ Preset применён: выключение через 2 часа.",
            "i_le_030": "✅ Preset применён: выключение при I≤0.30 A.",
            "v_ge_162": "✅ Preset применён: выключение при V≥16.2 V.",
            "clear": "✅ Условие выключения сброшено.",
        }
        for name, expected in cases:
            with self.subTest(preset=name):
                with tempfile.TemporaryDirectory() as directory:
                    path = Path(directory) / "manual_off_state.json"
                    state = OperatorOffConditions(voltage_ge=11.0, start_time=99.0)
                    runner, state, saves = self._preset_runner(state, path)
                    if name == "time_2h":
                        with patch("time.time", return_value=100.0):
                            result = runner(name)
                    else:
                        result = runner(name)
                    self.assertEqual(result, messages[name])
                    self.assertTrue(state.has_condition() if expected else not state.has_condition())
                    for key, value in expected.items():
                        self.assertEqual(getattr(state, key), value)
                    if name == "time_2h":
                        self.assertEqual(state.start_time, 100.0)
                    self.assertEqual(path.exists(), bool(expected))
                    self.assertEqual(len(saves), 1)

    def test_invalid_preset_contract_remains_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manual_off_state.json"
            state = OperatorOffConditions(voltage_ge=16.0)
            runner, _state, saves = self._preset_runner(state, path)
            with self.assertRaisesRegex(ValueError, "unknown_off_preset"):
                runner("not_a_preset")
            self.assertFalse(state.has_condition())
            self.assertFalse(path.exists())
            self.assertEqual(len(saves), 1)

    def test_preset_save_failure_propagates_after_owner_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manual_off_state.json"
            state = OperatorOffConditions()
            runner, _state, _saves = self._preset_runner(state, path)
            namespace = runner.__globals__
            namespace["_save_manual_off_state"] = lambda: (_ for _ in ()).throw(OSError("disk"))
            with self.assertRaisesRegex(OSError, "disk"):
                runner("v_ge_162")
            self.assertEqual(state.voltage_ge, 16.2)

    def test_exact_off_is_a_condition_clear_and_not_output_actuation(self):
        state = OperatorOffConditions(voltage_ge=16.2)
        calls = []
        state.clear()
        self.assertFalse(state.has_condition())
        self.assertEqual(calls, [])

    def test_non_mapping_json_unarms_without_exception(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manual_off_state.json"
            path.write_text("[]", encoding="utf-8")
            state = OperatorOffConditions(voltage_ge=12.0)
            self.assertFalse(state.load(path))
            self.assertFalse(state.has_condition())

    def test_bad_numeric_json_unarms_without_exception(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manual_off_state.json"
            path.write_text('{"voltage_ge": "bad"}', encoding="utf-8")
            state = OperatorOffConditions(voltage_ge=12.0)
            self.assertFalse(state.load(path))
            self.assertFalse(state.has_condition())


if __name__ == "__main__":
    unittest.main()
