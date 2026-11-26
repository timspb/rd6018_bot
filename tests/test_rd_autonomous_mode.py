import asyncio
import types
import unittest

from runtime.safety.edge_lease import EdgeSafetyLeaseConfig
from rd_autonomous_mode import (
    RdAutonomousModeCoordinator,
    install_rd_autonomous_final_hmi,
    install_rd_autonomous_mode,
)
from runtime.safety.runtime_guard import RuntimeSafetyError


class DummyLease:
    def __init__(self):
        self.config = EdgeSafetyLeaseConfig()


class DummyGuard:
    def __init__(self):
        self.edge_lease_enforced = True
        self.edge_safety_lease = DummyLease()
        self._off_unconfirmed = False
        self._orphan_output_seen_at = 123.0
        self.live = {"switch": "off", "autonomous_mode": "off"}

    async def _raw_live(self):
        return dict(self.live)


class DummyManager:
    def __init__(self):
        self.guard = DummyGuard()
        self.mode = types.SimpleNamespace()
        self.hands_off = False
        self.pb_managed = True
        self._record_edge_autonomous(False)
        self.enter_calls = 0
        self.return_calls = 0
        self.sessions = False
        self.writes = []
        self.clear_calls = 0
        self.off_calls = 0

    async def operator_output_off(self, entity_id=None):
        self.off_calls += 1
        return True

    @property
    def edge_autonomous(self):
        return bool(self._edge_autonomous)

    def _managed_session_active(self):
        return self.sessions

    def _record_edge_autonomous(self, active):
        if not isinstance(active, bool):
            raise TypeError("edge autonomous observation must be explicit")
        self._edge_autonomous = active

    def _observe_edge_mode(self, live):
        raw = live.get("autonomous_mode")
        if raw in (True, "on", "true", "1", 1):
            self._record_edge_autonomous(True)
        elif raw in (False, "off", "false", "0", 0):
            self._record_edge_autonomous(False)

    async def enter_hands_off(self):
        self.enter_calls += 1
        self.hands_off = True
        self.pb_managed = False
        return True

    async def return_pb_control(self):
        self.return_calls += 1
        self.hands_off = False
        self.pb_managed = True
        return True

    def _write_mode(self, mode):
        self.writes.append(mode)

    def _clear_stale_auto_restore_authority(self):
        self.clear_calls += 1


class FakeEdge:
    def __init__(self):
        self.autonomous = False
        self.enter_calls = 0
        self.exit_calls = 0
        self.fail_enter = False
        self.cancel_enter = False
        self.fail_exit = False
        self.command_may_have_executed = False
        self.enter_started = None
        self.allow_enter = None

    async def read_autonomous(self):
        return self.autonomous

    async def enter(self):
        self.enter_calls += 1
        self.command_may_have_executed = True
        if self.enter_started is not None:
            self.enter_started.set()
            await self.allow_enter.wait()
        if self.cancel_enter:
            self.autonomous = True
            raise asyncio.CancelledError()
        if self.fail_enter:
            # Model ESP applying the persistent bit while the ACK is lost.
            self.autonomous = True
            raise RuntimeError("edge enter ACK lost after command")
        self.autonomous = True
        return object()

    async def exit(self):
        self.exit_calls += 1
        if self.fail_exit:
            raise RuntimeError("edge exit failed")
        self.autonomous = False
        return object()


class RdAutonomousModeTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def make():
        manager = DummyManager()
        coordinator = RdAutonomousModeCoordinator(types.SimpleNamespace(), manager)
        coordinator.edge = FakeEdge()
        return manager, coordinator

    def test_edge_mode_mirror_has_one_state_owner(self):
        from pathlib import Path
        root = Path(__file__).resolve().parents[1]
        owner_source = (root / "rd_control_mode.py").read_text(encoding="utf-8")
        autonomous_source = (root / "rd_autonomous_mode.py").read_text(encoding="utf-8")
        startup_source = (root / "rd_startup_authority.py").read_text(encoding="utf-8")
        self.assertIn("def _record_edge_autonomous(", owner_source)
        self.assertIn("self._edge_autonomous = active", owner_source)
        self.assertNotIn("_edge_autonomous =", autonomous_source)
        self.assertNotIn("_edge_autonomous =", startup_source)
        self.assertIn("_record_edge_autonomous(", autonomous_source)
        self.assertIn("_record_edge_autonomous(", startup_source)

    async def test_deferred_runtime_lease_is_bound_on_first_use(self):
        manager = DummyManager()
        guard = manager.guard
        guard.edge_lease_enforced = False
        guard.edge_safety_lease = None
        attempts = []

        def bind_runtime_lease():
            attempts.append(True)
            guard.edge_safety_lease = DummyLease()
            guard.edge_lease_enforced = True
            return guard.edge_safety_lease

        guard.ensure_edge_safety_lease = bind_runtime_lease
        coordinator = RdAutonomousModeCoordinator(types.SimpleNamespace(), manager)
        self.assertIsNone(coordinator.edge)
        resolved = coordinator._require_edge()
        self.assertIs(resolved, coordinator.edge)
        self.assertIs(resolved.lease, guard.edge_safety_lease)
        self.assertIs(coordinator._require_edge(), resolved)
        self.assertEqual(attempts, [True])

    async def test_deferred_lease_never_bypasses_disabled_enforcement(self):
        manager = DummyManager()
        manager.guard.edge_lease_enforced = False
        manager.guard.edge_safety_lease = None
        manager.guard.ensure_edge_safety_lease = lambda: DummyLease()
        coordinator = RdAutonomousModeCoordinator(types.SimpleNamespace(), manager)
        with self.assertRaisesRegex(RuntimeSafetyError, "configured edge firmware authority"):
            coordinator._require_edge()
        self.assertIsNone(coordinator.edge)
        self.assertEqual(manager.enter_calls, 0)

    async def test_enter_crosses_hands_off_before_edge_autonomous(self):
        manager, coordinator = self.make()
        self.assertTrue(await coordinator.enter())
        self.assertEqual(manager.enter_calls, 1)
        self.assertTrue(manager.hands_off)
        self.assertFalse(manager.pb_managed)
        self.assertTrue(manager._edge_autonomous)
        self.assertEqual(coordinator.edge.enter_calls, 1)
        self.assertIsNone(manager.guard._orphan_output_seen_at)

    async def test_entry_requires_confirmed_output_off(self):
        manager, coordinator = self.make()
        manager.guard.live["switch"] = "on"
        with self.assertRaisesRegex(RuntimeSafetyError, "confirmed Output OFF"):
            await coordinator.enter()
        self.assertEqual(manager.enter_calls, 0)
        self.assertEqual(coordinator.edge.enter_calls, 0)

    async def test_entry_rejects_stale_output_off_evidence(self):
        manager, coordinator = self.make()
        manager.guard.live["_meta"] = {
            "switch": {"status": "unavailable"},
        }
        with self.assertRaisesRegex(RuntimeSafetyError, "fresh confirmed Output OFF"):
            await coordinator.enter()
        self.assertEqual(manager.enter_calls, 0)
        self.assertEqual(coordinator.edge.enter_calls, 0)

    async def test_ambiguous_edge_entry_never_rolls_back_bot_authority(self):
        manager, coordinator = self.make()
        coordinator.edge.fail_enter = True
        with self.assertRaisesRegex(RuntimeSafetyError, "RD remains HANDS_OFF"):
            await coordinator.enter()
        self.assertTrue(manager.hands_off)
        self.assertFalse(manager.pb_managed)
        self.assertEqual(manager.return_calls, 0)
        self.assertFalse(manager._edge_autonomous)

    async def test_generic_pb_restore_cannot_interleave_during_edge_enter(self):
        manager = DummyManager()
        app = types.SimpleNamespace()
        coordinator = install_rd_autonomous_mode(app, manager, install_ui=False)
        coordinator.edge = FakeEdge()
        coordinator.edge.enter_started = asyncio.Event()
        coordinator.edge.allow_enter = asyncio.Event()

        enter_task = asyncio.create_task(coordinator.enter())
        await asyncio.wait_for(coordinator.edge.enter_started.wait(), timeout=1.0)

        self.assertTrue(manager.hands_off)
        self.assertTrue(coordinator._entry_transition_pending)
        with self.assertRaisesRegex(RuntimeSafetyError, "transition is in progress"):
            await manager.return_pb_control()
        with self.assertRaisesRegex(RuntimeSafetyError, "transition is in progress"):
            await manager.operator_output_off()
        self.assertEqual(manager.return_calls, 0)
        self.assertEqual(manager.off_calls, 0)

        coordinator.edge.allow_enter.set()
        self.assertTrue(await asyncio.wait_for(enter_task, timeout=1.0))
        self.assertFalse(coordinator._entry_transition_pending)
        self.assertTrue(manager.edge_autonomous)
        self.assertTrue(manager.hands_off)

    async def test_cancelled_edge_enter_keeps_hands_off_until_explicit_exit(self):
        manager = DummyManager()
        app = types.SimpleNamespace()
        coordinator = install_rd_autonomous_mode(app, manager, install_ui=False)
        coordinator.edge = FakeEdge()
        coordinator.edge.cancel_enter = True

        with self.assertRaises(asyncio.CancelledError):
            await coordinator.enter()

        self.assertFalse(coordinator._entry_transition_pending)
        self.assertTrue(coordinator._entry_uncertain)
        self.assertTrue(coordinator.edge.autonomous)
        self.assertTrue(manager.hands_off)
        self.assertFalse(manager.pb_managed)
        with self.assertRaisesRegex(RuntimeSafetyError, "entry outcome is unconfirmed"):
            await manager.return_pb_control()
        self.assertEqual(manager.return_calls, 0)

        self.assertTrue(await coordinator.exit())
        self.assertFalse(coordinator._entry_uncertain)
        self.assertFalse(coordinator.edge.autonomous)
        self.assertTrue(manager.pb_managed)
        self.assertEqual(manager.return_calls, 1)

    async def test_ambiguous_entry_blocks_generic_restore_and_bot_off_until_explicit_exit(self):
        manager = DummyManager()
        app = types.SimpleNamespace()
        coordinator = install_rd_autonomous_mode(app, manager, install_ui=False)
        coordinator.edge = FakeEdge()
        coordinator.edge.fail_enter = True

        with self.assertRaisesRegex(RuntimeSafetyError, "not positively acknowledged"):
            await coordinator.enter()

        self.assertTrue(coordinator._entry_uncertain)
        self.assertTrue(coordinator.edge.autonomous)
        self.assertTrue(manager.hands_off)
        self.assertFalse(manager.pb_managed)
        self.assertFalse(manager.edge_autonomous)

        with self.assertRaisesRegex(RuntimeSafetyError, "entry outcome is unconfirmed"):
            await manager.return_pb_control()
        with self.assertRaisesRegex(RuntimeSafetyError, "outcome is unconfirmed"):
            await manager.operator_output_off()
        self.assertEqual(manager.return_calls, 0)
        self.assertEqual(manager.off_calls, 0)

        self.assertTrue(await coordinator.exit())
        self.assertFalse(coordinator._entry_uncertain)
        self.assertFalse(coordinator.edge.autonomous)
        self.assertTrue(manager.pb_managed)
        self.assertEqual(coordinator.edge.exit_calls, 1)
        self.assertEqual(manager.return_calls, 1)

    def test_app_aware_keyboard_preserves_autonomous_filter_without_global_patch(self):
        from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
        import operator_hmi
        from runtime.ui.components.hmi_state import HmiAuthority, HmiProcessState

        original_builder = operator_hmi.build_operator_keyboard
        managers = [DummyManager(), DummyManager()]
        managers[0]._edge_autonomous = True
        coordinators = [
            RdAutonomousModeCoordinator(types.SimpleNamespace(), manager)
            for manager in managers
        ]
        coordinators[0]._entry_uncertain = True
        apps = [types.SimpleNamespace(), types.SimpleNamespace()]
        states = [
            types.SimpleNamespace(
                process_state=HmiProcessState.HANDS_OFF,
                authority=HmiAuthority.EXTERNAL,
                output_on=False,
                _output_state_known=True,
            )
            for _ in apps
        ]
        base = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="PB", callback_data="rd_hands_off_disable"),
            InlineKeyboardButton(text="OFF", callback_data="rd_hands_off_output_off"),
            InlineKeyboardButton(text="adopt", callback_data="rd_managed_adopt"),
            InlineKeyboardButton(text="mix", callback_data="rd_live_mix"),
            InlineKeyboardButton(text="charge", callback_data="charge_modes"),
        ]])
        for app, coordinator in zip(apps, coordinators):
            install_rd_autonomous_final_hmi(app, coordinator)
        self.assertIs(operator_hmi.build_operator_keyboard, original_builder)

        # Invoke the pure app-aware keyboard owner with supplied actions' already
        # rendered shape so both normal and action-view entry paths use the same filter.
        from runtime.ui.components.hmi_action_keyboard import _autonomous_keyboard
        rendered = _autonomous_keyboard(apps[0], states[0], base)
        callbacks = [button.callback_data for row in rendered.inline_keyboard for button in row]
        self.assertEqual(callbacks, ["rd_autonomous_exit"])
        self.assertIn("Проверить AUTONOMOUS", rendered.inline_keyboard[0][0].text)
        self.assertEqual(managers[0].writes, [])
        self.assertEqual(
            [button.callback_data for row in _autonomous_keyboard(apps[1], states[1], base).inline_keyboard for button in row],
            ["rd_hands_off_disable", "rd_hands_off_output_off", "rd_managed_adopt", "rd_live_mix", "charge_modes"],
        )

        # Unknown Output is never accepted as known OFF; no autonomous exit is added.
        states[0]._output_state_known = False
        unknown = _autonomous_keyboard(apps[0], states[0], base)
        self.assertNotIn("rd_autonomous_exit", [button.callback_data for row in unknown.inline_keyboard for button in row])
        self.assertNotIn("rd_hands_off_disable", [button.callback_data for row in unknown.inline_keyboard for button in row])

        # Pending and uncertain entry use the same OFF-only reconciliation path;
        # ON or unknown physical state never exposes its callback.
        pending_app = types.SimpleNamespace()
        pending_manager = DummyManager()
        pending_coordinator = RdAutonomousModeCoordinator(pending_app, pending_manager)
        pending_coordinator._entry_transition_pending = True
        install_rd_autonomous_final_hmi(pending_app, pending_coordinator)
        pending_state = types.SimpleNamespace(
            process_state=HmiProcessState.HANDS_OFF,
            output_on=False,
            _output_state_known=True,
        )
        pending = _autonomous_keyboard(pending_app, pending_state, base)
        self.assertEqual(
            [button.callback_data for row in pending.inline_keyboard for button in row],
            ["rd_autonomous_exit"],
        )
        pending_state.output_on = True
        self.assertNotIn(
            "rd_autonomous_exit",
            [button.callback_data for row in _autonomous_keyboard(pending_app, pending_state, base).inline_keyboard for button in row],
        )

    def test_pb_managed_verified_off_gets_autonomous_entry_and_reinstall_is_idempotent(self):
        from runtime.ui.components.hmi_state import HmiAuthority, HmiProcessState
        from runtime.ui.components.hmi_action_keyboard import _autonomous_keyboard
        from runtime.ui.telegram.renderer import render_callback_rows

        manager = DummyManager()
        app = types.SimpleNamespace()
        coordinator = RdAutonomousModeCoordinator(app, manager)
        install_rd_autonomous_final_hmi(app, coordinator)
        marker = app.rd_autonomous_mode
        install_rd_autonomous_final_hmi(app, coordinator)
        self.assertIs(app.rd_autonomous_mode, marker)
        self.assertIs(app.rd_autonomous_mode, coordinator)
        state = types.SimpleNamespace(
            process_state=HmiProcessState.IDLE, authority=HmiAuthority.NONE,
            output_on=False, _output_state_known=True,
        )
        markup = _autonomous_keyboard(app, state, render_callback_rows([[('refresh', 'operator_refresh')]]))
        self.assertEqual(
            [button.callback_data for row in markup.inline_keyboard for button in row],
            ["operator_refresh", "rd_autonomous_confirm"],
        )
        state._output_state_known = False
        self.assertNotIn(
            "rd_autonomous_confirm",
            [button.callback_data for row in _autonomous_keyboard(app, state, markup).inline_keyboard for button in row],
        )

    async def test_observer_start_guard_remains_applicable_under_edge_autonomous(self):
        class Observer:
            def __init__(self):
                self.calls = 0

            async def start(self):
                self.calls += 1

        manager = DummyManager()
        manager._edge_autonomous = True
        observer = Observer()
        app = types.SimpleNamespace(rd_live_mix_observer=observer)
        coordinator = RdAutonomousModeCoordinator(app, manager)
        install_rd_autonomous_final_hmi(app, coordinator)
        with self.assertRaisesRegex(RuntimeSafetyError, "observer is disabled"):
            await observer.start()
        self.assertEqual(observer.calls, 0)

    async def test_exit_is_off_only_and_returns_managed_idle_after_edge_ack(self):
        manager, coordinator = self.make()
        manager.hands_off = True
        manager.pb_managed = False
        manager._edge_autonomous = True
        manager.guard.live["autonomous_mode"] = "on"
        coordinator.edge.autonomous = True
        self.assertTrue(await coordinator.exit())
        self.assertEqual(coordinator.edge.exit_calls, 1)
        self.assertEqual(manager.return_calls, 1)
        self.assertFalse(manager._edge_autonomous)
        self.assertTrue(manager.pb_managed)

    async def test_failed_exit_keeps_autonomous_authority(self):
        manager, coordinator = self.make()
        manager.hands_off = True
        manager.pb_managed = False
        manager._edge_autonomous = True
        manager.guard.live["autonomous_mode"] = "on"
        coordinator.edge.autonomous = True
        coordinator.edge.fail_exit = True
        with self.assertRaisesRegex(RuntimeSafetyError, "not positively acknowledged"):
            await coordinator.exit()
        self.assertTrue(manager._edge_autonomous)
        self.assertTrue(manager.hands_off)
        self.assertEqual(manager.return_calls, 0)

    async def test_active_managed_session_blocks_autonomous_entry(self):
        manager, coordinator = self.make()
        manager.sessions = True
        with self.assertRaisesRegex(RuntimeSafetyError, "active managed session"):
            await coordinator.enter()
        self.assertEqual(manager.enter_calls, 0)

    async def test_stale_generic_pb_restore_cannot_bypass_edge_autonomous(self):
        manager = DummyManager()
        app = types.SimpleNamespace()
        install_rd_autonomous_mode(app, manager, install_ui=False)
        manager.hands_off = True
        manager.pb_managed = False
        manager._edge_autonomous = True

        with self.assertRaisesRegex(RuntimeSafetyError, "explicit AUTONOMOUS exit"):
            await manager.return_pb_control()

        self.assertEqual(manager.return_calls, 0)
        self.assertTrue(manager.hands_off)


if __name__ == "__main__":
    unittest.main()
