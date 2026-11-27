"""Operator journal milestones are observational, never actuator decisions."""
import math
import unittest
from types import SimpleNamespace

from runtime.charge.evidence.trace_context import operator_journal_signal_event
from runtime.ui.components.journal import format_journal_event, operator_journal_events
from signal_analyzer import SignalEvent


class JournalMilestoneTests(unittest.TestCase):
    @staticmethod
    def record(events, *, minimum=None, maximum=None, **extra):
        metrics = {"current_min_a": minimum, "voltage_max_v": maximum, **extra}
        return SimpleNamespace(analysis=SimpleNamespace(
            events=set(events), metrics=SimpleNamespace(**metrics),
        ))

    def event(self, record, stage="Main Charge", prior=None, *, is_cv=False, is_cc=False):
        return operator_journal_signal_event(
            record, stage=stage, main_stage="Main Charge",
            mix_stage="Mix Mode", previous_current_min_a=prior,
            is_cv=is_cv, is_cc=is_cc)

    def test_main_first_minimum_begins_same_analyzer_timer(self):
        event = self.event(self.record([SignalEvent.CURRENT_MINIMUM_UPDATED], minimum=.23))
        self.assertEqual(event, "MAIN_HOLD_START | Imin=0.230A")
        rendered = format_journal_event(
            f"[2026-11-07 15:30:00] | Main Charge | 14.76 | 0.23 | 26.0 | 0.00 | {event}")
        self.assertIn("Imin 0,23 А", rendered)
        self.assertNotIn("?", rendered)
        self.assertEqual(rendered.count("\n"), 0)

    def test_new_lower_main_minimum_restarts_hold(self):
        event = self.event(self.record([SignalEvent.CURRENT_MINIMUM_UPDATED], minimum=.20), prior=.23)
        self.assertEqual(event, "MAIN_HOLD_RESET | Imin=0.200A")
        self.assertIn("RE Imin 0,2 А", format_journal_event(
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
        self.assertEqual(minimum, "MIX_IMIN_UPDATED | mode=unknown | Imin=0.300A")
        self.assertEqual(maximum, "MIX_VMAX_UPDATED | Vmax=16.700V | mode=unknown")

    def test_mix_delta_confirmation_is_logged_only_for_the_confirmed_mode(self):
        cv = self.record(
            [SignalEvent.CURRENT_REVERSAL_CONFIRMED], minimum=.30,
            delta_current_from_min_a=.56, reversal_threshold_a=.55,
            seconds_since_current_min=4200., reversal_confirmations=3,
        )
        cc = self.record(
            [SignalEvent.VOLTAGE_REVERSAL_CONFIRMED], maximum=16.70,
            delta_voltage_from_max_v=.11, voltage_reversal_threshold_v=.10,
            seconds_since_voltage_max=1800., voltage_reversal_confirmations=3,
        )
        cv_event = self.event(cv, "Mix Mode", is_cv=True)
        cc_event = self.event(cc, "Mix Mode", is_cc=True)
        self.assertIn("MIX_DELTA_CONFIRMED | mode=CV", cv_event)
        self.assertIn("delta_a=0.560", cv_event)
        self.assertIn("required_delta_a=0.550", cv_event)
        self.assertIn("confirmations=3", cv_event)
        self.assertIn("MIX_DELTA_CONFIRMED | mode=CC", cc_event)
        self.assertIn("delta_v=0.110", cc_event)
        self.assertIn("required_delta_v=0.100", cc_event)

    def test_main_mix_entry_log_carries_measured_hold_and_temperature(self):
        event = (
            "MIX_STARTED | reason=main_hold_complete | target_voltage_v=16.50 | "
            "target_current_a=1.80 | mode=CV | main_imin_a=0.300 | "
            "main_hold_age_s=10800.000 | main_hold_required_s=10800.000 | "
            "main_delta_a=0.560 | main_required_delta_a=0.550 | temperature_c=25.000"
        )
        row = f"[2026-11-09 21:00:00] | Mix Mode | 14.80 | 0.20 | 25.0 | 0.00 | {event}"
        rendered = format_journal_event(row)
        self.assertIn("выдержка 180м/180м", rendered)
        self.assertIn("ΔI 0.560/0.550 А", rendered)
        self.assertIn("T 25.000°C", rendered)

    def test_temperature_source_event_is_not_misclassified_as_warning(self):
        row = (
            "[2026-11-09 21:01:00] | Main Charge | 14.80 | 0.20 | 23.0 | 0.00 | "
            "TEMP_SOURCE | source=temp_ext_v2 | entity_id=sensor.rd6018_external_v2 "
            "| status=ok | age_s=4.0"
        )
        rendered = format_journal_event(row)
        self.assertIn("Источник температуры АКБ", rendered)
        self.assertIn("sensor.rd6018_external_v2", rendered)
        self.assertNotIn("Предупреждение", rendered)

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
