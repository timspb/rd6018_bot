import unittest
from enum import Enum
from types import SimpleNamespace

from physical_test_control import PhysicalTestControl
from physical_test_control_pb_mode import install_physical_test_control_pb_mode


class Mode(str, Enum):
    HANDS_OFF = "hands_off"
    PB_MANAGED = "pb_managed"


class FakeLease:
    def __init__(self) -> None:
        self.state = SimpleNamespace(
            armed=False,
            tripped=False,
            boot_quarantine=False,
            generation=16,
            remaining_s=0.0,
            modbus_age_s=2.0,
        )

    async def read_state(self):
        return SimpleNamespace(**vars(self.state))


class FakeGuard:
    def __init__(self, live):
        self.live = live
        self.edge_safety_lease = FakeLease()
        self._off_unconfirmed = False

    async def _raw_live(self):
        return dict(self.live)


class FakeModeManager:
    def __init__(self, mode=Mode.HANDS_OFF):
        self.mode = mode
        self.return_calls = 0
        self.release_in_progress = False
        self._edge_autonomous = False

    @property
    def hands_off(self):
        return self.mode is Mode.HANDS_OFF

    @property
    def pb_managed(self):
        return self.mode is Mode.PB_MANAGED

    @property
    def edge_autonomous(self):
        return self._edge_autonomous

    async def return_pb_control(self):
        self.return_calls += 1
        self.mode = Mode.PB_MANAGED
        return True


class FakeAutonomousEdge:
    def __init__(self) -> None:
        self.autonomous = False

    async def read_autonomous(self):
        return self.autonomous


class FakeAutonomousCoordinator:
    def __init__(self, manager, lease):
        self.manager = manager
        self.lease = lease
        self.edge = FakeAutonomousEdge()
        self.enter_calls = 0
        self.exit_calls = 0

    async def enter(self):
        self.enter_calls += 1
        self.manager.mode = Mode.HANDS_OFF
        self.manager._edge_autonomous = True
        self.edge.autonomous = True
        self.lease.state.generation += 1
        return True

    async def exit(self):
        self.exit_calls += 1
        self.manager._edge_autonomous = False
        self.edge.autonomous = False
        self.manager.mode = Mode.PB_MANAGED
        self.lease.state.generation += 1
        return True


class FakeApp:
    def __init__(self, *, mode=Mode.HANDS_OFF, output="off"):
        self.runtime_safety_guard = FakeGuard(
            {
                "switch": output,
                "output_state_code_v2": 0.0 if output == "off" else 1.0,
                "set_voltage": 15.10,
                "set_current": 0.18,
                "ovp": 15.30,
                "ocp": 0.40,
                "protection_code": 0.0,
            }
        )
        self.rd_control_mode_manager = FakeModeManager(mode)
        self.rd_autonomous_mode = FakeAutonomousCoordinator(
            self.rd_control_mode_manager,
            self.runtime_safety_guard.edge_safety_lease,
        )
        self.charge_controller = SimpleNamespace(is_active=False)
        self.manual_session_manager = SimpleNamespace(is_active=False)
        self.rd_managed_live_adoption = SimpleNamespace(active=False, off_pending=False)
        self.rd_managed_mix_adoption = SimpleNamespace(active=False, off_pending=False)


