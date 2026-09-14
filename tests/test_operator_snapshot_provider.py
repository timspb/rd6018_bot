from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from application.operator_snapshot_provider import OperatorSnapshotProvider
from application.operator_snapshot_shadow import compare_hmi_to_snapshot


class _Hass:
    def __init__(self, live):
        self.live = live

    async def get_all_live(self):
        return self.live


class _Controller:
    is_active = False


class _App:
    charge_controller = _Controller()
    manual_session_manager = None
    rd_control_mode_manager = None
    rd_live_mix_observer = None

    def __init__(self, live):
        self.hass = _Hass(live)

    def _operator_pause_active(self):
        return False


def live(**overrides):
    value = {
        "switch": "off", "battery_voltage": 12.8, "current": 0.0,
        "power": 0.0, "temp_ext": 25.0, "temp_int": 30.0,
        "ovp_triggered": "off", "ocp_triggered": "off",
        "is_cc": "off", "is_cv": "off",
        "_freshness": {name: 0.0 for name in ("switch", "battery_voltage", "current", "protection_code", "regulation_code")},
    }
    value.update(overrides)
    return value


class OperatorSnapshotProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_idle_snapshot_is_read_only_and_maps_actions(self):
        provider = OperatorSnapshotProvider(_App(live()))
        snapshot = await provider.get_operator_snapshot()
        self.assertEqual(snapshot.state, "IDLE")
        self.assertIn("start_charge", snapshot.available_actions)
        self.assertFalse(hasattr(snapshot, "hass"))

    async def test_stale_telemetry_is_fault_and_start_is_removed(self):
        old = (datetime.now(timezone.utc) - timedelta(seconds=60)).isoformat()
        data = live(_meta={name: {"status": "ok", "last_reported": old} for name in ("switch", "battery_voltage", "current", "protection_code", "regulation_code")})
        snapshot = await OperatorSnapshotProvider(_App(data)).get_operator_snapshot()
        self.assertEqual(snapshot.state, "FAULT")
        self.assertNotIn("start_charge", snapshot.available_actions)
        self.assertFalse(snapshot.telemetry_fresh)

    async def test_fault_mapping(self):
        snapshot = await OperatorSnapshotProvider(_App(live(ovp_triggered="on"))).get_operator_snapshot()
        self.assertEqual(snapshot.state, "FAULT")
        self.assertIn("OVP", snapshot.faults)

    async def test_shadow_matches_legacy_hmi_for_idle(self):
        provider = OperatorSnapshotProvider(_App(live()))
        snapshot = await provider.get_operator_snapshot()
        hmi = provider.legacy_hmi_state(live())
        result = compare_hmi_to_snapshot(hmi, snapshot)
        self.assertEqual(result.status, "MATCH")


if __name__ == "__main__":
    unittest.main()
