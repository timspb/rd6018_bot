import asyncio
import json
import tempfile
import time
import unittest

from ha_history import ContinuousOnEvidence, MixHistoryEvidence
from pb_domain import BatteryChemistry
from rd_live_adoption import (
    HandsOffMixObserver,
    LiveMixObserverMode,
    LiveMixObserverState,
    LiveMixPreview,
)
from signal_analyzer import SignalAnalysis, SignalEvent, SignalMetrics


class FakeGuard:
    def __init__(self, live):
        self.live = dict(live)

    async def _raw_live(self):
        return dict(self.live)


class FakeManager:
    def __init__(self, live):
        self.hands_off = True
        self.guard = FakeGuard(live)
        self.off_calls = 0

    async def operator_output_off(self, entity_id=None):
        self.off_calls += 1
        self.guard.live["switch"] = "off"
        return True


class FakeApp:
    def __init__(self, manager):
        self.ENTITY_MAP = {"switch": "switch.rd"}
        self.notices = []
        self.manager = manager

    def _charge_notify(self, message, critical=False):
        self.notices.append((str(message), bool(critical)))


class AlwaysDeltaAnalyzer:
    def __init__(self):
        self.reset_calls = []
        self.observe_calls = []

    def reset_stage(self, stage_name, *, target_voltage_v=None):
        self.reset_calls.append((stage_name, target_voltage_v))

    def observe(self, sample):
        self.observe_calls.append(sample)
        metrics = SignalMetrics(
            d_voltage_v_per_min=0.0,
            d_current_a_per_min=0.01,
            d_temp_c_per_min=0.0,
            current_min_a=0.8,
            seconds_since_current_min=300.0,
            delta_current_from_min_a=0.3,
            reversal_threshold_a=0.24,
            current_plateau_span_a=0.02,
            current_plateau_center_a=1.0,
            reversal_confirmations=3,
        )
        return SignalAnalysis(
            sample=sample,
            metrics=metrics,
            events=frozenset({SignalEvent.END_OF_CHARGE_LIKELY}),
        )


def live_state(*, source_ts="2026-08-31T05:00:00+00:00", set_i=1.0):
    return {
        "switch": "on",
        "battery_voltage": 16.4,
        "voltage": 16.55,
        "current": 0.90,
        "temp_ext": 27.0,
        "set_voltage": 16.55,
        "set_current": set_i,
        "ovp": 16.75,
        "ocp": 1.20,
        "regulation_code": 1,
        "_meta": {
            "current": {"last_reported": source_ts},
            "battery_voltage": {"last_reported": source_ts},
            "temp_ext": {"last_reported": source_ts},
            "regulation_code": {"last_reported": source_ts},
        },
    }


def preview_from_live(live):
    fingerprint = HandsOffMixObserver.fingerprint_from_live(live)
    assert fingerprint is not None
    return LiveMixPreview(
        battery_id="Baic72",
        chemistry=BatteryChemistry.CA_CA,
        capacity_ah=72.0,
        fingerprint=fingerprint,
        history=MixHistoryEvidence(
            fetched_at_s=time.time(),
            output=ContinuousOnEvidence(True, time.time() - 3600.0, 3600.0, "test", 2),
        ),
    )


