import asyncio
import tempfile
import types
import unittest

from manual_mode import ManualChargeRequest, ManualSessionState
from pb_domain import BatteryChemistry
from rd_control_mode import RdControlMode
from rd_managed_adoption import (
    ManagedAdoptionFingerprint,
    ManagedAdoptionPreview,
    ManagedAdoptionState,
    install_managed_live_adoption,
)
from runtime_safety import RuntimeSafetyError
from safe_output import SafetyPolicy


class FakeHass:
    def __init__(self):
        self.live = {
            "switch": "on",
            "set_voltage": 16.50,
            "set_current": 1.00,
            "ovp": 16.70,
            "ocp": 1.20,
            "voltage": 16.48,
            "current": 0.90,
            "battery_voltage": 14.40,
            "temp_ext": 25.0,
            "temp_int": 30.0,
            "protection_code": 0,
        }
        self.turn_on_calls = 0
        self.turn_off_calls = 0
        self.writes = []

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


class FakeManual:
    def __init__(self):
        self.state = ManualSessionState.IDLE
        self.request = None
        self.started_at = 0.0
        self.paused_total_s = 0.0
        self.cooling_started_at = None
        self.stop_reason = ""
        self._task = None
        self.persist_count = 0
        self.reach_voltage_v = None
        self.reach_current_a = None
        self._previous_voltage_v = None
        self._previous_current_a = None

    @property
    def is_active(self):
        return self.state in {
            ManualSessionState.ARMING,
            ManualSessionState.ACTIVE,
            ManualSessionState.COOLING,
        }

    def _persist(self):
        self.persist_count += 1

    def _reset_delta_tracking(self):
        pass


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
    generation = 40


class FakeEdge:
    def __init__(self, app, *, mutate_after_adopt=None, fail_before_command=None):
        self.app = app
        self.prepare_calls = 0
        self.adopt_calls = 0
        self.mutate_after_adopt = mutate_after_adopt
        self.fail_before_command = fail_before_command
        self.command_may_have_executed = False

    async def prepare(self):
        self.prepare_calls += 1
        self.command_may_have_executed = False
        return FakeEdgeState()

    async def adopt(self, *, expected_generation=None):
        self.adopt_calls += 1
        self.command_may_have_executed = False
        if self.fail_before_command is not None:
            raise RuntimeSafetyError(self.fail_before_command)
        self.command_may_have_executed = True
        if self.mutate_after_adopt is not None:
            self.mutate_after_adopt(self.app)
        return types.SimpleNamespace(generation=41, armed=True)


