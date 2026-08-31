import asyncio
import tempfile
import types
import unittest
from datetime import datetime, timezone

from ha_history import ContinuousOnEvidence, HomeAssistantHistoryError, MixHistoryEvidence
from pb_domain import BatteryChemistry
from rd_control_mode import RdControlMode
from rd_managed_adoption import ManagedAdoptionFingerprint
from rd_managed_mix import (
    ManagedMixAdoptionCoordinator,
    ManagedMixPreview,
    ManagedMixState,
    PriorMixAge,
    PriorMixAgeSource,
)
from runtime_safety import RuntimeSafetyError
from safe_output import SafetyPolicy


class Clock:
    def __init__(self, wall=2_000_000_000.0, mono=1000.0):
        self.wall = float(wall)
        self.mono = float(mono)

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
        self.turn_off_calls = 0
        self.live = {
            "switch": "on",
            "set_voltage": 16.50,
            "set_current": 1.00,
            "ovp": 16.70,
            "ocp": 1.20,
            "voltage": 16.48,
            "current": 0.90,
            "battery_voltage": 16.48,
            "temp_ext": 25.0,
            "regulation_code": 0,
            "is_cv": "on",
            "is_cc": "off",
        }
        self.refresh_meta()

    def refresh_meta(self):
        stamp = datetime.fromtimestamp(self.clock.wall, tz=timezone.utc).isoformat()
        self.live["_meta"] = {
            key: {"last_reported": stamp, "last_updated": stamp}
            for key in (
                "current",
                "battery_voltage",
                "temp_ext",
                "regulation_code",
                "is_cv",
                "is_cc",
            )
        }

    async def get_all_live(self):
        return dict(self.live)

    async def turn_off(self, entity_id=None):
        self.turn_off_calls += 1
        self.live["switch"] = "off"
        return True


class FakeGuard:
    def __init__(self, app):
        self.app = app
        self.policy = SafetyPolicy()
        self._off_unconfirmed = False
        self._orphan_output_seen_at = None
        self.edge_safety_lease = None

    async def _raw_live(self):
        return dict(self.app.hass.live)


class FakeManager:
    def __init__(self, app, guard):
        self.app = app
        self.guard = guard
        self.mode = RdControlMode.HANDS_OFF
        self._transition_lock = asyncio.Lock()
        self._release_in_progress = False

    @property
    def hands_off(self):
        return self.mode is RdControlMode.HANDS_OFF

    @property
    def pb_managed(self):
        return self.mode is RdControlMode.PB_MANAGED

    def _clear_stale_auto_restore_authority(self):
        pass

    def _write_mode(self, mode):
        pass

    async def operator_output_off(self, entity_id=None):
        return await self.app.hass.turn_off(entity_id)


class FakeEdge:
    def __init__(self):
        self.command_may_have_executed = False
        self.prepare_calls = 0
        self.adopt_calls = 0
        self.prepare_error = None
        self.adopt_error = None
        self.adopt_uncertain = True

    async def prepare(self):
        self.prepare_calls += 1
        if self.prepare_error is not None:
            raise self.prepare_error
        self.command_may_have_executed = False
        return types.SimpleNamespace(generation=17)

    async def adopt(self, *, expected_generation=None):
        self.adopt_calls += 1
        self.command_may_have_executed = bool(self.adopt_uncertain)
        if self.adopt_error is not None:
            raise self.adopt_error
        return types.SimpleNamespace(generation=18, armed=True)


class FakeD061:
    def __init__(self, guard, edge):
        self.guard = guard
        self.edge = edge
        self.active = False
        self.off_pending = False

    @staticmethod
    def fingerprint_from_live(live):
        try:
            return ManagedAdoptionFingerprint(
                float(live["set_voltage"]),
                float(live["set_current"]),
                float(live["ovp"]),
                float(live["ocp"]),
            )
        except (KeyError, TypeError, ValueError):
            return None

    def _preflight_live(self, live, *, expected=None):
        if str(live.get("switch")).lower() != "on":
            raise RuntimeSafetyError("synthetic D061 preflight requires Output ON")
        fingerprint = self.fingerprint_from_live(live)
        if fingerprint is None:
            raise RuntimeSafetyError("synthetic D061 fingerprint unavailable")
        if expected is not None and fingerprint != expected:
            raise RuntimeSafetyError("live RD setpoints changed during adoption")
        return fingerprint


class FakeHistoryReader:
    def __init__(self, history=None, error=None):
        self.history = history
        self.error = error

    async def read_mix_evidence(self, *, live=None, lookback_s=None):
        if self.error is not None:
            raise self.error
        return self.history


def history(clock, elapsed_s):
    return MixHistoryEvidence(
        fetched_at_s=clock.wall,
        output=ContinuousOnEvidence(
            reliable=True,
            started_at_s=clock.wall - float(elapsed_s),
            elapsed_s=float(elapsed_s),
            reason="explicit OFF->ON",
        ),
    )


