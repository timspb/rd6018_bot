"""Read-only MIX checkpoint evidence and operator rendering regression."""
import unittest

from runtime.charge.evidence.mix_progress_journal import mix_progress_event
from runtime.ui.components.journal import format_journal_event, operator_journal_events


class MixProgressJournalTests(unittest.TestCase):
    def setUp(self):
        self.signal = {
            "stage": "Mix Mode",
            "session_id": "session-1",
            "telemetry_valid": True,
            "telemetry_observed_at": 1000.0,
            "current_min_a": 0.30,
            "delta_current_from_min_a": 0.56,
            "reversal_threshold_a": 0.55,
            "reversal_confirmations": 3,
            "voltage_max_v": 16.70,
            "delta_voltage_from_max_v": 0.11,
            "voltage_reversal_threshold_v": 0.10,
            "voltage_reversal_confirmations": 2,
        }

    def event(self, live, signal=None, **overrides):
        opts = {
            "stage": "Mix Mode",
            "session_id": "session-1",
            "now_s": 1010.0,
            "max_age_s": 300.0,
            "hold_started_at": 900.0,
            **overrides,
        }
        return mix_progress_event(live, self.signal if signal is None else signal, **opts)

    def test_cc_reads_physical_register_and_voltage_delta(self):
        event = self.event({"regulation_code": 1})
        self.assertIn("MIX_PROGRESS | evidence=fresh | mode=CC", event)
        self.assertIn("Vmax=16.700V", event)
        self.assertIn("delta_v=0.110", event)
        self.assertIn("required_delta_v=0.100", event)
        self.assertIn("confirmations=2", event)
        self.assertIn("hold_elapsed_s=110.0", event)
        row = f"[2026-11-09 20:36:00] | Mix Mode | 16.42 | 1.79 | 25.0 | 0.00 | {event}"
        self.assertEqual(operator_journal_events([row]), [row])
        formatted = format_journal_event(row)
        self.assertIn("MIX CC", formatted)
        self.assertIn("ΔV 0.110/0.100 В", formatted)
        self.assertIn("выдержка идёт 1м", formatted)

    def test_cv_uses_analyzer_current_evidence(self):
        event = self.event({"regulation_code": 0})
        self.assertIn("mode=CV", event)
        self.assertIn("Imin=0.300A", event)
        self.assertIn("delta_a=0.560", event)
        self.assertNotIn("delta_v=", event)

    def test_missing_stale_wrong_session_and_unknown_regulator_fail_read_only(self):
        signal = dict(self.signal)
        for kwargs in (
            {"signal": {}},
            {"signal": {**signal, "telemetry_observed_at": 500.0}},
            {"signal": {**signal, "telemetry_valid": False}},
            {"session_id": "foreign"},
            {"now_s": 999.0},
        ):
            event = self.event(
                {"regulation_code": 1},
                kwargs.pop("signal", signal), **kwargs,
            )
            self.assertIn("evidence=", event)
            self.assertNotIn("Vmax=", event)
            self.assertNotIn("Imin=", event)
        unknown = self.event({"regulation_code": 9})
        self.assertIn("mode=unknown", unknown)
        self.assertNotIn("Vmax=", unknown)


if __name__ == "__main__":
    unittest.main()
