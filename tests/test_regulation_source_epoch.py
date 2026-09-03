from __future__ import annotations

import unittest

from rd6018_telemetry import _parse_iso_timestamp, canonicalize_live
from rd_managed_mix import ManagedMixAdoptionCoordinator


class RegulationSourceEpochTests(unittest.TestCase):
    def test_raw_regulation_heartbeat_replaces_stale_legacy_mode_metadata(self) -> None:
        fresh = "2026-09-03T12:30:00+00:00"
        stale = "2026-09-03T12:00:00+00:00"
        live = {
            "current": 0.18,
            "battery_voltage": 14.80,
            "temp_ext_v2": 27.0,
            "temp_ext": 26.0,
            "regulation_code": 1.0,
            "is_cv": True,
            "is_cc": False,
            "_meta": {
                "current": {"status": "ok", "last_reported": fresh},
                "battery_voltage": {"status": "ok", "last_reported": fresh},
                "temp_ext_v2": {"status": "ok", "last_reported": fresh},
                "temp_ext": {"status": "ok", "last_reported": stale},
                "regulation_code": {
                    "status": "ok",
                    "last_reported": fresh,
                    "entity_id": "sensor.rd6018_rd_6018_regulation_mode_code",
                },
                "is_cv": {"status": "ok", "last_reported": stale},
                "is_cc": {"status": "ok", "last_reported": stale},
            },
        }

        canonicalize_live(live)

        self.assertFalse(live["is_cv"])
        self.assertTrue(live["is_cc"])
        self.assertEqual(live["_meta"]["is_cv"]["last_reported"], fresh)
        self.assertEqual(live["_meta"]["is_cc"]["last_reported"], fresh)
        self.assertEqual(live["_meta"]["is_cv"]["source_key"], "regulation_code")
        self.assertEqual(live["_meta"]["is_cc"]["source_key"], "regulation_code")

        expected = _parse_iso_timestamp(fresh)
        self.assertIsNotNone(expected)
        self.assertEqual(ManagedMixAdoptionCoordinator._source_timestamp(live), expected)

    def test_legacy_mode_metadata_remains_authoritative_without_raw_code(self) -> None:
        legacy = "2026-09-03T12:15:00+00:00"
        live = {
            "regulation_code": "unavailable",
            "is_cv": True,
            "is_cc": False,
            "_meta": {
                "regulation_code": {"status": "unknown", "last_reported": None},
                "is_cv": {"status": "ok", "last_reported": legacy},
                "is_cc": {"status": "ok", "last_reported": legacy},
            },
        }

        canonicalize_live(live)

        self.assertTrue(live["is_cv"])
        self.assertFalse(live["is_cc"])
        self.assertEqual(live["_meta"]["is_cv"]["last_reported"], legacy)
        self.assertEqual(live["_meta"]["is_cc"]["last_reported"], legacy)
        self.assertNotIn("source_key", live["_meta"]["is_cv"])
        self.assertNotIn("source_key", live["_meta"]["is_cc"])


if __name__ == "__main__":
    unittest.main()