class LiveMixObserverTests(unittest.IsolatedAsyncioTestCase):
    async def test_start_is_hands_off_only_and_never_reprograms_rd(self):
        with tempfile.TemporaryDirectory() as tmp:
            live = live_state()
            manager = FakeManager(live)
            app = FakeApp(manager)
            observer = HandsOffMixObserver(
                app,
                manager,
                state_file=f"{tmp}/observer.json",
                poll_s=3600,
            )
            preview = preview_from_live(live)

            await observer.start(preview, mode=LiveMixObserverMode.OBSERVE_ONLY)
            self.assertTrue(observer.active)
            self.assertFalse(observer.actuator_authority)
            self.assertEqual(manager.off_calls, 0)
            self.assertEqual(manager.guard.live["set_voltage"], 16.55)
            self.assertEqual(manager.guard.live["set_current"], 1.0)
            await observer.cancel()

    async def test_toctou_setpoint_change_rejects_start_without_actuation(self):
        with tempfile.TemporaryDirectory() as tmp:
            live = live_state(set_i=1.0)
            manager = FakeManager(live)
            app = FakeApp(manager)
            observer = HandsOffMixObserver(
                app,
                manager,
                state_file=f"{tmp}/observer.json",
                poll_s=3600,
            )
            preview = preview_from_live(live)
            manager.guard.live["set_current"] = 1.5

            with self.assertRaisesRegex(RuntimeError, "setpoints changed"):
                await observer.start(preview, mode=LiveMixObserverMode.DELTA_THEN_OFF)

            self.assertFalse(observer.active)
            self.assertEqual(manager.off_calls, 0)

    async def test_history_is_context_only_and_fresh_delta_epoch_starts_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            live = live_state()
            manager = FakeManager(live)
            app = FakeApp(manager)
            observer = HandsOffMixObserver(
                app,
                manager,
                state_file=f"{tmp}/observer.json",
                poll_s=3600,
            )
            fake = AlwaysDeltaAnalyzer()
            observer.analyzer = fake

            await observer.start(preview_from_live(live), mode=LiveMixObserverMode.OBSERVE_ONLY)

            self.assertEqual(fake.reset_calls, [("Adopted Mix observer", 16.55)])
            self.assertIsNone(observer.finish_hold_started_at_s)
            await observer.cancel()

    async def test_duplicate_ha_source_report_does_not_accumulate_delta(self):
        with tempfile.TemporaryDirectory() as tmp:
            live = live_state(source_ts="2026-08-31T05:00:00+00:00")
            manager = FakeManager(live)
            app = FakeApp(manager)
            observer = HandsOffMixObserver(
                app,
                manager,
                state_file=f"{tmp}/observer.json",
                poll_s=3600,
            )
            fake = AlwaysDeltaAnalyzer()
            observer.analyzer = fake
            await observer.start(preview_from_live(live), mode=LiveMixObserverMode.OBSERVE_ONLY)

            await observer.observe_once()
            await observer.observe_once()

            self.assertEqual(len(fake.observe_calls), 1)
            await observer.cancel()

    async def test_external_setpoint_change_resets_delta_epoch_instead_of_accepting_old_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            live = live_state(source_ts="2026-08-31T05:00:00+00:00")
            manager = FakeManager(live)
            app = FakeApp(manager)
            observer = HandsOffMixObserver(
                app,
                manager,
                state_file=f"{tmp}/observer.json",
                poll_s=3600,
            )
            fake = AlwaysDeltaAnalyzer()
            observer.analyzer = fake
            await observer.start(preview_from_live(live), mode=LiveMixObserverMode.OBSERVE_ONLY)
            await observer.observe_once()
            first_hold = observer.finish_hold_started_at_s
            self.assertIsNotNone(first_hold)

            manager.guard.live["set_current"] = 0.8
            manager.guard.live["_meta"] = {
                key: {"last_reported": "2026-08-31T05:01:00+00:00"}
                for key in ("current", "battery_voltage", "temp_ext", "regulation_code")
            }
            await observer.observe_once()

            self.assertGreaterEqual(len(fake.reset_calls), 2)
            self.assertIsNotNone(observer.finish_hold_started_at_s)
            self.assertGreaterEqual(observer.finish_hold_started_at_s, first_hold)
            await observer.cancel()

    async def test_delta_then_off_has_only_verified_off_authority(self):
        with tempfile.TemporaryDirectory() as tmp:
            live = live_state(source_ts="2026-08-31T05:00:00+00:00")
            manager = FakeManager(live)
            app = FakeApp(manager)
            observer = HandsOffMixObserver(
                app,
                manager,
                state_file=f"{tmp}/observer.json",
                poll_s=3600,
            )
            observer.analyzer = AlwaysDeltaAnalyzer()
            await observer.start(preview_from_live(live), mode=LiveMixObserverMode.DELTA_THEN_OFF)

            await observer.observe_once()
            self.assertIsNotNone(observer.finish_hold_started_at_s)
            self.assertEqual(manager.off_calls, 0)

            observer.finish_hold_started_at_s = time.time() - 2 * 3600.0 - 1.0
            manager.guard.live["_meta"] = {
                key: {"last_reported": "2026-08-31T05:01:00+00:00"}
                for key in ("current", "battery_voltage", "temp_ext", "regulation_code")
            }
            await observer.observe_once()

            self.assertEqual(manager.off_calls, 1)
            self.assertEqual(observer.state, LiveMixObserverState.COMPLETED)
            self.assertEqual(manager.guard.live["switch"], "off")
            self.assertEqual(manager.guard.live["set_voltage"], 16.55)
            self.assertEqual(manager.guard.live["set_current"], 1.0)

    async def test_process_restart_never_resumes_future_off_authority(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_file = f"{tmp}/observer.json"
            live = live_state()
            manager = FakeManager(live)
            app = FakeApp(manager)
            observer = HandsOffMixObserver(app, manager, state_file=state_file, poll_s=3600)
            await observer.start(preview_from_live(live), mode=LiveMixObserverMode.DELTA_THEN_OFF)
            task = observer._task
            if task is not None:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

            restored = HandsOffMixObserver(app, manager, state_file=state_file, poll_s=3600)
            self.assertEqual(restored.state, LiveMixObserverState.INTERRUPTED)
            self.assertFalse(restored.active)
            self.assertFalse(restored.actuator_authority)
            self.assertEqual(manager.off_calls, 0)

            with open(state_file, "r", encoding="utf-8") as handle:
                self.assertEqual(json.load(handle)["state"], "interrupted")


if __name__ == "__main__":
    unittest.main()
