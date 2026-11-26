import asyncio
import tempfile
import types
import unittest
from datetime import datetime, timezone

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

import operator_hmi as hmi
from rd_control_mode import RdControlMode
from rd_ownership_recovery import (
    install_rd_ownership_recovery,
    release_unmanaged_live_output_to_hands_off,
)
from runtime.safety.runtime_guard import RuntimeSafetyError
from runtime.ui.components.hmi_action_keyboard import _ownership_recovery_keyboard


class DummyCallbackRegistry:
    def __init__(self):
        self.routes = []

    def __call__(self, *args, **kwargs):
        def decorator(func):
            self.routes.append(func)
            return func
        return decorator


class DummyRouter:
    def __init__(self):
        self.callback_query = DummyCallbackRegistry()
        self.routes = self.callback_query.routes


class FakeLease:
    def __init__(self, *, armed):
        self.armed = bool(armed)
        self.suspended = False
        self.released = False
        self.release_error = None
        self.cancel_prepare = False
        self.cancel_release = False
        self.config = types.SimpleNamespace(max_modbus_age_s=20.0)

    async def read_state(self):
        return types.SimpleNamespace(
            armed=self.armed,
            tripped=False,
            boot_quarantine=False,
            generation=7,
            modbus_age_s=0.5,
            remaining_s=500.0 if self.armed else 0.0,
        )

    def _fresh_modbus(self, state):
        return state.modbus_age_s <= 20.0

    def suspend_renewals(self):
        self.suspended = True

    def resume_renewals(self):
        self.suspended = False

    async def prepare_hands_off_release(self):
        if not self.suspended or not self.armed:
            raise RuntimeError("not prepared")
        if self.cancel_prepare:
            raise asyncio.CancelledError()
        return types.SimpleNamespace(generation=7)

    async def release_to_hands_off(self, *, expected_generation=None):
        if self.release_error is not None:
            raise self.release_error
        if expected_generation != 7:
            raise RuntimeError("generation mismatch")
        self.released = True
        self.armed = False
        if self.cancel_release:
            raise asyncio.CancelledError()
        return await self.read_state()


class FakeGuard:
    def __init__(self, lease):
        now = datetime.now(timezone.utc).isoformat()
        self.live = {
            "switch": "on",
            "_meta": {
                "switch": {
                    "status": "ok",
                    "last_reported": now,
                    "last_updated": now,
                }
            },
        }
        self.edge_lease_enforced = lease is not None
        self.edge_safety_lease = lease
        self._off_unconfirmed = False
        self._orphan_output_seen_at = 1.0

    async def _raw_live(self):
        return dict(self.live)

    @staticmethod
    def _output_evidence(live):
        raw = str(live.get("switch") or "").lower()
        state = True if raw == "on" else False if raw == "off" else None
        return types.SimpleNamespace(state=state)


class FakeManager:
    def __init__(self, guard):
        self.guard = guard
        self.mode = RdControlMode.PB_MANAGED
        self._transition_lock = asyncio.Lock()
        self._release_in_progress = False
        self.writes = []
        self.cleared_restore = 0

    @property
    def hands_off(self):
        return self.mode is RdControlMode.HANDS_OFF

    @property
    def pb_managed(self):
        return self.mode is RdControlMode.PB_MANAGED

    @property
    def release_in_progress(self):
        return bool(self._release_in_progress)

    def _write_mode(self, mode):
        self.writes.append(mode)

    def _clear_stale_auto_restore_authority(self):
        self.cleared_restore += 1


class OwnershipRecoveryTransactionTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _app(manager):
        return types.SimpleNamespace(
            charge_controller=types.SimpleNamespace(is_active=False),
            manual_session_manager=types.SimpleNamespace(is_active=False),
            rd_control_mode_manager=manager,
        )

    async def test_unarmed_external_output_can_commit_hands_off_without_actuation(self):
        lease = FakeLease(armed=False)
        guard = FakeGuard(lease)
        manager = FakeManager(guard)
        app = self._app(manager)

        self.assertTrue(await release_unmanaged_live_output_to_hands_off(app, manager))

        self.assertTrue(manager.hands_off)
        self.assertEqual(manager.writes, [RdControlMode.HANDS_OFF])
        self.assertFalse(lease.released)
        self.assertEqual(manager.cleared_restore, 1)
        self.assertIsNone(guard._orphan_output_seen_at)

    async def test_armed_orphan_lease_uses_live_release_without_touching_output(self):
        lease = FakeLease(armed=True)
        guard = FakeGuard(lease)
        manager = FakeManager(guard)
        app = self._app(manager)

        self.assertTrue(await release_unmanaged_live_output_to_hands_off(app, manager))

        self.assertTrue(manager.hands_off)
        self.assertTrue(lease.released)
        self.assertTrue(lease.suspended)

    async def test_precommit_cancellation_resumes_lease_and_keeps_pb_authority(self):
        lease = FakeLease(armed=True)
        lease.cancel_prepare = True
        guard = FakeGuard(lease)
        manager = FakeManager(guard)
        app = self._app(manager)

        with self.assertRaises(asyncio.CancelledError):
            await release_unmanaged_live_output_to_hands_off(app, manager)

        self.assertTrue(manager.pb_managed)
        self.assertEqual(manager.writes, [])
        self.assertFalse(manager.release_in_progress)
        self.assertFalse(lease.suspended)
        self.assertFalse(lease.released)

    async def test_postcommit_cancellation_keeps_durable_hands_off_without_resume(self):
        lease = FakeLease(armed=True)
        lease.cancel_release = True
        guard = FakeGuard(lease)
        manager = FakeManager(guard)
        app = self._app(manager)

        with self.assertRaises(asyncio.CancelledError):
            await release_unmanaged_live_output_to_hands_off(app, manager)

        self.assertTrue(manager.hands_off)
        self.assertEqual(manager.writes, [RdControlMode.HANDS_OFF])
        self.assertFalse(manager.release_in_progress)
        self.assertTrue(lease.suspended)
        self.assertTrue(lease.released)
        self.assertEqual(manager.cleared_restore, 1)

    async def test_ambiguous_edge_ack_never_rolls_back_durable_hands_off(self):
        lease = FakeLease(armed=True)
        lease.release_error = RuntimeError("synthetic lost ack")
        guard = FakeGuard(lease)
        manager = FakeManager(guard)
        app = self._app(manager)

        with self.assertRaisesRegex(RuntimeSafetyError, "durably active"):
            await release_unmanaged_live_output_to_hands_off(app, manager)

        self.assertTrue(manager.hands_off)
        self.assertEqual(manager.writes, [RdControlMode.HANDS_OFF])


