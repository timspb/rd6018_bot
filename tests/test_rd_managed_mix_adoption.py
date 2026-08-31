import asyncio
import tempfile
import types
import unittest
from datetime import datetime, timezone

from ha_history import ContinuousOnEvidence, MixHistoryEvidence
from pb_domain import BatteryChemistry
from rd_control_mode import RdControlMode
from rd_managed_adoption import ManagedAdoptionFingerprint, ManagedLiveAdoptionCoordinator
from rd_managed_mix_adoption import (
    ManagedMixAdoptionCoordinator,
    ManagedMixPreview,
    ManagedMixState,
    PriorMixAge,
    PriorMixAgeSource,
    resolve_prior_mix_age,
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
            "temp_int": 30.0,
            "protection_code": 0,
            "regulation_code": 0,
            "is_cv": "on",
            "is_cc": "off",
        }
        self.turn_on_calls = 0
        self.turn_off_calls = 0
        self.writes = []
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

    async def turn_on(self, entity_id=None):
        self.turn_on_calls += 1
        self.live["switch"] = "on"
        return True

    async def turn_off(self, entity_id=None):
        self.turn_off_calls += 1
        self.live["switch"] = "off"
        return True

    async def set_voltage(self, value):
        self.writes.append(("voltage", float(value)))
        self.live["set_voltage"] = float(value)
        return True

    async def set_current(self, value):
        self.writes.append(("current", float(value)))
        self.live["set_current"] = float(value)
        return True

    async def set_ovp(self, value):
        self.writes.append(("ovp", float(value)))
        self.live["ovp"] = float(value)
        return True

    async def set_ocp(self, value):
        self.writes.append(("ocp", float(value)))
        self.live["ocp"] = float(value)
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

    def _critical_telemetry_error(self, live, *, require_programming):
        return None

    def _runtime_freshness_error(self, live, *, output_state):
        return None


class FakeManager:
    def __init__(self, app, guard):
        self.app = app
        self.guard = guard
        self.mode = RdControlMode.HANDS_OFF
        self._transition_lock = asyncio.Lock()
        self._release_in_progress = False
        self.write_mode_calls = []

    @property
    def hands_off(self):
        return self.mode is RdControlMode.HANDS_OFF

    @property
    def pb_managed(self):
        return self.mode is RdControlMode.PB_MANAGED

    def _clear_stale_auto_restore_authority(self):
        pass

    def _write_mode(self, mode):
        self.write_mode_calls.append(mode)

    async def operator_output_off(self, entity_id=None):
        return await self.app.hass.turn_off(entity_id)


class FakeEdgeState:
    generation = 17


class FakeEdge:
    def __init__(self):
        self.prepare_calls = 0
        self.adopt_calls = 0
        self.command_may_have_executed = False

    async def prepare(self):
        self.prepare_calls += 1
        self.command_may_have_executed = False
        return FakeEdgeState()

    async def adopt(self, *, expected_generation=None):
        self.adopt_calls += 1
        self.command_may_have_executed = True
        return types.SimpleNamespace(generation=18, armed=True)


class FakeHistoryReader:
    def __init__(self, history):
        self.history = history
        self.calls = 0

    async def read_mix_evidence(self, *, live=None, lookback_s=None):
        self.calls += 1
        return self.history


def history(clock, elapsed_s, *, reliable=True):
    return MixHistoryEvidence(
        fetched_at_s=clock.wall,
        output=ContinuousOnEvidence(
            reliable=bool(reliable),
            started_at_s=clock.wall - float(elapsed_s) if reliable else None,
            elapsed_s=float(elapsed_s) if reliable else None,
            reason="explicit OFF->ON" if reliable else "window starts ON",
        ),
    )


