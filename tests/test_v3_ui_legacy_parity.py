import unittest

from runtime.ui import ChargeView, DiagnosticsView, RuntimeUISnapshot, SafetyView, TelemetryView
from runtime.ui.legacy_shadow import LegacyUISnapshotAdapter, UIParityComparator


class V3UILegacyParityTests(unittest.TestCase):
    def _snapshot(self):
        return RuntimeUISnapshot(
            ChargeView("MAIN", "normal", phase="CV", active_recipe="CV", timer_text="2ч"),
            telemetry=TelemetryView(14.4, 2.0, 30.0),
            diagnostics=DiagnosticsView("healthy"),
            safety=SafetyView(True),
            output={"enabled": True}, journal_tail=("started",),
        )

    def test_full_legacy_mapping_matches_available_v3_fields(self):
        legacy = LegacyUISnapshotAdapter.from_mapping({
            "charge": {"stage": "MAIN", "phase": "CV", "voltage": 14.4, "current": 2.0, "temperature": 30.0, "timers": {"stage": "2ч"}, "messages": ["started"]},
            "diagnostics": {"battery_status": "healthy"}, "output": {"enabled": True},
        })
        result = UIParityComparator.compare(legacy, self._snapshot())
        self.assertEqual(result.status, "MATCH")

    def test_missing_and_changed_fields_are_distinguished(self):
        legacy = LegacyUISnapshotAdapter.from_mapping({"stage": "MAIN", "voltage": 14.4, "current": 2.0, "temperature": 30.0, "warnings": ["x"]})
        changed = RuntimeUISnapshot(ChargeView("MIX", "normal"), telemetry=TelemetryView(14.5, 2.0, 30.0))
        result = UIParityComparator.compare(legacy, changed)
        self.assertIn("stage", result.mismatches)
        self.assertIn("warnings", result.missing_fields)


if __name__ == "__main__":
    unittest.main()
