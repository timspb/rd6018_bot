import unittest

from runtime.journal import InMemoryJournalRecorder, JournalEventFactory, JournalEventType, format_entry
from runtime.ui import ChargeView, RuntimeUISnapshot, SafetyView, TelemetryView, TransitionView
from ui_mapping_fixtures import snapshot_from_mapping


class V3UIJournalBoundaryTests(unittest.TestCase):
    def test_journal_is_single_line_and_recorder_has_tail(self):
        entry = JournalEventFactory.periodic(0.0, "MIX CV", {"V": "14.40V", "I": "0.21A", "Ah": "1.2"})
        rendered = format_entry(entry)
        self.assertNotIn("\n", rendered)
        recorder = InMemoryJournalRecorder()
        recorder.append(entry)
        self.assertEqual(recorder.tail(1), (entry,))

    def test_event_and_transition_models_are_data_only(self):
        transition = TransitionView("Imin", "0.21A", 10.0, True)
        snapshot = RuntimeUISnapshot(
            ChargeView("MIX", "manual", conditions=(transition,)),
            telemetry=TelemetryView(14.4, 0.21, 30.0, 1.2),
            safety=SafetyView(True),
        )
        self.assertTrue(snapshot.charge.conditions[0].confirmed)

    def test_legacy_adapter_is_mapping_only(self):
        snapshot = snapshot_from_mapping({"charge": {"stage": "MAIN", "program": "normal"}})
        self.assertEqual(snapshot.charge.stage, "MAIN")

    def test_invalid_journal_entry_rejected(self):
        with self.assertRaises(ValueError):
            JournalEventFactory.event(1.0, JournalEventType.ERROR, "", "broken")


if __name__ == "__main__":
    unittest.main()