class ManagedLiveAdoptionTests(unittest.IsolatedAsyncioTestCase):
    def make_system(self, state_file):
        app = types.SimpleNamespace()
        app.hass = FakeHass()
        app.ENTITY_MAP = {"switch": "switch.rd_output"}
        app.charge_controller = types.SimpleNamespace(is_active=False)
        app.manual_session_manager = FakeManual()
        app.rd_live_mix_observer = None
        guard = FakeGuard(app)
        manager = FakeManager(app, guard)
        coordinator = install_managed_live_adoption(app, manager, install_ui=False)
        coordinator.state_file = state_file
        coordinator.state = ManagedAdoptionState.IDLE
        coordinator.edge = FakeEdge(app)
        return app, manager, coordinator

    @staticmethod
    def preview(
        *,
        set_voltage=16.50,
        set_current=1.00,
        ovp=16.70,
        ocp=1.20,
    ):
        return ManagedAdoptionPreview(
            token="preview-token",
            battery_id="Baic72",
            chemistry=BatteryChemistry.CA_CA,
            capacity_ah=72.0,
            fingerprint=ManagedAdoptionFingerprint(
                float(set_voltage), float(set_current), float(ovp), float(ocp)
            ),
        )

    async def cleanup_task(self, coordinator):
        task = coordinator._task
        coordinator._task = None
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    async def test_successful_adoption_changes_only_ownership_authority(self):
        with tempfile.TemporaryDirectory() as tmp:
            app, manager, coordinator = self.make_system(f"{tmp}/adoption.json")
            ok = await coordinator.adopt(self.preview())
            self.assertTrue(ok)
            self.assertTrue(coordinator.active)
            self.assertTrue(manager.pb_managed)
            self.assertEqual(app.manual_session_manager.state, ManualSessionState.ACTIVE)
            self.assertIsInstance(app.manual_session_manager.request, ManualChargeRequest)
            self.assertEqual(app.manual_session_manager.request.voltage_v, 16.50)
            self.assertEqual(app.manual_session_manager.request.current_a, 1.00)
            self.assertEqual(app.hass.turn_on_calls, 0)
            self.assertEqual(app.hass.turn_off_calls, 0)
            self.assertEqual(app.hass.writes, [])
            self.assertEqual(coordinator.edge.prepare_calls, 1)
            self.assertEqual(coordinator.edge.adopt_calls, 1)
            await self.cleanup_task(coordinator)

    async def test_disabled_protection_fails_read_only_before_edge_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            app, manager, coordinator = self.make_system(f"{tmp}/adoption.json")
            app.hass.live["ocp"] = 0.0
            with self.assertRaises(RuntimeSafetyError):
                await coordinator.adopt(self.preview())
            self.assertTrue(manager.hands_off)
            self.assertEqual(coordinator.edge.prepare_calls, 0)
            self.assertEqual(coordinator.edge.adopt_calls, 0)
            self.assertEqual(app.hass.turn_off_calls, 0)
            self.assertEqual(app.hass.writes, [])

    async def test_low_temperature_fails_read_only_before_edge_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            app, manager, coordinator = self.make_system(f"{tmp}/adoption.json")
            app.hass.live["temp_ext"] = 9.0
            with self.assertRaisesRegex(RuntimeSafetyError, "below managed start envelope"):
                await coordinator.adopt(self.preview())
            self.assertTrue(manager.hands_off)
            self.assertEqual(coordinator.edge.prepare_calls, 0)
            self.assertEqual(app.hass.turn_off_calls, 0)
            self.assertEqual(app.hass.writes, [])

    async def test_pause_temperature_fails_read_only_before_edge_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            app, manager, coordinator = self.make_system(f"{tmp}/adoption.json")
            app.hass.live["temp_ext"] = 40.0
            with self.assertRaisesRegex(RuntimeSafetyError, "requires managed pause/OFF"):
                await coordinator.adopt(self.preview())
            self.assertTrue(manager.hands_off)
            self.assertEqual(coordinator.edge.prepare_calls, 0)
            self.assertEqual(app.hass.turn_off_calls, 0)
            self.assertEqual(app.hass.writes, [])

    async def test_auto_enable_hardware_config_fails_read_only_before_edge_command(self):
        for key in ("boot_power", "take_out"):
            with self.subTest(key=key), tempfile.TemporaryDirectory() as tmp:
                app, manager, coordinator = self.make_system(f"{tmp}/adoption.json")
                app.hass.live[key] = True
                with self.assertRaisesRegex(RuntimeSafetyError, "auto-enable configuration"):
                    await coordinator.adopt(self.preview())
                self.assertTrue(manager.hands_off)
                self.assertEqual(coordinator.edge.prepare_calls, 0)
                self.assertEqual(app.hass.turn_off_calls, 0)
                self.assertEqual(app.hass.writes, [])

    async def test_measured_current_over_working_ceiling_fails_before_edge_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            app, manager, coordinator = self.make_system(f"{tmp}/adoption.json")
            app.hass.live.update(
                set_current=12.0,
                ocp=12.2,
                current=12.10,
            )
            preview = self.preview(set_current=12.0, ocp=12.2)
            with self.assertRaisesRegex(RuntimeSafetyError, "current exceeds managed absolute working"):
                await coordinator.adopt(preview)
            self.assertTrue(manager.hands_off)
            self.assertEqual(coordinator.edge.prepare_calls, 0)
            self.assertEqual(app.hass.turn_off_calls, 0)
            self.assertEqual(app.hass.writes, [])

    async def test_measured_voltage_over_working_ceiling_fails_before_edge_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            app, manager, coordinator = self.make_system(f"{tmp}/adoption.json")
            app.hass.live.update(
                set_voltage=17.50,
                ovp=17.60,
                voltage=17.57,
            )
            preview = self.preview(set_voltage=17.50, ovp=17.60)
            with self.assertRaisesRegex(RuntimeSafetyError, "voltage exceeds managed absolute working"):
                await coordinator.adopt(preview)
            self.assertTrue(manager.hands_off)
            self.assertEqual(coordinator.edge.prepare_calls, 0)
            self.assertEqual(app.hass.turn_off_calls, 0)
            self.assertEqual(app.hass.writes, [])

    async def test_edge_adopt_precommand_race_does_not_stop_external_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            app, manager, coordinator = self.make_system(f"{tmp}/adoption.json")
            coordinator.edge = FakeEdge(app, fail_before_command="synthetic pre-command race")

            with self.assertRaisesRegex(RuntimeSafetyError, "synthetic pre-command race"):
                await coordinator.adopt(self.preview())

            self.assertTrue(manager.hands_off)
            self.assertEqual(coordinator.edge.prepare_calls, 1)
            self.assertEqual(coordinator.edge.adopt_calls, 1)
            self.assertFalse(coordinator.edge.command_may_have_executed)
            self.assertEqual(app.hass.turn_off_calls, 0)
            self.assertEqual(app.hass.live["switch"], "on")
            self.assertEqual(app.hass.writes, [])
            self.assertEqual(coordinator.state, ManagedAdoptionState.FAILED)

    async def test_post_edge_toctou_change_forces_verified_off(self):
        with tempfile.TemporaryDirectory() as tmp:
            app, manager, coordinator = self.make_system(f"{tmp}/adoption.json")
            coordinator.edge = FakeEdge(
                app,
                mutate_after_adopt=lambda app_arg: app_arg.hass.live.__setitem__(
                    "set_voltage", 16.80
                ),
            )
            with self.assertRaises(RuntimeSafetyError):
                await coordinator.adopt(self.preview())
            self.assertTrue(manager.hands_off)
            self.assertTrue(coordinator.edge.command_may_have_executed)
            self.assertEqual(app.hass.turn_off_calls, 1)
            self.assertEqual(app.hass.live["switch"], "off")
            self.assertEqual(coordinator.state, ManagedAdoptionState.FAILED)

    async def test_out_of_band_increase_terminates_adoption_off(self):
        with tempfile.TemporaryDirectory() as tmp:
            app, manager, coordinator = self.make_system(f"{tmp}/adoption.json")
            await coordinator.adopt(self.preview())
            await self.cleanup_task(coordinator)
            app.hass.live["set_current"] = 1.20
            await coordinator.observe_once()
            self.assertEqual(app.hass.turn_off_calls, 1)
            self.assertEqual(coordinator.state, ManagedAdoptionState.FAILED)

    async def test_external_decrease_ratchets_authority_without_actuation(self):
        with tempfile.TemporaryDirectory() as tmp:
            app, manager, coordinator = self.make_system(f"{tmp}/adoption.json")
            await coordinator.adopt(self.preview())
            await self.cleanup_task(coordinator)
            app.hass.live["set_current"] = 0.80
            await coordinator.observe_once()
            self.assertTrue(coordinator.active)
            self.assertEqual(coordinator.current_authority.set_current_a, 0.80)
            self.assertEqual(app.manual_session_manager.request.current_a, 0.80)
            self.assertEqual(app.hass.turn_off_calls, 0)

    async def test_bot_write_cannot_increase_and_successful_decrease_is_sticky(self):
        with tempfile.TemporaryDirectory() as tmp:
            app, manager, coordinator = self.make_system(f"{tmp}/adoption.json")
            await coordinator.adopt(self.preview())
            await self.cleanup_task(coordinator)

            with self.assertRaisesRegex(RuntimeSafetyError, "increase blocked"):
                await app.hass.set_voltage(16.70)
            self.assertEqual(app.hass.writes, [])

            self.assertTrue(await app.hass.set_voltage(16.40))
            self.assertEqual(coordinator.current_authority.set_voltage_v, 16.40)
            with self.assertRaisesRegex(RuntimeSafetyError, "increase blocked"):
                await app.hass.set_voltage(16.50)

    async def test_adopted_session_cannot_reenergize_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            app, manager, coordinator = self.make_system(f"{tmp}/adoption.json")
            await coordinator.adopt(self.preview())
            await self.cleanup_task(coordinator)
            app.hass.live["switch"] = "off"
            with self.assertRaisesRegex(RuntimeSafetyError, "cannot re-energize"):
                await app.hass.turn_on()
            self.assertEqual(app.hass.turn_on_calls, 0)

    async def test_restart_converts_active_authority_to_verified_off_pending(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_file = f"{tmp}/adoption.json"
            app, manager, coordinator = self.make_system(state_file)
            await coordinator.adopt(self.preview())
            await self.cleanup_task(coordinator)

            restored = type(coordinator)(app, manager, state_file=state_file, edge=FakeEdge(app))
            self.assertEqual(restored.state, ManagedAdoptionState.OFF_PENDING)
            self.assertTrue(await restored.recover_startup())
            self.assertEqual(app.hass.live["switch"], "off")
            self.assertEqual(restored.state, ManagedAdoptionState.INTERRUPTED)


if __name__ == "__main__":
    unittest.main()