class ManagedMixHardeningTests(unittest.IsolatedAsyncioTestCase):
    def make_system(self, state_file, *, recorder_age_s=2 * 3600):
        clock = Clock()
        app = types.SimpleNamespace()
        app.ENTITY_MAP = {"switch": "switch.rd_output"}
        app.hass = FakeHass(clock)
        app.charge_controller = types.SimpleNamespace(is_active=False)
        app.manual_session_manager = types.SimpleNamespace(is_active=False)
        app.rd_live_mix_observer = None
        app._charge_notify = lambda *args, **kwargs: None
        guard = FakeGuard(app)
        manager = FakeManager(app, guard)
        edge = FakeEdge()
        d061 = FakeD061(guard, edge)
        reader = FakeHistoryReader(history(clock, recorder_age_s))
        coordinator = ManagedMixAdoptionCoordinator(
            app,
            manager,
            d061,
            state_file=state_file,
            poll_s=60.0,
            monotonic=clock.monotonic,
            wall_time=clock.time,
            history_reader=reader,
        )
        app.rd_managed_mix_adoption = coordinator
        return clock, app, manager, edge, coordinator, reader

    @staticmethod
    def preview(clock, prior_s=8 * 3600):
        return ManagedMixPreview(
            token="hardening-preview",
            battery_id="Baic72",
            chemistry=BatteryChemistry.CA_CA,
            capacity_ah=72.0,
            fingerprint=ManagedAdoptionFingerprint(16.50, 1.00, 16.70, 1.20),
            prior_age=PriorMixAge(
                float(prior_s),
                PriorMixAgeSource.RECORDER,
                clock.wall,
            ),
        )

    async def cleanup(self, coordinator):
        task = coordinator._task
        coordinator._task = None
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    async def test_fresh_recorder_snapshot_cannot_shrink_preview_age_floor(self):
        with tempfile.TemporaryDirectory() as tmp:
            clock, app, _manager, _edge, coordinator, _reader = self.make_system(
                f"{tmp}/mix.json", recorder_age_s=2 * 3600
            )
            preview = self.preview(clock, prior_s=8 * 3600)
            clock.advance(30 * 60)
            app.hass.refresh_meta()

            age = await coordinator._fresh_prior_age(preview, app.hass.live)

            self.assertEqual(age.source, PriorMixAgeSource.RECORDER)
            self.assertAlmostEqual(age.elapsed_s, 8.5 * 3600)

    async def test_recorder_error_preserves_and_ages_preview_floor(self):
        with tempfile.TemporaryDirectory() as tmp:
            clock, app, _manager, _edge, coordinator, reader = self.make_system(
                f"{tmp}/mix.json"
            )
            preview = self.preview(clock, prior_s=7 * 3600)
            reader.error = HomeAssistantHistoryError("synthetic recorder outage")
            clock.advance(15 * 60)
            app.hass.refresh_meta()

            age = await coordinator._fresh_prior_age(preview, app.hass.live)

            self.assertAlmostEqual(age.elapsed_s, 7.25 * 3600)

    async def test_stale_edge_uncertainty_before_prepare_failure_is_non_actuating(self):
        with tempfile.TemporaryDirectory() as tmp:
            clock, app, manager, edge, coordinator, _reader = self.make_system(
                f"{tmp}/mix.json", recorder_age_s=3 * 3600
            )
            edge.command_may_have_executed = True
            edge.prepare_error = RuntimeSafetyError("synthetic read-only prepare failure")

            with self.assertRaisesRegex(RuntimeSafetyError, "read-only prepare failure"):
                await coordinator.adopt(self.preview(clock, prior_s=3 * 3600))

            self.assertTrue(manager.hands_off)
            self.assertEqual(edge.adopt_calls, 0)
            self.assertEqual(app.hass.turn_off_calls, 0)
            self.assertEqual(app.hass.live["switch"], "on")
            self.assertEqual(coordinator.state, ManagedMixState.FAILED)

    async def test_edge_precommand_reject_with_false_uncertainty_is_non_actuating(self):
        with tempfile.TemporaryDirectory() as tmp:
            clock, app, manager, edge, coordinator, _reader = self.make_system(
                f"{tmp}/mix.json", recorder_age_s=3 * 3600
            )
            edge.adopt_uncertain = False
            edge.adopt_error = RuntimeSafetyError("synthetic pre-command edge race")

            with self.assertRaisesRegex(RuntimeSafetyError, "pre-command edge race"):
                await coordinator.adopt(self.preview(clock, prior_s=3 * 3600))

            self.assertTrue(manager.hands_off)
            self.assertEqual(edge.prepare_calls, 1)
            self.assertEqual(edge.adopt_calls, 1)
            self.assertEqual(app.hass.turn_off_calls, 0)
            self.assertEqual(app.hass.live["switch"], "on")

    async def test_ambiguous_edge_failure_forces_verified_off(self):
        with tempfile.TemporaryDirectory() as tmp:
            clock, app, manager, edge, coordinator, _reader = self.make_system(
                f"{tmp}/mix.json", recorder_age_s=3 * 3600
            )
            edge.adopt_uncertain = True
            edge.adopt_error = RuntimeSafetyError("synthetic lost ACK")

            with self.assertRaisesRegex(RuntimeSafetyError, "lost ACK"):
                await coordinator.adopt(self.preview(clock, prior_s=3 * 3600))

            self.assertTrue(manager.hands_off)
            self.assertEqual(edge.adopt_calls, 1)
            self.assertEqual(app.hass.turn_off_calls, 1)
            self.assertEqual(app.hass.live["switch"], "off")
            self.assertEqual(coordinator.state, ManagedMixState.FAILED)
            self.assertIn("INCOMPLETE_AFTER_EDGE", coordinator.terminal_reason)


if __name__ == "__main__":
    unittest.main()