class PhysicalTestPbModeTests(unittest.IsolatedAsyncioTestCase):
    def _control(self, app):
        control = PhysicalTestControl(app, enabled=True)
        install_physical_test_control_pb_mode(app, control)
        return control

    async def test_requires_hands_off(self):
        app = FakeApp(mode=Mode.PB_MANAGED)
        response = await self._control(app).dispatch({"op": "return_pb_control_verified_off"})
        self.assertFalse(response["ok"])
        self.assertEqual(app.rd_control_mode_manager.return_calls, 0)

    async def test_requires_canonical_output_off(self):
        app = FakeApp(output="on")
        response = await self._control(app).dispatch({"op": "return_pb_control_verified_off"})
        self.assertFalse(response["ok"])
        self.assertEqual(app.rd_control_mode_manager.return_calls, 0)

    async def test_rejects_active_authority(self):
        app = FakeApp()
        app.rd_managed_live_adoption.active = True
        response = await self._control(app).dispatch({"op": "return_pb_control_verified_off"})
        self.assertFalse(response["ok"])
        self.assertEqual(app.rd_control_mode_manager.return_calls, 0)

    async def test_rejects_dirty_edge_state(self):
        app = FakeApp()
        app.runtime_safety_guard.edge_safety_lease.state.armed = True
        app.runtime_safety_guard.edge_safety_lease.state.remaining_s = 899.0
        response = await self._control(app).dispatch({"op": "return_pb_control_verified_off"})
        self.assertFalse(response["ok"])
        self.assertEqual(app.rd_control_mode_manager.return_calls, 0)

    async def test_rejects_unconfirmed_off_or_nonzero_protection(self):
        app = FakeApp()
        app.runtime_safety_guard._off_unconfirmed = True
        response = await self._control(app).dispatch({"op": "return_pb_control_verified_off"})
        self.assertFalse(response["ok"])
        self.assertEqual(app.rd_control_mode_manager.return_calls, 0)

        app = FakeApp()
        app.runtime_safety_guard.live["protection_code"] = 2.0
        response = await self._control(app).dispatch({"op": "return_pb_control_verified_off"})
        self.assertFalse(response["ok"])
        self.assertEqual(app.rd_control_mode_manager.return_calls, 0)

    async def test_transition_delegates_existing_manager_and_preserves_hardware_state(self):
        app = FakeApp()
        control = self._control(app)
        before_live = dict(app.runtime_safety_guard.live)
        before_generation = app.runtime_safety_guard.edge_safety_lease.state.generation
        response = await control.dispatch({"op": "return_pb_control_verified_off"})
        self.assertTrue(response["ok"])
        self.assertEqual(app.rd_control_mode_manager.return_calls, 1)
        self.assertTrue(app.rd_control_mode_manager.pb_managed)
        self.assertEqual(app.runtime_safety_guard.live, before_live)
        self.assertEqual(
            app.runtime_safety_guard.edge_safety_lease.state.generation,
            before_generation,
        )
        result = response["result"]
        self.assertEqual(result["mode"], "pb_managed")
        self.assertEqual(result["output"], "off")
        self.assertEqual(result["output_state_code_v2"], 0.0)
        self.assertFalse(result["lease_armed"])
        self.assertEqual(result["hardware_writes_injected"], 0)

    async def test_extra_fields_are_rejected_without_transition(self):
        app = FakeApp()
        response = await self._control(app).dispatch(
            {"op": "return_pb_control_verified_off", "force": True}
        )
        self.assertFalse(response["ok"])
        self.assertEqual(app.rd_control_mode_manager.return_calls, 0)

    async def test_autonomous_status_is_read_only(self):
        app = FakeApp(mode=Mode.PB_MANAGED)
        control = self._control(app)
        before_live = dict(app.runtime_safety_guard.live)
        before_generation = app.runtime_safety_guard.edge_safety_lease.state.generation
        response = await control.dispatch({"op": "autonomous_status"})
        self.assertTrue(response["ok"])
        self.assertFalse(response["result"]["edge_autonomous"])
        self.assertFalse(response["result"]["manager_edge_autonomous"])
        self.assertEqual(response["result"]["rd_control_mode"], "pb_managed")
        self.assertEqual(app.runtime_safety_guard.live, before_live)
        self.assertEqual(app.runtime_safety_guard.edge_safety_lease.state.generation, before_generation)
        self.assertEqual(app.rd_autonomous_mode.enter_calls, 0)
        self.assertEqual(app.rd_autonomous_mode.exit_calls, 0)

    async def test_autonomous_entry_delegates_production_coordinator_off_only(self):
        app = FakeApp(mode=Mode.PB_MANAGED)
        control = self._control(app)
        before_live = dict(app.runtime_safety_guard.live)
        before_generation = app.runtime_safety_guard.edge_safety_lease.state.generation
        response = await control.dispatch({"op": "enter_autonomous_verified_off"})
        self.assertTrue(response["ok"])
        self.assertEqual(app.rd_autonomous_mode.enter_calls, 1)
        self.assertEqual(app.rd_autonomous_mode.exit_calls, 0)
        self.assertTrue(app.rd_control_mode_manager.hands_off)
        self.assertTrue(app.rd_control_mode_manager.edge_autonomous)
        self.assertTrue(response["result"]["edge_autonomous"])
        self.assertEqual(response["result"]["output"], "off")
        self.assertEqual(app.runtime_safety_guard.live, before_live)
        self.assertNotEqual(
            app.runtime_safety_guard.edge_safety_lease.state.generation,
            before_generation,
        )
        self.assertEqual(response["result"]["rd_actuator_writes_injected"], 0)

    async def test_autonomous_entry_rejects_output_on_before_coordinator(self):
        app = FakeApp(mode=Mode.PB_MANAGED, output="on")
        response = await self._control(app).dispatch({"op": "enter_autonomous_verified_off"})
        self.assertFalse(response["ok"])
        self.assertEqual(app.rd_autonomous_mode.enter_calls, 0)
        self.assertFalse(app.rd_autonomous_mode.edge.autonomous)

    async def test_autonomous_entry_requires_normal_protection(self):
        app = FakeApp(mode=Mode.PB_MANAGED)
        app.runtime_safety_guard.live["protection_code"] = 2.0
        response = await self._control(app).dispatch({"op": "enter_autonomous_verified_off"})
        self.assertFalse(response["ok"])
        self.assertEqual(app.rd_autonomous_mode.enter_calls, 0)

    async def test_autonomous_entry_rejects_already_autonomous(self):
        app = FakeApp(mode=Mode.HANDS_OFF)
        app.rd_autonomous_mode.edge.autonomous = True
        app.rd_control_mode_manager._edge_autonomous = True
        response = await self._control(app).dispatch({"op": "enter_autonomous_verified_off"})
        self.assertFalse(response["ok"])
        self.assertEqual(app.rd_autonomous_mode.enter_calls, 0)

    async def test_autonomous_exit_delegates_production_coordinator_and_stays_off(self):
        app = FakeApp(mode=Mode.HANDS_OFF)
        app.rd_autonomous_mode.edge.autonomous = True
        app.rd_control_mode_manager._edge_autonomous = True
        control = self._control(app)
        before_live = dict(app.runtime_safety_guard.live)
        before_generation = app.runtime_safety_guard.edge_safety_lease.state.generation
        response = await control.dispatch({"op": "exit_autonomous_verified_off"})
        self.assertTrue(response["ok"])
        self.assertEqual(app.rd_autonomous_mode.exit_calls, 1)
        self.assertFalse(app.rd_control_mode_manager.edge_autonomous)
        self.assertTrue(app.rd_control_mode_manager.pb_managed)
        self.assertFalse(response["result"]["edge_autonomous"])
        self.assertEqual(response["result"]["output"], "off")
        self.assertEqual(app.runtime_safety_guard.live, before_live)
        self.assertNotEqual(
            app.runtime_safety_guard.edge_safety_lease.state.generation,
            before_generation,
        )
        self.assertEqual(response["result"]["rd_actuator_writes_injected"], 0)

    async def test_autonomous_exit_requires_autonomous_and_clean_edge(self):
        app = FakeApp(mode=Mode.HANDS_OFF)
        response = await self._control(app).dispatch({"op": "exit_autonomous_verified_off"})
        self.assertFalse(response["ok"])
        self.assertEqual(app.rd_autonomous_mode.exit_calls, 0)

        app = FakeApp(mode=Mode.HANDS_OFF)
        app.rd_autonomous_mode.edge.autonomous = True
        app.rd_control_mode_manager._edge_autonomous = True
        app.runtime_safety_guard.edge_safety_lease.state.tripped = True
        response = await self._control(app).dispatch({"op": "exit_autonomous_verified_off"})
        self.assertFalse(response["ok"])
        self.assertEqual(app.rd_autonomous_mode.exit_calls, 0)

    async def test_autonomous_operations_reject_extra_fields(self):
        app = FakeApp(mode=Mode.PB_MANAGED)
        response = await self._control(app).dispatch(
            {"op": "enter_autonomous_verified_off", "force": True}
        )
        self.assertFalse(response["ok"])
        self.assertEqual(app.rd_autonomous_mode.enter_calls, 0)


if __name__ == "__main__":
    unittest.main()
