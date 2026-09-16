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
from runtime_safety import RuntimeSafetyError


class DummyCallbackRegistry:
    def __call__(self, *args, **kwargs):
        def decorator(func):
            return func
        return decorator


class DummyRouter:
    def __init__(self):
        self.callback_query = DummyCallbackRegistry()


class FakeLease:
    def __init__(self, *, armed):
        self.armed = bool(armed)
        self.suspended = False
        self.released = False
        self.release_error = None
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
        return types.SimpleNamespace(generation=7)

    async def release_to_hands_off(self, *, expected_generation=None):
        if self.release_error is not None:
            raise self.release_error
        if expected_generation != 7:
            raise RuntimeError("generation mismatch")
        self.released = True
        self.armed = False
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
        self.original_keyboard = hmi.build_operator_keyboard
        hmi.build_operator_keyboard = lambda app, state: InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="info", callback_data="operator_details")],
                [InlineKeyboardButton(text="refresh", callback_data="operator_refresh")],
            ]
        )

    def tearDown(self):
        hmi.build_operator_keyboard = self.original_keyboard

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

        callbacks = self._callbacks(hmi.build_operator_keyboard(app, state))

        self.assertIn("rd_ownership_adopt", callbacks)
        self.assertIn("rd_ownership_hands_off", callbacks)
        self.assertIn("rd_ownership_output_off", callbacks)

    def test_idle_exposes_general_purpose_psu_hands_off(self):
        app, manager = self._app()
        install_rd_ownership_recovery(app, manager)
        state = self._state(
            hmi.HmiProcessState.IDLE,
            hmi.HmiAuthority.NONE,
            output_on=False,
        )

        callbacks = self._callbacks(hmi.build_operator_keyboard(app, state))
        self.assertIn("rd_ownership_hands_off", callbacks)

    def test_hands_off_off_exposes_return_to_pb_control(self):
        app, manager = self._app(hands_off=True)
        install_rd_ownership_recovery(app, manager)
        state = self._state(
            hmi.HmiProcessState.HANDS_OFF,
            hmi.HmiAuthority.EXTERNAL,
            output_on=False,
        )

        callbacks = self._callbacks(hmi.build_operator_keyboard(app, state))
        self.assertIn("rd_hands_off_disable", callbacks)

    def test_active_managed_session_hides_rd_release_button(self):
        app, manager = self._app()
        app.charge_controller.is_active = True
        install_rd_ownership_recovery(app, manager)
        state = self._state(
            hmi.HmiProcessState.RUNNING,
            hmi.HmiAuthority.AUTO,
            output_on=True,
        )

        callbacks = self._callbacks(hmi.build_operator_keyboard(app, state))
        self.assertNotIn("rd_hands_off_release_confirm", callbacks)


if __name__ == "__main__":
    unittest.main()
