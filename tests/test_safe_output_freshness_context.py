import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from safe_output import (
    OutputRequest,
    SafeOutputCoordinator,
    SafetySupervisor,
    snapshot_from_live,
)


NOW = datetime(2026, 8, 30, 14, 33, 10, tzinfo=timezone.utc)
FRESH = "2026-08-30T14:33:05+00:00"
STALE = "2026-01-01T00:00:00+00:00"


def _meta(ts):
    return {"status": "ok", "last_reported": ts, "last_updated": ts}


def _live(*, output_on=False, programmed_ts=STALE, voltage_ts=FRESH):
    live = {
        "battery_voltage": 12.6,
        "voltage": 0.0 if not output_on else 14.4,
        "current": 0.0 if not output_on else 2.0,
        "temp_ext": 25.0,
        "temp_int": 30.0,
        "switch": 1 if output_on else 0,
        "protection_code": 0,
        "set_voltage": 14.4,
        "set_current": 2.0,
        "ovp": 14.5,
        "ocp": 2.1,
        "_meta": {
            "battery_voltage": _meta(FRESH),
            "voltage": _meta(voltage_ts),
            "current": _meta(FRESH),
            "temp_ext": _meta(FRESH),
            "temp_int": _meta(FRESH),
            "switch": _meta(FRESH),
            "protection_code": _meta(FRESH),
            "set_voltage": _meta(programmed_ts),
            "set_current": _meta(programmed_ts),
            "ovp": _meta(programmed_ts),
            "ocp": _meta(programmed_ts),
        },
    }
    return live


class _Adapter:
    def __init__(self, snapshots):
        self.snapshots = list(snapshots)
        self.index = 0
        self.off_calls = 0
        self.on_calls = 0

    async def get_all_live(self):
        idx = min(self.index, len(self.snapshots) - 1)
        self.index += 1
        return self.snapshots[idx]

    async def set_ovp(self, _value):
        return True

    async def set_ocp(self, _value):
        return True

    async def set_voltage(self, _value):
        return True

    async def set_current(self, _value):
        return True

    async def turn_on(self, _entity_id=None):
        self.on_calls += 1
        return True

    async def turn_off(self, _entity_id=None):
        self.off_calls += 1
        return True


class SafeOutputFreshnessContextTests(unittest.IsolatedAsyncioTestCase):
    def test_preflight_ignores_old_static_setpoint_heartbeat(self):
        with self.subTest("preflight"):
            with patch("rd6018_telemetry.time.time", return_value=NOW.timestamp()):
                snapshot = snapshot_from_live(
                    _live(output_on=False, programmed_ts=STALE),
                    require_programming_freshness=False,
                )
            self.assertIsNotNone(snapshot)

        with self.subTest("programmed readback"):
            with patch("rd6018_telemetry.time.time", return_value=NOW.timestamp()):
                snapshot = snapshot_from_live(
                    _live(output_on=False, programmed_ts=STALE),
                    require_programming_freshness=True,
                )
            self.assertIsNone(snapshot)

    def test_stale_vout_is_ignored_while_off_but_rejected_when_on(self):
        with self.subTest("output off"):
            with patch("rd6018_telemetry.time.time", return_value=NOW.timestamp()):
                snapshot = snapshot_from_live(
                    _live(output_on=False, programmed_ts=FRESH, voltage_ts=STALE),
                    require_programming_freshness=True,
                )
            self.assertIsNotNone(snapshot)

        with self.subTest("output on"):
            with patch("rd6018_telemetry.time.time", return_value=NOW.timestamp()):
                snapshot = snapshot_from_live(
                    _live(output_on=True, programmed_ts=FRESH, voltage_ts=STALE),
                    require_programming_freshness=True,
                )
            self.assertIsNone(snapshot)

    async def test_coordinator_allows_stale_idle_setpoints_then_requires_fresh_readback(self):
        adapter = _Adapter(
            [
                _live(output_on=False, programmed_ts=STALE, voltage_ts=STALE),
                _live(output_on=False, programmed_ts=FRESH, voltage_ts=STALE),
                _live(output_on=True, programmed_ts=FRESH, voltage_ts=FRESH),
            ]
        )
        coordinator = SafeOutputCoordinator(adapter, SafetySupervisor(), readback_timeout_s=0.0)
        request = OutputRequest(14.4, 2.0, 14.5, 2.1, 14.4)

        with patch("rd6018_telemetry.time.time", return_value=NOW.timestamp()):
            result = await coordinator.enable(request)

        self.assertTrue(result.enabled, result.detail)
        self.assertEqual(adapter.on_calls, 1)
        self.assertEqual(adapter.off_calls, 0)

    async def test_coordinator_rejects_stale_programmed_readback_before_output_on(self):
        adapter = _Adapter(
            [
                _live(output_on=False, programmed_ts=STALE),
                _live(output_on=False, programmed_ts=STALE),
            ]
        )
        coordinator = SafeOutputCoordinator(adapter, SafetySupervisor(), readback_timeout_s=0.0)
        request = OutputRequest(14.4, 2.0, 14.5, 2.1, 14.4)

        with patch("rd6018_telemetry.time.time", return_value=NOW.timestamp()):
            result = await coordinator.enable(request)

        self.assertFalse(result.enabled)
        self.assertEqual(adapter.on_calls, 0)
        self.assertEqual(adapter.off_calls, 1)


if __name__ == "__main__":
    unittest.main()
