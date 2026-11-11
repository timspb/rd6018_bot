from datetime import datetime, timedelta, timezone
import unittest
from unittest.mock import patch

import runtime.production_runtime as production_runtime


class TemperatureSourceJournalTests(unittest.TestCase):
    def setUp(self):
        self.previous = production_runtime._temperature_source_observer.last_signature
        production_runtime._temperature_source_observer.last_signature = None

    def tearDown(self):
        production_runtime._temperature_source_observer.last_signature = self.previous

    def test_failed_journal_write_is_retried_and_never_marks_evidence_saved(self):
        now = datetime.now(timezone.utc)
        live = {
            "temp_ext": 25.0,
            "_meta": {"temp_ext": {
                "source_key": "temp_ext_v2",
                "entity_id": "sensor.rd6018_external_v2",
                "status": "ok",
                "age_s": 1.0,
                "last_reported": now.isoformat(),
            }},
        }
        args = dict(
            stage="Mix Mode", voltage=16.42, current=1.79,
            temperature=25.0, ah=1.0, session_id="test-run",
        )
        with patch.object(
            production_runtime, "log_event", side_effect=OSError("journal unavailable")
        ):
            with self.assertRaises(OSError):
                production_runtime._log_temperature_source_if_changed(live, **args)
        self.assertIsNone(production_runtime._temperature_source_observer.last_signature)
        with patch.object(production_runtime, "log_event") as write:
            production_runtime._log_temperature_source_if_changed(live, **args)
            self.assertEqual(write.call_count, 1)
            self.assertIn("TEMP_SOURCE", write.call_args.args[-1])

    def test_source_value_freshness_and_session_changes_are_logged_once(self):
        now = datetime.now(timezone.utc)
        live = {
            "temp_ext": 23.0,
            "_meta": {
                "temp_ext": {
                    "source_key": "temp_ext_v2",
                    "entity_id": "sensor.rd6018_rd_6018_temperature_external_v2",
                    "status": "ok",
                    "age_s": 4.0,
                    "last_reported": now.isoformat(),
                }
            },
        }
        args = dict(
            stage="Main Charge", voltage=14.8, current=.2,
            temperature=23.0, ah=1.0, session_id="session-1",
        )
        with patch.object(production_runtime, "log_event") as write:
            production_runtime._log_temperature_source_if_changed(live, **args)
            production_runtime._log_temperature_source_if_changed(live, **args)
            self.assertEqual(write.call_count, 1)
            self.assertIn("TEMP_SOURCE", write.call_args.args[-1])
            self.assertIn("temp_ext_v2", write.call_args.args[-1])
            self.assertIn("age_s=4.0", write.call_args.args[-1])

            live["temp_ext"] = 23.1
            args["temperature"] = 23.1
            production_runtime._log_temperature_source_if_changed(live, **args)
            self.assertEqual(write.call_count, 1)  # No every-0.1°C log flood.

            live["temp_ext"] = 24.0
            args["temperature"] = 24.0
            production_runtime._log_temperature_source_if_changed(live, **args)
            self.assertEqual(write.call_count, 2)

            live["_meta"]["temp_ext"]["last_reported"] = (
                now - timedelta(seconds=30)
            ).isoformat()
            production_runtime._log_temperature_source_if_changed(live, **args)
            self.assertEqual(write.call_count, 3)
            self.assertIn("stale_or_invalid", write.call_args.args[-1])

            args["session_id"] = "session-2"
            production_runtime._log_temperature_source_if_changed(live, **args)
            self.assertEqual(write.call_count, 4)


if __name__ == "__main__":
    unittest.main()
