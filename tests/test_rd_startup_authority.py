import types
import unittest

import v2_mix_mode
from rd_startup_authority import RdStartupAuthorityGate
from runtime_safety import RuntimeSafetyError


class DummyHass:
    def __init__(self):
        self.turn_on_calls = 0
        self.turn_off_calls = 0
        self.get_all_calls = 0

    async def get_all_live(self):
        self.get_all_calls += 1
        return {"switch": "off", "autonomous_mode": "off", "managed": True}

    async def turn_on(self, entity_id=None):
        self.turn_on_calls += 1
        return True

    async def turn_off(self, entity_id=None):
        self.turn_off_calls += 1
        return True

    async def set_voltage(self, value):
        return True

    async def set_current(self, value):
        return True

    async def set_ovp(self, value):
        return True

    async def set_ocp(self, value):
        return True


class DummyGuard:
    def __init__(self):
        self.raw = {"switch": "off", "autonomous_mode": "off"}
        self.read_error = None

    async def _raw_live(self):
        if self.read_error is not None:
            raise self.read_error
        return dict(self.raw)


class DummyManager:
    def __init__(self, guard):
        self.guard = guard
        self.pb_managed = True
        self.hands_off = False
        self._edge_autonomous = False
        self.return_calls = 0

    @property
    def edge_autonomous(self):
        return self._edge_autonomous

    def _observe_edge_mode(self, live):
        value = live.get("autonomous_mode")
        if value in (True, 1, "on", "true", "1"):
            self._edge_autonomous = True
        elif value in (False, 0, "off", "false", "0"):
            self._edge_autonomous = False

    async def return_pb_control(self):
        self.return_calls += 1
        self.hands_off = False
        self.pb_managed = True
        return True


class RdStartupAuthorityGateTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.original_mix = v2_mix_mode.start_mix_transactional
        if hasattr(v2_mix_mode, "_rd_startup_authority_wrapped"):
            delattr(v2_mix_mode, "_rd_startup_authority_wrapped")

    async def asyncTearDown(self):
        v2_mix_mode.start_mix_transactional = self.original_mix
        if hasattr(v2_mix_mode, "_rd_startup_authority_wrapped"):
            delattr(v2_mix_mode, "_rd_startup_authority_wrapped")

    @staticmethod
    def make():
        hass = DummyHass()
        guard = DummyGuard()
        manager = DummyManager(guard)
        app = types.SimpleNamespace(hass=hass)
        gate = RdStartupAuthorityGate(app, manager)
        return app, manager, guard, gate

    async def test_normal_actuation_is_blocked_before_reconciliation(self):
        app, _manager, _guard, gate = self.make()

        with self.assertRaisesRegex(RuntimeSafetyError, "authority unresolved"):
            await app.hass.turn_on("switch.test")

        self.assertFalse(gate.managed_actuation_ready)
        self.assertEqual(app.hass.turn_on_calls, 0)

    async def test_managed_recovery_may_use_verified_off_then_reopens_control(self):
        app, manager, _guard, gate = self.make()
        recovery_calls = 0

        async def recover():
            nonlocal recovery_calls
            recovery_calls += 1
            self.assertTrue(gate.recovery_scope)
            self.assertTrue(await app.hass.turn_off("switch.test"))
            return True

        result = await gate.reconcile(recover)

        self.assertEqual(result, "managed")
        self.assertEqual(recovery_calls, 1)
        self.assertTrue(gate.managed_actuation_ready)
        self.assertFalse(manager.edge_autonomous)
        self.assertTrue(await app.hass.turn_on("switch.test"))

    async def test_autonomous_never_runs_managed_recovery_or_allows_bot_output(self):
        app, manager, guard, gate = self.make()
        guard.raw["autonomous_mode"] = "on"
        recovery_calls = 0

        async def recover():
            nonlocal recovery_calls
            recovery_calls += 1
            return True

        result = await gate.reconcile(recover)

        self.assertEqual(result, "autonomous")
        self.assertEqual(recovery_calls, 0)
        self.assertTrue(manager.edge_autonomous)
        self.assertFalse(gate.managed_actuation_ready)
        with self.assertRaisesRegex(RuntimeSafetyError, "AUTONOMOUS"):
            await app.hass.turn_on("switch.test")

    async def test_explicit_autonomous_exit_can_reopen_gate_after_clean_pb_return(self):
        app, manager, guard, gate = self.make()
        guard.raw["autonomous_mode"] = "on"

        async def recover():
            self.fail("managed recovery must not run while autonomous")

        self.assertEqual(await gate.reconcile(recover), "autonomous")
        manager.hands_off = True
        # rd_autonomous_mode clears the manager bit only after positive edge EXIT ACK.
        manager._edge_autonomous = False

        self.assertTrue(await manager.return_pb_control())

        self.assertEqual(manager.return_calls, 1)
        self.assertTrue(gate.managed_actuation_ready)
        self.assertFalse(gate.candidate_autonomous)
        self.assertTrue(await app.hass.turn_on("switch.test"))

    async def test_plain_hands_off_return_does_not_bypass_unresolved_startup_recovery(self):
        _app, manager, _guard, gate = self.make()
        manager.hands_off = True

        self.assertTrue(await manager.return_pb_control())

        self.assertFalse(gate.managed_actuation_ready)
        self.assertIsNone(gate.candidate_autonomous)

    async def test_failed_managed_recovery_stays_blocked_without_retry_loop(self):
        app, _manager, _guard, gate = self.make()
        recovery_calls = 0

        async def recover():
            nonlocal recovery_calls
            recovery_calls += 1
            return False

        result = await gate.reconcile(recover)

        self.assertEqual(result, "blocked")
        self.assertEqual(recovery_calls, 1)
        self.assertFalse(gate.reconciliation_complete)
        self.assertFalse(gate.managed_actuation_ready)
        with self.assertRaisesRegex(RuntimeSafetyError, "recovery incomplete"):
            await app.hass.turn_on("switch.test")

    async def test_unreconciled_get_all_live_is_raw_not_managed_pipeline(self):
        app, _manager, guard, gate = self.make()
        guard.raw = {"switch": "on", "autonomous_mode": "on", "raw_only": 1}

        live = await app.hass.get_all_live()

        self.assertEqual(live["raw_only"], 1)
        self.assertEqual(app.hass.get_all_calls, 0)
        self.assertFalse(gate.managed_actuation_ready)

    def test_parser_never_infers_mode_from_unknown_values(self):
        for raw in (
            {},
            {"autonomous_mode": None},
            {"autonomous_mode": "unknown"},
            {"autonomous_mode": "unavailable"},
            {"autonomous_mode": 2},
        ):
            with self.subTest(raw=raw):
                self.assertIsNone(RdStartupAuthorityGate.parse_explicit(raw))


if __name__ == "__main__":
    unittest.main()
