"""P5-9G fake-only parity for adopted MIX observe timestamps and OFF ACKs."""

from __future__ import annotations

import asyncio
import json
import tempfile
import types
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

from pb_domain import BatteryChemistry
from rd_control_mode import RdControlMode
from rd_managed_adoption import ManagedAdoptionFingerprint
from rd_managed_mix import ManagedMixAdoptionCoordinator, ManagedMixState
from rd_live_adoption import MIX_FINISH_HOLD_S
from signal_analyzer import SignalEvent
from runtime.safety.output_policy import SafetyPolicy
from runtime.safety.runtime_guard import RuntimeSafetyError


class Clock:
    def __init__(self):
        self.wall = 2_000_000_000.0
        self.mono = 1_000.0

    def time(self):
        return self.wall

    def monotonic(self):
        return self.mono

    def advance(self, seconds):
        self.wall += float(seconds)
        self.mono += float(seconds)


class FakeHass:
    def __init__(self, clock):
        self.clock = clock
        self.live = {
            "switch": "on", "set_voltage": 16.50, "set_current": 1.00,
            "battery_voltage": 16.48, "current": 0.90, "temp_ext": 25.0,
            "regulation_code": 0, "is_cv": "on", "is_cc": "off",
        }
        self.read_calls = 0
        self.refresh_meta()

    def refresh_meta(self):
        stamp = datetime.fromtimestamp(self.clock.wall, tz=timezone.utc).isoformat()
        self.live["_meta"] = {
            key: {"last_reported": stamp, "last_updated": stamp}
            for key in ("current", "battery_voltage", "temp_ext", "regulation_code", "is_cv", "is_cc")
        }

    async def get_all_live(self):
        self.read_calls += 1
        return dict(self.live)


class FakeGuard:
    def __init__(self, app):
        self.app = app
        self.policy = SafetyPolicy()
        self._off_unconfirmed = False
        self._orphan_output_seen_at = None
        self.edge_safety_lease = None
        self.managed_read_calls = 0

    async def _raw_live(self):
        return dict(self.app.hass.live)

    async def get_all_live(self):
        self.managed_read_calls += 1
        return await self.app.hass.get_all_live()


class FakeManager:
    def __init__(self, guard):
        self.guard = guard
        self.mode = RdControlMode.PB_MANAGED
        self._transition_lock = asyncio.Lock()
        self._release_in_progress = False
        self.hands_off = False
        self.pb_managed = True
        self.off_results = []
        self.off_calls = []

    async def operator_output_off(self, entity_id=None):
        self.off_calls.append(entity_id)
        result = self.off_results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


class FakeFingerprintOwner:
    @staticmethod
    def fingerprint_from_live(live):
        try:
            return ManagedAdoptionFingerprint(float(live["set_voltage"]), float(live["set_current"]))
        except (KeyError, TypeError, ValueError):
            return None

    @staticmethod
    def _preflight_live(live, *, expected=None):
        return FakeFingerprintOwner.fingerprint_from_live(live)


class FakeLease:
    def __init__(self):
        self.calls = 0

    async def disarm(self):
        self.calls += 1


