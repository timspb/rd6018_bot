import types
import unittest

from application.execution_port import ExecutionPort, get_or_create_execution_port
from runtime.safety.runtime_guard import RuntimeSafetyError


class Owner:
    def __init__(self):
        self.calls = []
        self.live = {"switch": "off", "battery_voltage": 12.5}

    async def get_all_live(self):
        return dict(self.live)

    async def turn_on(self):
        self.calls.append("on")
        self.live["switch"] = "on"
        return True

    async def turn_off(self, entity_id=None):
        self.calls.append(("off", entity_id))
        self.live["switch"] = "off"
        return True

    async def set_voltage(self, value):
        self.calls.append(("v", float(value)))
        return True

    async def set_current(self, value):
        self.calls.append(("i", float(value)))
        return True


class Adoption:
    def __init__(self, *, active=False, off_pending=False, ceiling=16.5):
        self.active = active
        self.off_pending = off_pending
        self.ceiling = float(ceiling)
        self.events = []

    def authorize_managed_write(self, field, value):
        self.events.append(("authorize", field, float(value)))
        if self.active and float(value) > self.ceiling:
            raise RuntimeSafetyError("increase blocked")

    def ratchet_after_managed_write(self, field, value):
        if self.active:
            self.events.append(("ratchet", field, float(value)))
            self.ceiling = min(self.ceiling, float(value))


class Mix(Adoption):
    @property
    def managed_authority(self):
        return self.active or self.off_pending


class ExecutionPortPolicyBoundaryTests(unittest.IsolatedAsyncioTestCase):
    def app(self):
        owner = Owner()
        hass = types.SimpleNamespace(marker="transport")
        app = types.SimpleNamespace(
            hass=hass,
            runtime_safety_guard=owner,
            rd_control_mode_manager=None,
            rd_startup_authority_gate=None,
            rd_managed_live_adoption=None,
            rd_managed_mix_adoption=None,
        )
        port = get_or_create_execution_port(app)
        return app, owner, port

    async def test_explicit_safety_owner_not_transport_adapter(self):
        app, owner, port = self.app()
        self.assertIs(port._execution_owner, owner)
        self.assertFalse(hasattr(port, "execution_owner"))
        self.assertIs(app.hass.marker, "transport")
        await port.program_voltage(14.2)
        self.assertEqual(owner.calls, [("v", 14.2)])

    async def test_hands_off_blocks_normal_actuation_without_mutating_transport(self):
        app, owner, port = self.app()
        app.rd_control_mode_manager = types.SimpleNamespace(
            hands_off=True, edge_autonomous=False, release_in_progress=False
        )
        with self.assertRaisesRegex(RuntimeSafetyError, "HANDS_OFF"):
            await port.program_voltage(14.2)
        with self.assertRaisesRegex(RuntimeSafetyError, "HANDS_OFF"):
            await port.request_verified_on()
        self.assertEqual(owner.calls, [])
        self.assertEqual(app.hass.marker, "transport")

    async def test_explicit_emergency_off_override_is_default_deny_and_off_only(self):
        app, owner, port = self.app()
        app.rd_control_mode_manager = types.SimpleNamespace(
            hands_off=True, edge_autonomous=False, release_in_progress=False
        )
        with self.assertRaisesRegex(RuntimeSafetyError, "HANDS_OFF"):
            await port.request_emergency_off()
        self.assertTrue(await port.request_emergency_off(
            "switch.rd6018", allow_hands_off_operator_off=True
        ))
        self.assertEqual(owner.calls, [("off", "switch.rd6018")])
        with self.assertRaisesRegex(RuntimeSafetyError, "HANDS_OFF"):
            await port.request_verified_off()
        for action in ("Output ON", "voltage write", "current write"):
            with self.assertRaisesRegex(RuntimeSafetyError, "HANDS_OFF"):
                port._normal_actuation_gate(
                    action,
                    allow_hands_off_operator_off=True,
                )

    async def test_explicit_hands_off_off_override_cannot_enable_or_write_or_bypass_autonomous(self):
        app, owner, port = self.app()
        app.rd_control_mode_manager = types.SimpleNamespace(
            hands_off=True, edge_autonomous=False, release_in_progress=False
        )
        with self.assertRaisesRegex(RuntimeSafetyError, "HANDS_OFF"):
            await port.request_verified_on()
        with self.assertRaisesRegex(RuntimeSafetyError, "HANDS_OFF"):
            await port.program_voltage(14.2)
        with self.assertRaisesRegex(RuntimeSafetyError, "HANDS_OFF"):
            await port.program_current(1.0)
        app.rd_control_mode_manager.edge_autonomous = True
        with self.assertRaisesRegex(RuntimeSafetyError, "AUTONOMOUS"):
            await port.request_emergency_off(
                "switch.rd6018", allow_hands_off_operator_off=True
            )
        self.assertEqual(owner.calls, [])

    async def test_release_barrier_allows_off_direction_only(self):
        app, owner, port = self.app()
        app.rd_control_mode_manager = types.SimpleNamespace(
            hands_off=False, edge_autonomous=False, release_in_progress=True
        )
        with self.assertRaisesRegex(RuntimeSafetyError, "HANDS_OFF transfer"):
            await port.program_current(1.0)
        self.assertTrue(await port.request_verified_off())
        self.assertEqual(owner.calls, [("off", None)])

    async def test_startup_gate_blocks_normal_actions_but_quarantine_clearance_keeps_off(self):
        app, owner, port = self.app()
        manager = types.SimpleNamespace(
            hands_off=False, edge_autonomous=False, release_in_progress=False
        )
        app.rd_control_mode_manager = manager
        gate = types.SimpleNamespace(
            recovery_scope=False,
            managed_actuation_ready=False,
            candidate_autonomous=False,
            _blocked=lambda action: RuntimeSafetyError("authority unresolved: " + action),
        )
        app.rd_startup_authority_gate = gate
        with self.assertRaisesRegex(RuntimeSafetyError, "authority unresolved"):
            await port.program_current(1.0)
        app.session_recovery_guard.quarantine("test")
        self.assertTrue(await port.request_verified_off())
        self.assertEqual(owner.calls, [("off", None)])

    async def test_adopted_authority_blocks_on_and_ratchets_successful_write(self):
        app, owner, port = self.app()
        adoption = Adoption(active=True, ceiling=16.5)
        app.rd_managed_live_adoption = adoption
        with self.assertRaisesRegex(RuntimeSafetyError, "cannot re-energize"):
            await port.request_verified_on()
        with self.assertRaisesRegex(RuntimeSafetyError, "increase blocked"):
            await port.program_voltage(16.7)
        self.assertTrue(await port.program_voltage(16.4))
        self.assertEqual(
            adoption.events,
            [
                ("authorize", "set_voltage_v", 16.7),
                ("authorize", "set_voltage_v", 16.4),
                ("ratchet", "set_voltage_v", 16.4),
            ],
        )

    async def test_mix_authority_is_checked_before_transport_write(self):
        app, owner, port = self.app()
        mix = Mix(active=True, ceiling=3.0)
        app.rd_managed_mix_adoption = mix
        with self.assertRaisesRegex(RuntimeSafetyError, "increase blocked"):
            await port.program_current(3.1)
        self.assertEqual(owner.calls, [])
        self.assertTrue(await port.program_current(2.9))
        self.assertEqual(owner.calls, [("i", 2.9)])