class OwnershipRecoveryHmiTests(unittest.TestCase):
    def setUp(self):
        self.base_markup = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="info", callback_data="operator_details")],
                [InlineKeyboardButton(text="refresh", callback_data="operator_refresh")],
            ]
        )

    def _keyboard(self, app, state, *, actions=None):
        return _ownership_recovery_keyboard(app, state, self.base_markup, actions=actions)

    @staticmethod
    def _app(*, hands_off=False, adoption=True):
        manager = types.SimpleNamespace(
            hands_off=hands_off,
            pb_managed=not hands_off,
        )
        app = types.SimpleNamespace(
            router=DummyRouter(),
            rd_control_mode_manager=manager,
            charge_controller=types.SimpleNamespace(is_active=False),
            manual_session_manager=types.SimpleNamespace(is_active=False),
            rd_managed_live_adoption=(
                types.SimpleNamespace(active=False, off_pending=False) if adoption else None
            ),
            _check_chat_and_respond=lambda call: True,
        )
        return app, manager

    @staticmethod
    def _state(process_state, authority, *, output_on):
        return hmi.OperatorHmiState(
            process_state=process_state,
            authority=authority,
            title="",
            output_on=output_on,
            regulator="—",
            battery_label="",
            battery_voltage_v=None,
            current_a=None,
            power_w=None,
            battery_temp_c=None,
            psu_temp_c=None,
            target_voltage_v=None,
            current_limit_a=None,
            progress="",
            safety="",
        )

    @staticmethod
    def _callbacks(markup):
        return [
            button.callback_data
            for row in markup.inline_keyboard
            for button in row
            if button.callback_data
        ]

    def test_foreign_output_exposes_adopt_hands_off_and_verified_off(self):
        app, manager = self._app()
        install_rd_ownership_recovery(app, manager)
        state = self._state(
            hmi.HmiProcessState.CONTAINMENT,
            hmi.HmiAuthority.CONTAINMENT,
            output_on=True,
        )

        callbacks = self._callbacks(self._keyboard(app, state))

        self.assertIn("rd_ownership_adopt", callbacks)
        self.assertIn("rd_ownership_hands_off", callbacks)
        self.assertIn("rd_ownership_output_off", callbacks)
        self.assertEqual(
            [[button.callback_data for button in row] for row in self._keyboard(app, state).inline_keyboard],
            [
                ["rd_ownership_adopt"],
                ["rd_ownership_hands_off"],
                ["rd_ownership_output_off"],
                ["operator_details"],
                ["operator_refresh"],
            ],
        )

    def test_idle_exposes_general_purpose_psu_hands_off(self):
        app, manager = self._app()
        install_rd_ownership_recovery(app, manager)
        state = self._state(
            hmi.HmiProcessState.IDLE,
            hmi.HmiAuthority.NONE,
            output_on=False,
        )

        callbacks = self._callbacks(self._keyboard(app, state))
        self.assertIn("rd_ownership_hands_off", callbacks)

    def test_ownership_keyboard_is_bound_to_installed_app(self):
        from application.operator_actions import OperatorActionsView

        app, manager = self._app()
        foreign, _ = self._app()
        install_rd_ownership_recovery(app, manager)
        state = self._state(hmi.HmiProcessState.IDLE, hmi.HmiAuthority.NONE, output_on=False)
        actions = OperatorActionsView.for_state("IDLE", safety_allowed=True)

        foreign_callbacks = self._callbacks(self._keyboard(foreign, state, actions=actions))
        self.assertNotIn("rd_ownership_hands_off", foreign_callbacks)
        self.assertIn("operator_refresh", foreign_callbacks)
        own_callbacks = self._callbacks(self._keyboard(app, state, actions=actions))
        self.assertIn("rd_ownership_hands_off", own_callbacks)

    def test_hands_off_off_exposes_return_to_pb_control(self):
        app, manager = self._app(hands_off=True)
        install_rd_ownership_recovery(app, manager)
        state = self._state(
            hmi.HmiProcessState.HANDS_OFF,
            hmi.HmiAuthority.EXTERNAL,
            output_on=False,
        )

        callbacks = self._callbacks(self._keyboard(app, state))
        self.assertIn("rd_hands_off_disable", callbacks)
        self.assertEqual(
            [(button.text, button.callback_data) for button in self._keyboard(app, state).inline_keyboard[0]],
            [("🔒 Вернуть контроль заряда", "rd_hands_off_disable")],
        )

    def test_hands_off_on_never_exposes_pb_restore(self):
        app, manager = self._app(hands_off=True)
        install_rd_ownership_recovery(app, manager)
        state = self._state(hmi.HmiProcessState.HANDS_OFF, hmi.HmiAuthority.EXTERNAL, output_on=True)

        self.assertNotIn("rd_hands_off_disable", self._callbacks(self._keyboard(app, state)))

    def test_active_managed_session_hides_rd_release_button(self):
        app, manager = self._app()
        app.charge_controller.is_active = True
        install_rd_ownership_recovery(app, manager)
        state = self._state(
            hmi.HmiProcessState.RUNNING,
            hmi.HmiAuthority.AUTO,
            output_on=True,
        )

        callbacks = self._callbacks(self._keyboard(app, state))
        self.assertNotIn("rd_hands_off_release_confirm", callbacks)

    def test_snapshot_actions_path_exposes_hands_off(self):
        from application.operator_actions import OperatorActionsView

        app, manager = self._app()
        install_rd_ownership_recovery(app, manager)
        state = self._state(hmi.HmiProcessState.IDLE, hmi.HmiAuthority.NONE, output_on=False)
        actions = OperatorActionsView.for_state("IDLE", safety_allowed=True)

        callbacks = self._callbacks(self._keyboard(app, state, actions=actions))

        self.assertIn("rd_ownership_hands_off", callbacks)

    def test_snapshot_actions_path_exposes_active_release(self):
        from application.operator_actions import OperatorActionsView

        app, manager = self._app()
        app.charge_controller.is_active = True
        install_rd_ownership_recovery(app, manager)
        state = self._state(hmi.HmiProcessState.RUNNING, hmi.HmiAuthority.AUTO, output_on=True)
        actions = OperatorActionsView.for_state("CHARGING", safety_allowed=True)

        callbacks = self._callbacks(self._keyboard(app, state, actions=actions))

        self.assertIn("rd_hands_off_release_confirm", callbacks)
        self.assertEqual(
            [(button.text, button.callback_data) for button in self._keyboard(app, state, actions=actions).inline_keyboard[0]],
            [("🔓 Отпустить РД", "rd_hands_off_release_confirm")],
        )

    def test_snapshot_release_requires_pb_managed_active_session(self):
        from application.operator_actions import OperatorActionsView

        app, manager = self._app(hands_off=True)
        app.charge_controller.is_active = True
        install_rd_ownership_recovery(app, manager)
        state = self._state(hmi.HmiProcessState.RUNNING, hmi.HmiAuthority.AUTO, output_on=True)
        actions = OperatorActionsView.for_state("CHARGING", safety_allowed=True)

        self.assertNotIn("rd_hands_off_release_confirm", self._callbacks(self._keyboard(app, state, actions=actions)))

    def test_idle_none_path_keeps_ownership_button_at_end_and_uses_each_apps_manager(self):
        first, _ = self._app()
        second, second_manager = self._app(hands_off=True)
        install_rd_ownership_recovery(first, first.rd_control_mode_manager)
        route_count = len(first.router.routes)
        self.assertGreater(route_count, 0)
        install_rd_ownership_recovery(first, first.rd_control_mode_manager)
        self.assertEqual(len(first.router.routes), route_count)
        install_rd_ownership_recovery(second, second_manager)
        state = self._state(hmi.HmiProcessState.IDLE, hmi.HmiAuthority.NONE, output_on=False)

        first_markup = self._keyboard(first, state)
        second_markup = self._keyboard(second, state)
        self.assertEqual(
            [[button.callback_data for button in row] for row in first_markup.inline_keyboard],
            [["operator_details"], ["operator_refresh"], ["rd_ownership_hands_off"]],
        )
        self.assertEqual(self._callbacks(second_markup), ["operator_details", "operator_refresh"])
        self.assertEqual(len(first.router.routes), len(second.router.routes))

    def test_unknown_output_filter_removes_restore_and_containment_actions(self):
        from operator_output_truth import filter_keyboard_for_output_truth

        app, _manager = self._app(hands_off=True)
        install_rd_ownership_recovery(app, app.rd_control_mode_manager)
        state = self._state(hmi.HmiProcessState.HANDS_OFF, hmi.HmiAuthority.EXTERNAL, output_on=False)
        object.__setattr__(state, "_output_state_known", False)
        markup = self._keyboard(app, state)
        filtered = filter_keyboard_for_output_truth(app, state, markup, hmi)

        self.assertNotIn("rd_hands_off_disable", self._callbacks(filtered))
        self.assertIn("rd_hands_off_output_off", self._callbacks(filtered))

    def test_autonomous_boundary_never_offers_ownership_or_bot_output_off(self):
        from operator_output_truth import filter_keyboard_for_output_truth

        app, _manager = self._app()
        install_rd_ownership_recovery(app, app.rd_control_mode_manager)
        app.rd_autonomous_mode = types.SimpleNamespace(
            manager=types.SimpleNamespace(edge_autonomous=True),
            _entry_transition_pending=False,
            _entry_uncertain=False,
        )
        state = self._state(hmi.HmiProcessState.CONTAINMENT, hmi.HmiAuthority.CONTAINMENT, output_on=True)
        markup = self._keyboard(app, state)
        filtered = filter_keyboard_for_output_truth(app, state, markup, hmi)

        callbacks = self._callbacks(filtered)
        self.assertNotIn("rd_ownership_adopt", callbacks)
        self.assertNotIn("rd_ownership_hands_off", callbacks)
        self.assertNotIn("rd_ownership_output_off", callbacks)

    def test_installer_does_not_replace_process_global_keyboard_builder(self):
        builder = hmi.build_operator_keyboard
        app, manager = self._app()

        install_rd_ownership_recovery(app, manager)

        self.assertIs(hmi.build_operator_keyboard, builder)
        self.assertNotIn("hmi.build_operator_keyboard =", __import__("inspect").getsource(install_rd_ownership_recovery))


