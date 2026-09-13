import ast
import pathlib
import unittest
from dataclasses import FrozenInstanceError

from runtime.telemetry import (
    AccumulatorState,
    ChargeAccumulator,
    InMemoryTelemetryRecorder,
    TelemetryFieldQuality,
    TelemetryHistory,
    TelemetryQualityStatus,
    TelemetryRecorder,
    TelemetrySnapshot,
    assess_field,
)


ROOT = pathlib.Path(__file__).parents[1] / "runtime" / "telemetry"


class V3TelemetryTests(unittest.TestCase):
    def test_snapshot_is_immutable_and_complete(self):
        snapshot = TelemetrySnapshot(voltage=14.4, current=2.0, output_state=True, timestamp=10.0)
        with self.assertRaises(FrozenInstanceError):
            snapshot.voltage = 15.0
        self.assertTrue(hasattr(snapshot, "programmed_voltage"))
        self.assertTrue(hasattr(snapshot, "accumulated_ah"))

    def test_field_quality_valid_stale_invalid_missing(self):
        valid = assess_field("voltage", 14.4, timestamp=98.0, now=100.0, source="HA", max_age=5.0)
        stale = assess_field("voltage", 14.4, timestamp=90.0, now=100.0, source="HA", max_age=5.0)
        invalid = assess_field("voltage", float("nan"), timestamp=98.0, now=100.0, source="HA", max_age=5.0)
        missing = assess_field("voltage", None, timestamp=None, now=100.0, source="HA", max_age=5.0)
        self.assertEqual(TelemetryQualityStatus.VALID, valid.status)
        self.assertEqual(TelemetryQualityStatus.STALE, stale.status)
        self.assertEqual(TelemetryQualityStatus.INVALID, invalid.status)
        self.assertEqual(TelemetryQualityStatus.MISSING, missing.status)
        self.assertIsInstance(valid, TelemetryFieldQuality)

    def test_history_append_and_window(self):
        history = TelemetryHistory(max_samples=2)
        history.append(TelemetrySnapshot(voltage=14.0, timestamp=1.0))
        history.append(TelemetrySnapshot(voltage=14.1, timestamp=2.0))
        history.append(TelemetrySnapshot(voltage=14.2, timestamp=3.0))
        self.assertEqual((14.1, 14.2), tuple(item.voltage for item in history.window(since=2.0)))
        self.assertEqual(2, len(history))

    def test_accumulator_integrates_and_supports_restore_reset(self):
        accumulator = ChargeAccumulator()
        accumulator.add(TelemetrySnapshot(current=2.0, timestamp=0.0))
        result = accumulator.add(TelemetrySnapshot(current=2.0, timestamp=3600.0))
        self.assertAlmostEqual(2.0, result)
        restored = ChargeAccumulator(AccumulatorState(5.0, 10.0, 20.0, 2.0))
        result = restored.add(TelemetrySnapshot(current=2.0, timestamp=3620.0))
        self.assertAlmostEqual(5.0 + 2.0 * 10.0 / 3600.0, result)
        restored.reset()
        self.assertEqual(0.0, restored.state.accumulated_ah)

    def test_recorder_is_in_memory_only(self):
        recorder = InMemoryTelemetryRecorder()
        recorder.record(TelemetrySnapshot(timestamp=1.0))
        self.assertIsInstance(recorder, TelemetryRecorder)
        self.assertEqual(1, len(recorder.records))

    def test_telemetry_layer_has_no_transport_or_actuator_imports(self):
        forbidden_modules = {"hass_api", "aiogram", "serial", "modbus", "rd_control_mode", "bot_legacy"}
        forbidden_calls = {"turn_on", "turn_off", "set_voltage", "set_current", "set_ovp", "set_ocp"}
        for path in ROOT.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    self.assertTrue(forbidden_modules.isdisjoint({alias.name.split(".")[0] for alias in node.names}))
                elif isinstance(node, ast.ImportFrom):
                    self.assertNotIn((node.module or "").split(".")[0], forbidden_modules, str(path))
                elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                    self.assertNotIn(node.func.attr, forbidden_calls, str(path))


if __name__ == "__main__":
    unittest.main()
