from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from application.operator_snapshot_provider import OperatorSnapshotProvider
from application.operator_read_source import OperatorReadSource
from application.operator_snapshot import snapshot_from_mapping


class _Hass:
    def __init__(self, live):
        self.live = live

    async def get_all_live(self):
        return self.live


class _SequencedHass:
    def __init__(self, *values):
        self.values = list(values)
        self.reads = 0

    async def get_all_live(self):
        value = self.values[min(self.reads, len(self.values) - 1)]
        self.reads += 1
        return value


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


class _HandsOffManager:
    hands_off = True


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
    def test_snapshot_renderer_preserves_manual_authority_and_psu_temperature(self):
        snapshot = snapshot_from_mapping({
            "state": "CHARGING",
            "charge": {"stage": "Main Charge", "program": "manual", "phase": "CV", "waiting_for": "internal"},
            "telemetry": {"voltage": 13.55, "current": 1.46, "temperature": 23.0, "psu_temperature": 33.0},
            "output": {"enabled": True},
        })
        state = OperatorSnapshotProvider.hmi_state_from_snapshot(snapshot)
        self.assertEqual(state.authority.value, "manual")
        self.assertEqual(state.psu_temp_c, 33.0)
        self.assertEqual(state.progress, "")
    async def test_idle_snapshot_is_read_only_and_maps_actions(self):
        provider = OperatorSnapshotProvider(OperatorReadSource(_App(live())))
        snapshot = await provider.get_operator_snapshot()
        self.assertEqual(snapshot.state, "IDLE")
        self.assertIn("start_charge", snapshot.available_actions)
        self.assertFalse(hasattr(snapshot, "hass"))

    async def test_stale_telemetry_is_fault_and_start_is_removed(self):
        old = (datetime.now(timezone.utc) - timedelta(seconds=60)).isoformat()
        data = live(_meta={name: {"status": "ok", "last_reported": old} for name in ("switch", "battery_voltage", "current", "protection_code", "regulation_code")})
        snapshot = await OperatorSnapshotProvider(OperatorReadSource(_App(data))).get_operator_snapshot()
        self.assertEqual(snapshot.state, "FAULT")
        self.assertNotIn("start_charge", snapshot.available_actions)
        self.assertFalse(snapshot.telemetry_fresh)

    async def test_idle_actions_reuse_home_snapshot_across_telemetry_refresh_race(self):
        fresh = live()
        old = (datetime.now(timezone.utc) - timedelta(seconds=60)).isoformat()
        stale = live(_meta={name: {"status": "ok", "last_reported": old} for name in (
            "switch", "battery_voltage", "current", "protection_code", "regulation_code"
        )})
        app = _App(fresh)
        app.hass = _SequencedHass(fresh, stale)
        provider = OperatorSnapshotProvider(OperatorReadSource(app))

        snapshot = await provider.get_operator_snapshot()
        actions = await provider.get_operator_actions(snapshot=snapshot)

        self.assertEqual(snapshot.state, "IDLE")
        self.assertTrue(snapshot.snapshot.safety.allowed)
        self.assertIn("start_charge", {item.action.value for item in actions.available_actions})
        self.assertEqual(app.hass.reads, 1)

    async def test_hands_off_snapshot_preserves_exact_progress_and_does_not_reread(self):
        first = live()
        second = live(switch="on", battery_voltage=15.2, current=2.4)
        app = _App(first)
        app.rd_control_mode_manager = _HandsOffManager()
        app.hass = _SequencedHass(first, second)
        provider = OperatorSnapshotProvider(OperatorReadSource(app))

        snapshot = await provider.get_operator_snapshot()
        actions = await provider.get_operator_actions(snapshot=snapshot)
        state = provider.hmi_state_from_snapshot(snapshot)

        self.assertEqual(snapshot.state, "HANDS_OFF")
        self.assertEqual(state.process_state.value, "hands_off")
        self.assertEqual(state.progress, "RD свободен от Pb-автоматики")
        self.assertEqual(app.hass.reads, 1)
        callbacks = {item.action.value for item in actions.available_actions}
        self.assertEqual(callbacks, {"start_charge", "return_pb_control"})
        self.assertNotIn("stop_charge", callbacks)
        self.assertNotIn("disable_output", callbacks)

    async def test_idle_navigation_remains_visible_for_safety_denied_read_model(self):
        snapshot = snapshot_from_mapping({
            "state": "IDLE",
            "safety": {"allowed": False, "reason": "telemetry_stale"},
            "output": {"enabled": False},
            "charge": {"stage": "IDLE"},
        })
        provider = OperatorSnapshotProvider(OperatorReadSource(_App(live())))
        actions = await provider.get_operator_actions(snapshot=snapshot)
        self.assertIn("start_charge", {item.action.value for item in actions.available_actions})

    async def test_fault_mapping(self):
        snapshot = await OperatorSnapshotProvider(OperatorReadSource(_App(live(ovp_triggered="on")))).get_operator_snapshot()
        self.assertEqual(snapshot.state, "FAULT")
        self.assertIn("OVP", snapshot.faults)

    async def test_details_and_service_details_are_dtos(self):
        provider = OperatorSnapshotProvider(OperatorReadSource(_App(live())))
        details = await provider.get_operator_details()
        service = await provider.get_service_details()
        self.assertEqual(details.process_state, "idle")
        self.assertEqual(service.output_on, False)
        self.assertFalse(hasattr(details, "hass"))
        self.assertFalse(hasattr(service, "controller"))



if __name__ == "__main__":
    unittest.main()
