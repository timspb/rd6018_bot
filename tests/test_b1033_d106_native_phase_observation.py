import unittest
import ast
import inspect
from pathlib import Path

from tools.node104_native_phase_capture import (
    PhaseCaptureError, capture_native_phase,
)
from tools.node104_d106_live_observer import collect_live


def records(*, output=1, generation=7, source="esp_native_api", age=0.5):
    fields = (
        ("output_r18", "output_state", 1, output),
        ("voltage_v", "output_voltage", 2, 14.2),
        ("current_a", "output_current", 3, 0.8),
    )
    return {
        field: {
            "value": value,
            "meta": {
                "source": source, "object_id": field,
                "actual_object_id": actual_id, "status": "ok",
                "native_type": "SensorState", "native_key": key,
                "device_id": 0, "connection_generation": generation,
                "subscription_timestamp_monotonic": 12.0,
                "age_s": age,
            },
        }
        for field, actual_id, key, value in fields
    }


class B1033NativePhaseObservationTests(unittest.TestCase):
    def capture(self, values):
        return capture_native_phase(
            values, phase_started_monotonic=11.0,
            captured_at_monotonic=12.5,
        )

    def test_on_phase_is_read_only_native_observation_with_identity_and_age(self):
        result = self.capture(records())
        self.assertEqual(result["output_r18"]["value"], 1)
        self.assertEqual(result["output_r18"]["source"], "esp_native_api")
        self.assertEqual(result["voltage_v"]["actual_object_id"], "output_voltage")
        self.assertEqual(result["current_a"]["source_key"], 3)
        self.assertEqual(result["voltage_v"]["connection_generation"], 7)
        self.assertEqual(result["voltage_v"]["subscription_timestamp_monotonic"], 12.0)
        self.assertEqual(result["voltage_v"]["age_s"], 0.5)
        self.assertNotIn("trial_off_proof", result)

    def test_off_callback_remains_a_phase_observation_not_an_off_proof(self):
        result = self.capture(records(output=0))
        self.assertEqual(result["output_r18"]["value"], 0)
        self.assertEqual(set(result), {"output_r18", "voltage_v", "current_a"})

    def test_opt_in_reuses_one_callback_collection_and_default_remains_off_proof(self):
        self.assertFalse(inspect.signature(collect_live).parameters[
            "phase_observation"].default)
        source = Path(inspect.getsourcefile(collect_live)).read_text(encoding="utf-8")
        tree = ast.parse(source)
        live = next(node for node in tree.body if isinstance(node, ast.AsyncFunctionDef)
                    and node.name == "collect_live")
        native_callback_calls = [node for node in ast.walk(live)
                                 if isinstance(node, ast.Call)
                                 and isinstance(node.func, ast.Attribute)
                                 and node.func.attr == "_fresh_measured_sensor_callbacks"]
        self.assertEqual(len(native_callback_calls), 1)
        self.assertIn("projection.project_off(snapshot, now=captured)", source)
        phase_branch = next(node for node in ast.walk(live)
                            if isinstance(node, ast.If)
                            and isinstance(node.test, ast.Name)
                            and node.test.id == "phase_observation")
        branch_calls = [
            (node.func.attr if isinstance(node.func, ast.Attribute)
             else node.func.id if isinstance(node.func, ast.Name) else "")
            for node in ast.walk(phase_branch) if isinstance(node, ast.Call)
        ]
        self.assertIn("capture_native_phase", branch_calls)
        self.assertFalse(set(branch_calls) & {
            "turn_on", "turn_off", "set_output", "set_voltage", "set_current",
        })

    def test_ha_only_measurements_are_rejected(self):
        with self.assertRaisesRegex(PhaseCaptureError, "wrong Native callback source"):
            self.capture(records(source="ha102_rest"))

    def test_cross_generation_callbacks_are_rejected(self):
        values = records()
        values["current_a"]["meta"]["connection_generation"] = 8
        with self.assertRaisesRegex(PhaseCaptureError, "span connection generations"):
            self.capture(values)

    def test_missing_generation_and_stale_callback_are_rejected(self):
        values = records()
        values["voltage_v"]["meta"].pop("connection_generation")
        with self.assertRaisesRegex(PhaseCaptureError, "generation missing"):
            self.capture(values)
        values = records()
        values["voltage_v"]["meta"]["subscription_timestamp_monotonic"] = 1.0
        with self.assertRaisesRegex(PhaseCaptureError, "phase/freshness"):
            self.capture(values)


if __name__ == "__main__":
    unittest.main()
