import types
import unittest
from unittest.mock import patch

import v2_mix_mode
from rd_startup_authority import (
    RdStartupAuthorityGate,
    reconcile_startup_authority,
)
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


class DummyController:
    def __init__(self):
        self.restore_calls = []
        self.start_calls = []
        self.is_active = False

    def start(self, *args, **kwargs):
        self.start_calls.append((args, kwargs))
        self.is_active = True
        return True

    def try_restore_session(self, *args, **kwargs):
        self.restore_calls.append((args, kwargs))
        self.is_active = True
        return True, "restored"


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
        controller = DummyController()
        app = types.SimpleNamespace(hass=hass, charge_controller=controller)
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

    async def test_failed_managed_recovery_is_throttled_and_eventually_reopens_control(self):
        app, _manager, _guard, gate = self.make()
        recovery_calls = 0
        sleeps = []

        async def recover():
            nonlocal recovery_calls
            recovery_calls += 1
            self.assertFalse(gate.managed_actuation_ready)
            return recovery_calls >= 2

        async def fake_sleep(delay):
            sleeps.append(delay)
            self.assertFalse(gate.managed_actuation_ready)

        with patch("rd_startup_authority.asyncio.sleep", side_effect=fake_sleep):
            result = await gate.reconcile(recover, recovery_retry_s=30.0)

        self.assertEqual(result, "managed")
        self.assertEqual(recovery_calls, 2)
        self.assertEqual(sleeps, [30.0])
        self.assertTrue(gate.managed_actuation_ready)
        self.assertTrue(await app.hass.turn_on("switch.test"))

    async def test_recovery_exception_is_throttled_and_retried_fail_closed(self):
        _app, _manager, _guard, gate = self.make()
        recovery_calls = 0
        sleeps = []

        async def recover():
            nonlocal recovery_calls
            recovery_calls += 1
            if recovery_calls == 1:
                raise OSError("transient HA failure")
            return True

        async def fake_sleep(delay):
            sleeps.append(delay)
            self.assertFalse(gate.managed_actuation_ready)

        with patch("rd_startup_authority.asyncio.sleep", side_effect=fake_sleep):
            result = await gate.reconcile(recover, recovery_retry_s=30.0)

        self.assertEqual(result, "managed")
        self.assertEqual(recovery_calls, 2)
        self.assertEqual(sleeps, [30.0])
        self.assertTrue(gate.managed_actuation_ready)

    async def test_early_legacy_restore_is_replayed_once_after_managed_recovery(self):
        app, _manager, _guard, gate = self.make()
        replay_calls = 0

        ok, message = app.charge_controller.try_restore_session(12.4, 0.0, 3.0)
        self.assertFalse(ok)
        self.assertIsNone(message)
        self.assertTrue(gate.deferred_restore_requested)
        self.assertEqual(app.charge_controller.restore_calls, [])

        async def recover():
            return True

        async def replay():
            nonlocal replay_calls
            replay_calls += 1
            app.charge_controller.try_restore_session(12.5, 0.0, 3.1)

        result = await reconcile_startup_authority(gate, recover, replay)

        self.assertEqual(result, "managed")
        self.assertEqual(replay_calls, 1)
        self.assertEqual(len(app.charge_controller.restore_calls), 1)
        self.assertEqual(app.charge_controller.restore_calls[0][0], (12.5, 0.0, 3.1))
        self.assertFalse(gate.deferred_restore_requested)

    async def test_managed_reconciliation_before_legacy_restore_does_not_double_restore(self):
        app, _manager, _guard, gate = self.make()
        replay_calls = 0

        async def recover():
            return True

        async def replay():
            nonlocal replay_calls
            replay_calls += 1

        self.assertEqual(
            await reconcile_startup_authority(gate, recover, replay),
            "managed",
        )
        self.assertEqual(replay_calls, 0)

        ok, message = app.charge_controller.try_restore_session(12.6, 0.1, 3.2)
        self.assertTrue(ok)
        self.assertEqual(message, "restored")
        self.assertEqual(len(app.charge_controller.restore_calls), 1)
        self.assertFalse(gate.deferred_restore_requested)

    async def test_autonomous_startup_discards_deferred_managed_restore(self):
        app, _manager, guard, gate = self.make()
        guard.raw["autonomous_mode"] = "on"
        replay_calls = 0

        app.charge_controller.try_restore_session(12.4, 0.0, 3.0)
        self.assertTrue(gate.deferred_restore_requested)

        async def recover():
            self.fail("managed recovery must not run in AUTONOMOUS")

        async def replay():
            nonlocal replay_calls
            replay_calls += 1

        result = await reconcile_startup_authority(gate, recover, replay)

        self.assertEqual(result, "autonomous")
        self.assertEqual(replay_calls, 0)
        self.assertEqual(app.charge_controller.restore_calls, [])
        self.assertFalse(gate.deferred_restore_requested)
        self.assertFalse(gate.managed_actuation_ready)

    async def test_transient_deferred_restore_read_failure_retries_without_duplicate_restore(self):
        app, _manager, _guard, gate = self.make()
        app.charge_controller.try_restore_session(12.4, 0.0, 3.0)
        replay_calls = 0
        sleeps = []

        async def recover():
            return True

        async def replay():
            nonlocal replay_calls
            replay_calls += 1
            if replay_calls == 1:
                raise OSError("transient live read")
            app.charge_controller.try_restore_session(12.7, 0.0, 3.3)

        async def fake_sleep(delay):
            sleeps.append(delay)
            self.assertTrue(gate.managed_actuation_ready)

        with patch("rd_startup_authority.asyncio.sleep", side_effect=fake_sleep):
            result = await reconcile_startup_authority(
                gate,
                recover,
                replay,
                retry_s=5.0,
            )

        self.assertEqual(result, "managed")
        self.assertEqual(replay_calls, 2)
        self.assertEqual(sleeps, [5.0])
        self.assertEqual(len(app.charge_controller.restore_calls), 1)
        self.assertFalse(gate.deferred_restore_requested)

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