class ManagedMixAdoptionTests(unittest.IsolatedAsyncioTestCase):
    def make_system(self, state_file, *, prior_s=3600.0, reliable=True):
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
        d061 = types.SimpleNamespace(
            guard=guard,
            edge=edge,
            active=False,
            off_pending=False,
        )
        d061.fingerprint_from_live = ManagedLiveAdoptionCoordinator.fingerprint_from_live
        d061.fingerprint_matches = ManagedLiveAdoptionCoordinator.fingerprint_matches
        d061._preflight_live = types.MethodType(
            ManagedLiveAdoptionCoordinator._preflight_live,
            d061,
        )
        reader = FakeHistoryReader(history(clock, prior_s, reliable=reliable))
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
    def preview(clock, *, prior_s=3600.0, source=PriorMixAgeSource.RECORDER):
        return ManagedMixPreview(
            token="mix-preview",
            battery_id="Baic72",
            chemistry=BatteryChemistry.CA_CA,
            capacity_ah=72.0,
            fingerprint=ManagedAdoptionFingerprint(16.50, 1.00, 16.70, 1.20),
            prior_age=PriorMixAge(float(prior_s), source, clock.wall),
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

    def test_unknown_prior_age_cannot_create_fresh_budget(self):
        clock = Clock()
        with self.assertRaisesRegex(RuntimeSafetyError, "prior external Mix age is not proven"):
            resolve_prior_mix_age(history(clock, 0, reliable=False), now_s=clock.wall)

    def test_explicit_declared_age_is_authoritative_when_recorder_unknown(self):
        clock = Clock()
        age = resolve_prior_mix_age(
            history(clock, 0, reliable=False),
            declared_elapsed_s=2.5 * 3600,
            declared_at_s=clock.wall,
            now_s=clock.wall,
        )
        self.assertEqual(age.source, PriorMixAgeSource.OPERATOR_DECLARED)
        self.assertAlmostEqual(age.elapsed_s, 2.5 * 3600)

    def test_operator_declaration_can_only_conservatively_extend_recorder_age(self):
        clock = Clock()
        age = resolve_prior_mix_age(
            history(clock, 5 * 3600),
            declared_elapsed_s=7 * 3600,
            declared_at_s=clock.wall,
            now_s=clock.wall,
        )
        self.assertEqual(age.source, PriorMixAgeSource.OPERATOR_DECLARED)
        self.assertAlmostEqual(age.elapsed_s, 7 * 3600)

    async def test_successful_takeover_changes_ownership_without_actuator_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            clock, app, manager, edge, coordinator, _reader = self.make_system(
                f"{tmp}/mix.json", prior_s=3 * 3600
            )
            ok = await coordinator.adopt(self.preview(clock, prior_s=3 * 3600))
            self.assertTrue(ok)
            self.assertTrue(coordinator.active)
            self.assertTrue(manager.pb_managed)
            self.assertEqual(edge.prepare_calls, 1)
            self.assertEqual(edge.adopt_calls, 1)
            self.assertEqual(app.hass.turn_on_calls, 0)
            self.assertEqual(app.hass.turn_off_calls, 0)
            self.assertEqual(app.hass.writes, [])
            self.assertAlmostEqual(coordinator.prior_elapsed_s, 3 * 3600)
            await self.cleanup(coordinator)

    async def test_budget_already_exhausted_is_read_only_reject_before_edge(self):
        with tempfile.TemporaryDirectory() as tmp:
            clock, app, manager, edge, coordinator, _reader = self.make_system(
                f"{tmp}/mix.json", prior_s=20 * 3600
            )
            with self.assertRaisesRegex(RuntimeSafetyError, "already exhausts"):
                await coordinator.adopt(self.preview(clock, prior_s=20 * 3600))
            self.assertTrue(manager.hands_off)
            self.assertEqual(edge.prepare_calls, 0)
            self.assertEqual(edge.adopt_calls, 0)
            self.assertEqual(app.hass.turn_off_calls, 0)
            self.assertEqual(app.hass.writes, [])

    async def test_normal_stage_voltage_is_not_misclassified_as_adopted_mix(self):
        with tempfile.TemporaryDirectory() as tmp:
            clock, app, manager, edge, coordinator, _reader = self.make_system(f"{tmp}/mix.json")
            app.hass.live["set_voltage"] = 14.70
            app.hass.live["voltage"] = 14.68
            preview = ManagedMixPreview(
                token="x",
                battery_id="Baic72",
                chemistry=BatteryChemistry.CA_CA,
                capacity_ah=72.0,
                fingerprint=ManagedAdoptionFingerprint(14.70, 1.00, 16.70, 1.20),
                prior_age=PriorMixAge(3600, PriorMixAgeSource.RECORDER, clock.wall),
            )
            with self.assertRaisesRegex(RuntimeSafetyError, "high-voltage Mix"):
                await coordinator.adopt(preview)
            self.assertEqual(edge.prepare_calls, 0)
            self.assertEqual(app.hass.turn_off_calls, 0)

    async def test_chemistry_hv_current_envelope_is_enforced_before_edge(self):
        with tempfile.TemporaryDirectory() as tmp:
            clock, app, manager, edge, coordinator, _reader = self.make_system(f"{tmp}/mix.json")
            app.hass.live.update(set_current=2.50, ocp=2.70, current=2.0)
            preview = ManagedMixPreview(
                token="x",
                battery_id="Baic72",
                chemistry=BatteryChemistry.CA_CA,
                capacity_ah=72.0,
                fingerprint=ManagedAdoptionFingerprint(16.50, 2.50, 16.70, 2.70),
                prior_age=PriorMixAge(3600, PriorMixAgeSource.RECORDER, clock.wall),
            )
            with self.assertRaisesRegex(RuntimeSafetyError, "chemistry HV envelope"):
                await coordinator.adopt(preview)
            self.assertEqual(edge.prepare_calls, 0)
            self.assertEqual(app.hass.turn_off_calls, 0)

    async def test_prior_plus_post_adoption_active_time_hits_mix_timeout(self):
        with tempfile.TemporaryDirectory() as tmp:
            prior = 20 * 3600 - 10
            clock, app, _manager, _edge, coordinator, _reader = self.make_system(
                f"{tmp}/mix.json", prior_s=prior
            )
            await coordinator.adopt(self.preview(clock, prior_s=prior))
            clock.advance(11)
            app.hass.refresh_meta()
            await coordinator.observe_once()
            self.assertEqual(coordinator.state, ManagedMixState.FAILED)
            self.assertEqual(coordinator.terminal_reason, "MIX_TIMEOUT")
            self.assertEqual(app.hass.turn_off_calls, 1)
            self.assertEqual(app.hass.live["switch"], "off")
            await self.cleanup(coordinator)

    async def test_hold_started_before_budget_boundary_can_finish_after_boundary(self):
        with tempfile.TemporaryDirectory() as tmp:
            prior = 20 * 3600 - 10
            clock, app, _manager, _edge, coordinator, _reader = self.make_system(
                f"{tmp}/mix.json", prior_s=prior
            )
            await coordinator.adopt(self.preview(clock, prior_s=prior))
            coordinator.finish_hold_started_at_s = clock.wall
            coordinator._finish_hold_anchor_mono = clock.mono
            clock.advance(11)
            app.hass.refresh_meta()
            await coordinator.observe_once()
            self.assertTrue(coordinator.active)
            self.assertEqual(app.hass.turn_off_calls, 0)

            clock.advance(2 * 3600)
            app.hass.refresh_meta()
            await coordinator.observe_once()
            self.assertEqual(coordinator.state, ManagedMixState.COMPLETED)
            self.assertEqual(coordinator.terminal_reason, "DELTA_HOLD_COMPLETE")
            self.assertEqual(app.hass.turn_off_calls, 1)
            await self.cleanup(coordinator)

    async def test_out_of_band_increase_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            clock, app, _manager, _edge, coordinator, _reader = self.make_system(f"{tmp}/mix.json")
            await coordinator.adopt(self.preview(clock))
            app.hass.live["set_current"] = 1.20
            clock.advance(5)
            app.hass.refresh_meta()
            await coordinator.observe_once()
            self.assertEqual(coordinator.state, ManagedMixState.FAILED)
            self.assertIn("OUT_OF_BAND_INCREASE", coordinator.terminal_reason)
            self.assertEqual(app.hass.turn_off_calls, 1)
            await self.cleanup(coordinator)

    async def test_restart_never_resumes_managed_mix_authority(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = f"{tmp}/mix.json"
            clock, app, manager, _edge, coordinator, reader = self.make_system(path)
            await coordinator.adopt(self.preview(clock))
            await self.cleanup(coordinator)

            restored = ManagedMixAdoptionCoordinator(
                app,
                manager,
                coordinator.d061,
                state_file=path,
                monotonic=clock.monotonic,
                wall_time=clock.time,
                history_reader=reader,
            )
            self.assertTrue(restored.off_pending)
            ok = await restored.recover_startup()
            self.assertTrue(ok)
            self.assertEqual(restored.state, ManagedMixState.INTERRUPTED)
            self.assertEqual(app.hass.live["switch"], "off")


if __name__ == "__main__":
    unittest.main()