class AdoptedMixObserveOffTests(unittest.IsolatedAsyncioTestCase):
    def make_system(self, state_file):
        clock = Clock()
        app = types.SimpleNamespace()
        app.ENTITY_MAP = {"switch": "switch.rd_output"}
        app.hass = FakeHass(clock)
        app.charge_controller = types.SimpleNamespace(is_active=False)
        app.manual_session_manager = types.SimpleNamespace(is_active=False)
        app.rd_live_mix_observer = None
        guard = FakeGuard(app)
        manager = FakeManager(guard)
        d061 = types.SimpleNamespace(
            guard=guard, edge=None, active=False, off_pending=False,
            fingerprint_from_live=FakeFingerprintOwner.fingerprint_from_live,
            _preflight_live=FakeFingerprintOwner._preflight_live,
        )
        coordinator = ManagedMixAdoptionCoordinator(
            app, manager, d061, state_file=state_file,
            monotonic=clock.monotonic, wall_time=clock.time,
            history_reader=object(),
        )
        coordinator.state = ManagedMixState.ACTIVE
        coordinator.chemistry = BatteryChemistry.CA_CA
        coordinator.capacity_ah = 72.0
        coordinator.prior_elapsed_s = 0.0
        coordinator.adopted_active_elapsed_s = 0.0
        coordinator._active_anchor_mono = clock.mono
        coordinator.current_authority = ManagedAdoptionFingerprint(16.50, 1.00)
        coordinator.max_authority = coordinator.current_authority
        coordinator.last_source_timestamp_s = clock.wall
        coordinator._persist()
        coordinator.analyzer = types.SimpleNamespace(
            observe=Mock(return_value=types.SimpleNamespace(
                metrics=types.SimpleNamespace(
                    current_min_a=0.1, delta_current_from_min_a=0.8,
                    voltage_max_v=16.5, delta_voltage_from_max_v=0.0,
                ),
                events={SignalEvent.END_OF_CHARGE_LIKELY},
            )),
            reset_stage=Mock(),
        )
        return clock, app, guard, manager, coordinator

    @staticmethod
    def persisted(path):
        return json.loads(Path(path).read_text(encoding="utf-8"))

    async def test_stale_and_equal_source_timestamps_persist_without_analysis_or_new_hold(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = f"{tmp}/mix.json"
            clock, app, _guard, _manager, coordinator = self.make_system(path)
            for offset in (0, -1):
                stamp = datetime.fromtimestamp(clock.wall + offset, tz=timezone.utc).isoformat()
                for item in app.hass.live["_meta"].values():
                    item["last_reported"] = stamp
                await coordinator.observe_once()
                self.assertEqual(coordinator.state, ManagedMixState.ACTIVE)
                self.assertIsNone(coordinator.finish_hold_started_at_s)
                self.assertEqual(coordinator.analyzer.observe.call_count, 0)
                self.assertEqual(self.persisted(path)["state"], "active")
            self.assertEqual(_guard.managed_read_calls, 2)

    async def test_stale_timestamp_skips_measurement_parsing(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = f"{tmp}/mix.json"
            clock, app, _guard, _manager, coordinator = self.make_system(path)
            app.hass.live["battery_voltage"] = "malformed"
            with patch("rd_managed_mix.finite_float") as parse_number:
                await coordinator.observe_once()
            parse_number.assert_not_called()
            coordinator.analyzer.observe.assert_not_called()

    async def test_chemistry_hard_timeout_precedes_source_projection(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = f"{tmp}/mix.json"
            _clock, app, _guard, manager, coordinator = self.make_system(path)
            coordinator.prior_elapsed_s = coordinator.hard_limit_s + 2.0
            manager.hands_off = True
            manager.off_results = [False]
            with patch.object(
                coordinator, "_source_timestamp", side_effect=AssertionError("timestamp reached")
            ):
                await coordinator.observe_once()
            self.assertEqual(manager.off_calls, ["switch.rd_output"])
            self.assertEqual(coordinator.terminal_reason, "MIX_TIMEOUT")
            coordinator.analyzer.observe.assert_not_called()

    async def test_strictly_newer_coherent_timestamp_reaches_analyzer_once_and_starts_hold(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = f"{tmp}/mix.json"
            clock, app, _guard, _manager, coordinator = self.make_system(path)
            clock.advance(1)
            app.hass.refresh_meta()
            await coordinator.observe_once()
            coordinator.analyzer.observe.assert_called_once()
            sample = coordinator.analyzer.observe.call_args.args[0]
            self.assertEqual(sample.timestamp_s, clock.wall)
            self.assertEqual(coordinator.last_source_timestamp_s, clock.wall)
            self.assertEqual(coordinator.finish_hold_started_at_s, clock.wall)
            self.assertEqual(self.persisted(path)["finish_hold_started_at_s"], clock.wall)

    async def test_repeated_end_event_does_not_reset_hold_and_exact_boundary_requests_verified_off(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = f"{tmp}/mix.json"
            clock, app, _guard, manager, coordinator = self.make_system(path)
            manager.hands_off = True
            manager.off_results = [True]
            clock.advance(1)
            app.hass.refresh_meta()
            await coordinator.observe_once()
            initial_anchor = coordinator._finish_hold_anchor_mono
            initial_wall = coordinator.finish_hold_started_at_s

            clock.advance(1)
            app.hass.refresh_meta()
            await coordinator.observe_once()
            self.assertEqual(coordinator._finish_hold_anchor_mono, initial_anchor)
            self.assertEqual(coordinator.finish_hold_started_at_s, initial_wall)

            clock.mono = initial_anchor + MIX_FINISH_HOLD_S
            clock.advance(0)
            clock.wall += 1
            app.hass.refresh_meta()
            await coordinator.observe_once()
            self.assertEqual(manager.off_calls, ["switch.rd_output"])
            self.assertEqual(coordinator.state, ManagedMixState.COMPLETED)
            self.assertEqual(coordinator.terminal_reason, "DELTA_HOLD_COMPLETE")

    async def test_absent_hold_anchor_does_not_request_hold_completion_off(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = f"{tmp}/mix.json"
            clock, app, _guard, manager, coordinator = self.make_system(path)
            coordinator.analyzer.observe.return_value.events = set()
            clock.advance(1)
            app.hass.refresh_meta()
            await coordinator.observe_once()
            self.assertIsNone(coordinator._finish_hold_anchor_mono)
            self.assertIsNone(coordinator.finish_hold_started_at_s)
            self.assertEqual(manager.off_calls, [])
            self.assertEqual(coordinator.state, ManagedMixState.ACTIVE)

    async def test_exact_boundary_false_and_exception_off_stay_pending_and_retry(self):
        for first_result in (False, RuntimeError("synthetic OFF transport failure")):
            with self.subTest(first_result=first_result), tempfile.TemporaryDirectory() as tmp:
                path = f"{tmp}/mix.json"
                clock, app, _guard, manager, coordinator = self.make_system(path)
                manager.hands_off = True
                manager.off_results = [first_result, True]
                coordinator.finish_hold_started_at_s = clock.wall - 100.0
                coordinator._finish_hold_anchor_mono = clock.mono - MIX_FINISH_HOLD_S
                clock.advance(1)
                app.hass.refresh_meta()
                await coordinator.observe_once()
                self.assertEqual(coordinator.state, ManagedMixState.OFF_PENDING)
                self.assertEqual(coordinator.terminal_reason, "DELTA_HOLD_COMPLETE")
                if isinstance(first_result, Exception):
                    self.assertIn("RuntimeError: synthetic OFF transport failure", coordinator.last_status)
                await coordinator.observe_once()
                self.assertEqual(manager.off_calls, ["switch.rd_output", "switch.rd_output"])
                self.assertEqual(coordinator.state, ManagedMixState.FAILED)
                self.assertEqual(coordinator.terminal_reason, "DELTA_HOLD_COMPLETE")

    async def test_finish_hold_clock_error_propagates_with_existing_message(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = f"{tmp}/mix.json"
            clock, app, _guard, _manager, coordinator = self.make_system(path)
            coordinator._finish_hold_anchor_mono = clock.mono
            coordinator.finish_hold_started_at_s = clock.wall
            values = iter((clock.mono, float("nan")))
            coordinator._monotonic = lambda: next(values, float("nan"))
            clock.wall += 1
            app.hass.refresh_meta()
            with self.assertRaisesRegex(
                RuntimeSafetyError,
                "^MIX_ADOPTED finish-hold monotonic clock moved backwards$",
            ):
                await coordinator.observe_once()

    async def test_unknown_output_requests_exact_verified_off_reason_and_remains_pending_on_false_ack(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = f"{tmp}/mix.json"
            _clock, app, _guard, manager, coordinator = self.make_system(path)
            app.hass.live["switch"] = None
            manager.hands_off = True
            manager.off_results = [False]
            await coordinator.observe_once()
            self.assertEqual(manager.off_calls, ["switch.rd_output"])
            self.assertEqual(coordinator.state, ManagedMixState.OFF_PENDING)
            self.assertEqual(coordinator.terminal_reason, "MIX_ADOPTED_OUTPUT_UNKNOWN")
            self.assertIn("Output OFF unconfirmed", coordinator.last_status)
            saved = self.persisted(path)
            self.assertEqual(saved["state"], "off_pending")
            self.assertEqual(saved["terminal_reason"], "MIX_ADOPTED_OUTPUT_UNKNOWN")

    async def test_missing_program_readback_requests_verified_off_with_exact_reason(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = f"{tmp}/mix.json"
            _clock, app, _guard, manager, coordinator = self.make_system(path)
            app.hass.live["set_current"] = None
            manager.hands_off = True
            manager.off_results = [False]
            await coordinator.observe_once()
            self.assertEqual(manager.off_calls, ["switch.rd_output"])
            self.assertEqual(coordinator.state, ManagedMixState.OFF_PENDING)
            self.assertEqual(coordinator.terminal_reason, "MIX_ADOPTED_PROGRAM_READBACK_LOST")
            self.assertEqual(self.persisted(path)["terminal_reason"], "MIX_ADOPTED_PROGRAM_READBACK_LOST")

    async def test_off_exception_is_persisted_and_retried_on_next_observe(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = f"{tmp}/mix.json"
            _clock, app, _guard, manager, coordinator = self.make_system(path)
            app.hass.live["switch"] = "unknown"
            manager.hands_off = True
            manager.off_results = [RuntimeError("synthetic OFF transport failure"), True]
            await coordinator.observe_once()
            self.assertEqual(coordinator.state, ManagedMixState.OFF_PENDING)
            self.assertEqual(coordinator.terminal_reason, "MIX_ADOPTED_OUTPUT_UNKNOWN")
            self.assertIn("RuntimeError: synthetic OFF transport failure", coordinator.last_status)
            self.assertEqual(self.persisted(path)["state"], "off_pending")
            await coordinator.observe_once()
            self.assertEqual(manager.off_calls, ["switch.rd_output", "switch.rd_output"])
            self.assertEqual(coordinator.state, ManagedMixState.FAILED)
            self.assertEqual(coordinator.terminal_reason, "MIX_ADOPTED_OUTPUT_UNKNOWN")
            self.assertEqual(self.persisted(path)["state"], "failed")

    async def test_false_ack_remains_pending_and_each_observe_retries_without_idempotence_claim(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = f"{tmp}/mix.json"
            _clock, app, _guard, manager, coordinator = self.make_system(path)
            app.hass.live["switch"] = None
            manager.hands_off = True
            manager.off_results = [False, False]
            await coordinator.observe_once()
            first_status = coordinator.last_status
            await coordinator.observe_once()
            self.assertEqual(manager.off_calls, ["switch.rd_output", "switch.rd_output"])
            self.assertEqual(coordinator.state, ManagedMixState.OFF_PENDING)
            self.assertEqual(coordinator.terminal_reason, "MIX_ADOPTED_OUTPUT_UNKNOWN")
            self.assertNotEqual(first_status, "")
            self.assertEqual(self.persisted(path)["state"], "off_pending")

    async def test_external_confirmed_off_uses_completion_and_disarms_without_off_request(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = f"{tmp}/mix.json"
            _clock, app, guard, manager, coordinator = self.make_system(path)
            lease = FakeLease()
            guard.edge_safety_lease = lease
            app.hass.live["switch"] = "off"
            manager.hands_off = True
            await coordinator.observe_once()
            self.assertEqual(coordinator.state, ManagedMixState.COMPLETED)
            self.assertEqual(coordinator.terminal_reason, "OUTPUT_OFF_EXTERNAL")
            self.assertEqual(lease.calls, 1)
            self.assertEqual(manager.off_calls, [])
            self.assertEqual(self.persisted(path)["state"], "completed")


if __name__ == "__main__":
    unittest.main()
