"""Operator journal milestones are observational, never actuator decisions."""
import math
import unittest
from types import SimpleNamespace

from runtime.charge.evidence.trace_context import operator_journal_signal_event
from runtime.ui.components.journal import format_journal_event, operator_journal_events
from signal_analyzer import SignalEvent


class JournalMilestoneTests(unittest.TestCase):
    @staticmethod
    def record(events, *, minimum=None, maximum=None):
        return SimpleNamespace(analysis=SimpleNamespace(
            events=set(events),
            metrics=SimpleNamespace(current_min_a=minimum, voltage_max_v=maximum),
        ))

    def event(self, record, stage="Main Charge", prior=None):
        return operator_journal_signal_event(
            record, stage=stage, main_stage="Main Charge",
            mix_stage="Mix Mode", previous_current_min_a=prior)

    def test_main_first_minimum_begins_same_analyzer_timer(self):
        event = self.event(self.record([SignalEvent.CURRENT_MINIMUM_UPDATED], minimum=.23))
        self.assertEqual(event, "MAIN_HOLD_START | Imin=0.230A")
        rendered = format_journal_event(
            f"[2026-11-07 15:30:00] | Main Charge | 14.76 | 0.23 | 26.0 | 0.00 | {event}")
        self.assertIn("Imin=0,23?", rendered)
        self.assertIn("?", rendered)
        self.assertNotIn("Imin=0.230A", rendered)
        self.assertEqual(rendered.count("\n"), 0)

    def test_new_lower_main_minimum_restarts_hold(self):
        event = self.event(self.record([SignalEvent.CURRENT_MINIMUM_UPDATED], minimum=.20), prior=.23)
        self.assertEqual(event, "MAIN_HOLD_RESET | Imin=0.200A")
        self.assertIn("RE Imin=0,2?", format_journal_event(
            f"[2026-11-07 15:45:00] | Main Charge | 14.76 | 0.20 | 26.0 | 0.00 | {event}"))

    def test_mix_started_is_visible_with_reason_and_target_setpoints(self):
        event = "MIX_STARTED | reason=main_hold_complete_recovery_mix | target_voltage_v=16.50 | target_current_a=1.80"
        row = f"[2026-11-09 20:26:00] | Mix Mode | 14.83 | 0.20 | 23.0 | 0.00 | {event}"
        self.assertTrue(operator_journal_events((row,)))
        rendered = format_journal_event(row)
        self.assertIn("Начат MIX", rendered)
        self.assertIn("main hold complete recovery mix", rendered)
        self.assertIn("16,50 В", rendered)
        self.assertIn("1,80 А", rendered)

    def test_mix_minimum_and_maximum_are_mode_evidence(self):
        minimum = self.event(self.record([SignalEvent.CURRENT_MINIMUM_UPDATED], minimum=.30), "Mix Mode")
        maximum = self.event(self.record([SignalEvent.VOLTAGE_MAXIMUM_UPDATED], maximum=16.7), "Mix Mode")
        self.assertEqual(minimum, "MIX_IMIN_UPDATED | Imin=0.300A")
        self.assertEqual(maximum, "MIX_VMAX_UPDATED | Vmax=16.700V")

    def test_no_unobserved_evidence_or_wrong_stage(self):
        no_event = self.record([], minimum=.2)
        self.assertIsNone(self.event(no_event))
        self.assertIsNone(self.event(self.record([SignalEvent.CURRENT_MINIMUM_UPDATED], minimum=.2), "Idle"))
        self.assertIsNone(self.event(self.record([SignalEvent.CURRENT_MINIMUM_UPDATED], minimum=math.nan)))

    def test_periodic_rows_filtered_before_operator_paging(self):
        source = (
            "[2026-11-07 15:00:00] | Main Charge | 14.76 | 0.25 | 27 | 0 | SESSION_START | profile=EFB",
            "[2026-11-07 15:10:00] | Main Charge | 14.76 | 0.24 | 26 | 0 | CHECKPOINT",
            "[2026-11-07 15:20:00] | Main Charge | 14.76 | 0.23 | 26 | 0 | MAIN_HOLD_START | Imin=0.230A",
            "[2026-11-07 15:25:00] | Main Charge | 14.76 | 0.23 | 26 | 0 | CHECKPOINT",
        )
        result = operator_journal_events(source)
        self.assertEqual(len(result), 2)
        self.assertTrue(result[-1].endswith("Imin=0.230A"))


if __name__ == "__main__":
    unittest.main()
