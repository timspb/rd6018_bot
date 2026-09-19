import unittest
from datetime import datetime, timedelta, timezone

from safe_output import output_state_confidence, snapshot_from_live


def _live(*, modbus_age=1.0, protection_code=0, switch_age_s=3846.6):
    now = datetime.now(timezone.utc)
    fresh = now.isoformat()
    old = (now - timedelta(seconds=switch_age_s)).isoformat()
    return {
        "battery_voltage": 12.7,
        "voltage": 0.0,
        "current": 0.0,
        "temp_ext": 25.0,
        "temp_int": 31.0,
        "switch": "off",
        "output_state_code_v2": 0,
        "take_out": False,
        "safety_modbus_age": modbus_age,
        "protection_code": protection_code,
        "_meta": {
            key: {"status": "ok", "last_reported": fresh, "last_updated": fresh}
            for key in (
                "battery_voltage", "current", "temp_ext", "temp_int",
                "output_state_code_v2", "take_out", "protection_code",
            )
        } | {"switch": {"status": "ok", "last_reported": old, "last_updated": old}},
    }


class OutputStateConfidenceTests(unittest.TestCase):
    def test_off_with_old_last_changed_and_fresh_modbus_allows(self):
        live = _live()
        confidence = output_state_confidence(live)

        self.assertTrue(confidence.allowed)
        self.assertFalse(confidence.output_on)
        self.assertIsNotNone(snapshot_from_live(live))

    def test_stale_modbus_denies(self):
        confidence = output_state_confidence(_live(modbus_age=20.1))

        self.assertFalse(confidence.allowed)
        self.assertIn("stale", confidence.reason)
        self.assertIsNone(snapshot_from_live(_live(modbus_age=20.1)))

    def test_protection_fault_denies(self):
        confidence = output_state_confidence(_live(protection_code=1))

        self.assertFalse(confidence.allowed)
        self.assertIn("protection", confidence.reason)
        self.assertIsNone(snapshot_from_live(_live(protection_code=1)))


if __name__ == "__main__":
    unittest.main()
