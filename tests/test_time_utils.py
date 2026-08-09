import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from time_utils import format_time_user_tz, now_utc, parse_datetime, timestamp_iso_utc


class TimeUtilsTests(unittest.TestCase):
    def test_iso_z_is_converted_to_user_timezone(self):
        with patch("time_utils.USER_TIMEZONE", "Asia/Vladivostok"):
            self.assertEqual(
                format_time_user_tz(parse_datetime("2026-08-09T05:00:00Z")),
                "15:00:00",
            )

    def test_naive_legacy_datetime_is_explicitly_utc(self):
        with patch("time_utils.USER_TIMEZONE", "Asia/Vladivostok"):
            self.assertEqual(
                format_time_user_tz(datetime(2026, 8, 9, 5, 0, 0)),
                "15:00:00",
            )

    def test_epoch_serialization_is_unambiguous(self):
        value = datetime(2026, 8, 9, 5, 0, tzinfo=timezone.utc).timestamp()
        self.assertEqual(timestamp_iso_utc(value), "2026-08-09T05:00:00Z")

    def test_trend_summary_uses_user_timezone_for_age(self):
        from bot import _build_trend_summary

        with patch("time_utils.USER_TIMEZONE", "Asia/Vladivostok"):
            current = now_utc()
            times = [
                (current - timedelta(minutes=10)).isoformat().replace("+00:00", "Z"),
                current.isoformat().replace("+00:00", "Z"),
            ]
            summary = _build_trend_summary(times, [16.4, 16.5], [1.8, 1.9])

        self.assertIn("10 мин назад", summary)
        self.assertIn("сейчас", summary)


if __name__ == "__main__":
    unittest.main()
