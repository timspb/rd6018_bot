import unittest
from datetime import datetime, timedelta, timezone

from safe_output import OutputRequest, SafetySupervisor, snapshot_from_live


def _meta(stamp):
    return {"status": "ok", "last_reported": stamp, "last_updated": stamp}


def _live(*, v2_age_s=0.0, include_v2=True):
    stamp = (datetime.now(timezone.utc) - timedelta(seconds=v2_age_s)).isoformat()
    live = {
        "battery_voltage": 12.6,
        "voltage": 0.0,
        "current": 0.0,
        "temp_ext": 25.0,
        "temp_int": 30.0,
        "input_voltage": 64.0,
        "switch": "off",
        "protection_code": 0,
        "set_voltage": 99.0,
        "set_current": 99.0,
        "ovp": 99.0,
        "ocp": 99.0,
        "_meta": {
            key: _meta(stamp)
            for key in (
                "battery_voltage",
                "current",
                "temp_ext",
                "temp_int",
                "switch",
                "protection_code",
            )
        },
    }
    if include_v2:
        live.update(
            {
                "set_voltage_readback_v2": 14.4,
                "set_current_readback_v2": 2.0,
                "ovp_readback_v2": 14.5,
                "ocp_readback_v2": 2.1,
            }
        )
        live["_meta"].update(
            {
                key: _meta(stamp)
                for key in (
                    "set_voltage_readback_v2",
                    "set_current_readback_v2",
                    "ovp_readback_v2",
                    "ocp_readback_v2",
                )
            }
        )
    return live


class ProgrammedReadbackAuthorityAllTests(unittest.TestCase):
    REQUEST = OutputRequest(14.4, 2.0, 14.5, 2.1, 14.4)

    def test_fresh_canonical_readbacks_override_legacy_projection(self):
        telemetry = snapshot_from_live(_live(), require_programming_freshness=True)
        self.assertIsNotNone(telemetry)
        decision = SafetySupervisor().verify_programmed(self.REQUEST, telemetry)
        self.assertTrue(decision.allowed, decision.detail)
        self.assertEqual(telemetry.set_voltage_v, 14.4)
        self.assertEqual(telemetry.set_current_a, 2.0)

    def test_stale_canonical_readback_fails_closed_despite_legacy_values(self):
        self.assertIsNone(
            snapshot_from_live(_live(v2_age_s=30.0), require_programming_freshness=True)
        )

    def test_missing_canonical_readback_fails_closed_despite_legacy_values(self):
        self.assertIsNone(
            snapshot_from_live(_live(include_v2=False), require_programming_freshness=True)
        )

    def test_legacy_only_values_cannot_authorize_programmed_action(self):
        live = _live(include_v2=False)
        live["set_voltage"] = 14.4
        live["set_current"] = 2.0
        live["ovp"] = 14.5
        live["ocp"] = 2.1
        self.assertIsNone(snapshot_from_live(live, require_programming_freshness=True))


if __name__ == "__main__":
    unittest.main()
