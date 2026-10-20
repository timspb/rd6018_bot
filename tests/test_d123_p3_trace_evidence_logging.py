from types import SimpleNamespace
import unittest

from runtime.charge.evidence.trace_context import log_analysis_events
from signal_analyzer import SignalEvent


class TraceEvidenceLoggingTests(unittest.TestCase):
    def test_analysis_events_keep_existing_payloads_and_values(self):
        metrics = SimpleNamespace(
            current_min_a=0.42,
            voltage_max_v=14.73,
            delta_current_from_min_a=0.18,
            delta_voltage_from_max_v=0.24,
        )
        record = SimpleNamespace(
            analysis=SimpleNamespace(
                metrics=metrics,
                events=frozenset({
                    SignalEvent.CURRENT_MINIMUM_UPDATED,
                    SignalEvent.VOLTAGE_MAXIMUM_UPDATED,
                    SignalEvent.CURRENT_REVERSAL_CONFIRMED,
                    SignalEvent.VOLTAGE_REVERSAL_CONFIRMED,
                }),
            )
        )

        with self.assertLogs("rd6018.recovery", level="INFO") as captured:
            log_analysis_events(
                record, stage="Main Charge", session_id="session-123",
                timestamp_s=1234.5,
            )

        self.assertEqual(len(captured.output), 4)
        self.assertIn("CURRENT_MINIMUM_UPDATED Imin=0.420A stage=Main Charge session=session-123", captured.output[0])
        self.assertIn("kind=maximum event=update mode=CC Vmax=14.730 timestamp=1234.500", captured.output[1])
        self.assertIn("kind=delta event=confirmation mode=CV Imin=0.420 delta=0.180 timestamp=1234.500", captured.output[2])
        self.assertIn("kind=delta event=confirmation mode=CC Vmax=14.730 delta=0.240 timestamp=1234.500", captured.output[3])


if __name__ == "__main__":
    unittest.main()