class CompositionSourceContractTests(unittest.TestCase):
    def test_ownership_installers_do_not_monkeypatch_hass_actuators(self):
        from pathlib import Path
        for relative in (
            "rd_control_mode.py",
            "rd_startup_authority.py",
            "rd_managed_adoption.py",
            "rd_managed_mix.py",
        ):
            source = Path(relative).read_text(encoding="utf-8")
            for token in (
                "hass.turn_on =",
                "hass.turn_off =",
                "hass.set_voltage =",
                "hass.set_current =",
            ):
                self.assertNotIn(token, source, relative)

    def test_production_installs_detached_safety_before_execution_port(self):
        from pathlib import Path
        source = Path("production_bootstrap.py").read_text(encoding="utf-8")
        safety = source.index("install_managed_runtime_safety(app, patch_adapter=False)")
        port = source.index("get_or_create_execution_port(app)", safety)
        self.assertLess(safety, port)

    def test_application_consumers_cannot_reach_the_private_execution_owner(self):
        from pathlib import Path
        for relative in (
            "application/main_guard_transaction.py",
            "application/recipe_execution_adapter.py",
        ):
            source = Path(relative).read_text(encoding="utf-8")
            self.assertNotIn(".execution_owner", source, relative)
            self.assertIn("port.read_live()", source, relative)
        port_source = Path("application/execution_port.py").read_text(encoding="utf-8")
        self.assertIn("self._execution_owner = execution_owner", port_source)
        self.assertNotIn("self.execution_owner =", port_source)
        self.assertIn("async def read_live(", port_source)
        for path in Path("application").rglob("*.py"):
            if path.name == "execution_port.py":
                continue
            source = path.read_text(encoding="utf-8")
            self.assertNotIn(".execution_owner", source, str(path))
            self.assertNotIn("._execution_owner", source, str(path))

    def test_hass_client_is_transport_only_not_a_second_safety_owner(self):
        from pathlib import Path
        source = Path("hass_api.py").read_text(encoding="utf-8")
        for forbidden in (
            "SafetySupervisor",
            "SafeOutputCoordinator",
            "snapshot_from_live",
            "_safety_supervisor",
            "_programming_state",
            "safe_enable_output",
            "verify_live_programming",
            "wait_for_output_off",
        ):
            self.assertNotIn(forbidden, source)
        self.assertIn('return await self._switch_service("turn_on", entity_id)', source)
        self.assertIn('return await self._switch_service("turn_off", entity_id)', source)
        self.assertIn("async def get_native_physical_output_report(", source)

    def test_safety_owner_uses_transport_adapter_without_metadata_monkeypatch(self):
        from pathlib import Path
        runtime_guard = Path("runtime/safety/runtime_guard.py").read_text(encoding="utf-8")
        strict_guard = Path("runtime/safety/strict_guard.py").read_text(encoding="utf-8")
        managed_guard = Path("runtime/safety/managed_guard.py").read_text(encoding="utf-8")
        production = Path("runtime/production_runtime.py").read_text(encoding="utf-8")
        self.assertIn("self.adapter = app.hass", runtime_guard)
        self.assertNotIn("self.hass", runtime_guard)
        self.assertNotIn("self.hass", strict_guard)
        self.assertNotIn("_install_last_reported_metadata_bridge", managed_guard)
        self.assertNotIn("_entity_metadata =", managed_guard)
        self.assertNotIn("_install_last_reported_metadata_bridge", production)


if __name__ == "__main__":
    unittest.main()