class RegisteredOutputOffCallbackTests(unittest.IsolatedAsyncioTestCase):
    async def test_registered_output_off_reports_success_after_verified_off_and_disarm(self):
        events, registered, answers = [], [], []

        class Registry:
            def __call__(self, filter_expr):
                def register(callback):
                    registered.append(callback)
                    return callback
                return register

        class Guard:
            async def _ensure_output_off(self, reason, entity):
                events.append(("off", reason, entity))

            async def _disarm_edge_lease_best_effort(self):
                events.append(("disarm",))

        manager = types.SimpleNamespace(hands_off=False, guard=Guard())
        app = types.SimpleNamespace(
            router=types.SimpleNamespace(callback_query=Registry()),
            charge_controller=types.SimpleNamespace(is_active=False),
            manual_session_manager=types.SimpleNamespace(is_active=False),
            _check_chat_and_respond=lambda _call: _return_true(),
            ENTITY_MAP={"switch": "switch.rd6018_output"},
        )
        install_rd_ownership_recovery(app, manager)
        callback = next(fn for fn in registered if fn.__name__ == "_ownership_output_off")

        async def answer(text, **kwargs):
            answers.append((text, kwargs))

        async def message_answer(text):
            answers.append(("message", text))

        await callback(types.SimpleNamespace(
            answer=answer, message=types.SimpleNamespace(answer=message_answer)
        ))

        self.assertEqual([event[0] for event in events], ["off", "disarm"])
        self.assertEqual(events[0][1:], (
            "explicit operator shutdown of unmanaged Output", "switch.rd6018_output"
        ))
        self.assertEqual(answers[0][0], "Output OFF подтверждён")
        self.assertEqual(answers[1], (
            "message", "⏹ Output подтверждён OFF. Pb-control остаётся активным."
        ))

    async def test_registered_output_off_failure_never_reports_success_or_disarms(self):
        registered, answers = [], []

        class Registry:
            def __call__(self, filter_expr):
                def register(callback):
                    registered.append(callback)
                    return callback
                return register

        class Guard:
            async def _ensure_output_off(self, *_args):
                raise RuntimeError("synthetic verified-OFF failure")

            async def _disarm_edge_lease_best_effort(self):
                raise AssertionError("lease disarm must follow verified OFF")

        manager = types.SimpleNamespace(hands_off=False, guard=Guard())
        app = types.SimpleNamespace(
            router=types.SimpleNamespace(callback_query=Registry()),
            charge_controller=types.SimpleNamespace(is_active=False),
            manual_session_manager=types.SimpleNamespace(is_active=False),
            _check_chat_and_respond=lambda _call: _return_true(),
            ENTITY_MAP={"switch": "switch.rd6018_output"},
        )
        install_rd_ownership_recovery(app, manager)
        callback = next(fn for fn in registered if fn.__name__ == "_ownership_output_off")

        async def answer(text, **kwargs):
            answers.append((text, kwargs))

        async def message_answer(text):
            answers.append(("message", text))

        await callback(types.SimpleNamespace(
            answer=answer, message=types.SimpleNamespace(answer=message_answer)
        ))

        self.assertEqual(answers, [("synthetic verified-OFF failure", {"show_alert": True})])


async def _return_true():
    return True


if __name__ == "__main__":
    unittest.main()
