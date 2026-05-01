import logging
import tempfile
import unittest
from pathlib import Path

import charging_log


class ChargingLogTests(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.log_path = Path(self._tmpdir.name) / "charging_history.log"

        self.logger = logging.getLogger("charging_history")
        self.original_handlers = self.logger.handlers[:]
        for handler in self.original_handlers:
            self.logger.removeHandler(handler)

        self.original_log_file = charging_log.LOG_FILE
        self.original_charge_logger = charging_log._charge_logger
        charging_log.LOG_FILE = str(self.log_path)
        charging_log._charge_logger = None
        self.addCleanup(self._restore_logging)

    def _restore_logging(self):
        for handler in self.logger.handlers[:]:
            self.logger.removeHandler(handler)
            try:
                handler.close()
            except Exception:
                pass

        charging_log.LOG_FILE = self.original_log_file
        charging_log._charge_logger = self.original_charge_logger
        for handler in self.original_handlers:
            self.logger.addHandler(handler)

    def test_session_header_marks_current_session_start(self):
        self.log_path.write_text(
            "[2026-01-01 00:00:00] | Idle         |  0.00 |  0.00 |   0.0 |   0.00 | RESTORE | old\n",
            encoding="utf-8",
        )

        charging_log.log_session_header(
            "start",
            "Main Charge",
            0.0,
            0.0,
            0.0,
            0.0,
            "EFB",
            60,
            "Main 14.8V; 0.3A/3h -> Mix 16.5V.",
            meta={"session_reason": "User Command"},
        )
        charging_log.log_event("Main Charge", 14.8, 1.2, 25.0, 1.0, "TRACK")

        events = charging_log.get_recent_events(10)

        self.assertEqual(len(events), 2)
        self.assertTrue(events[0].endswith("SESSION_START | kind=start | profile=EFB | capacity_ah=60 | rules=Main 14.8V; 0.3A/3h -> Mix 16.5V. | session_reason=User Command"))
        self.assertNotIn("RESTORE | old", "\n".join(events))

    def test_consecutive_duplicates_are_collapsed(self):
        charging_log.log_session_header(
            "start",
            "Main Charge",
            0.0,
            0.0,
            0.0,
            0.0,
            "Ca/Ca",
            60,
            "Main 14.7V; 0.3A/3h -> Mix 16.5V.",
        )
        for _ in range(3):
            charging_log.log_event("Main Charge", 14.8, 0.1, 25.0, 2.0, "EMERGENCY_UNAVAILABLE")

        events = charging_log.get_recent_events(10)

        self.assertTrue(any("(x3)" in event for event in events))


if __name__ == "__main__":
    unittest.main()
