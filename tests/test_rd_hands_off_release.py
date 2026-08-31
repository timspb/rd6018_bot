import json
import tempfile
import types
import unittest

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from manual_mode import ManualSessionState
from rd_control_mode import RdControlMode, RdControlModeManager
from rd_hands_off_release import install_rd_hands_off_release
from runtime_safety import RuntimeSafetyError


class FakeGuard:
    def __init__(self):
        self._off_unconfirmed = False
        self._orphan_output_seen_at = 123.0
        self.edge_lease_enforced = False
        self.edge_safety_lease = None


class FakeController:
    STAGE_IDLE = "Idle"
    STAGE_MAIN = "Main"
    STAGE_MIX = "Mix"

    def __init__(self, stage="Main"):
        self.current_stage = stage
        self.is_active = True
        self.stop_calls = 0

    def stop(self, clear_session=True):
        self.stop_calls += 1
        self.current_stage = self.STAGE_IDLE
        self.is_active = False


class FakeMixAuthority:
    def __init__(self):
        self.calls = []

    def mark_terminal(self, session_id, reason):
        self.calls.append((session_id, reason))


class FakeMixController(FakeController):
    def __init__(self):
        super().__init__(self.STAGE_MIX)
        self._mix_active_authority = FakeMixAuthority()

    @staticmethod
    def _mix_authority_session_id():
        return "mix-session"


class FakeManual:
    def __init__(self):
        self.state = ManualSessionState.ACTIVE
        self.stop_reason = ""
        self.cooling_started_at = 1.0
        self._previous_voltage_v = 14.0
        self._previous_current_a = 1.0
        self.retire_calls = 0
        self.persist_calls = 0
        self.reset_calls = 0

    @property
    def is_active(self):
        return self.state in {
            ManualSessionState.ARMING,
            ManualSessionState.ACTIVE,
            ManualSessionState.COOLING,
        }

    async def _retire_runner(self):
        self.retire_calls += 1

    def _reset_delta_tracking(self):
        self.reset_calls += 1

    def _persist(self):
        self.persist_calls += 1


class FakeLease:
    def __init__(self, result):
        self.result = result
        self.disarm_calls = 0

    async def disarm(self):
        self.disarm_calls += 1
        return self.result


class CallbackRegistry:
    def __init__(self):
        self.handlers = {}

    def __call__(self, *args, **kwargs):
        def decorator(func):
            self.handlers[func.__name__] = func
            return func
        return decorator


class FakeRouter:
    def __init__(self):
        self.callback_query = CallbackRegistry()


class FakeMessage:
    def __init__(self):
        self.answers = []

    async def answer(self, text, **kwargs):
        self.answers.append((str(text), kwargs))


class FakeCall:
    def __init__(self):
        self.message = FakeMessage()
        self.answers = []

    async def answer(self, text=None, **kwargs):
        self.answers.append((text, kwargs))


class ActiveHandsOffReleaseTests(unittest.IsolatedAsyncioTestCase):
    def _manager(self, state_file, *, controller=None, manual=None, install_ui=False):
        app = types.SimpleNamespace(
            charge_controller=controller,
            manual_session_manager=manual,
        )
        if install_ui:
            app.router = FakeRouter()
            app.ParseMode = types.SimpleNamespace(HTML="HTML")

            async def _check_chat_and_respond(call):
                return True

            app._check_chat_and_respond = _check_chat_and_respond
            app._build_dashboard_keyboard = (
                lambda is_on, user_id, back_to_dashboard=False: InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text="RD hands off",
                                callback_data="rd_hands_off_enable",
                            )
                        ],
                        [InlineKeyboardButton(text="refresh", callback_data="refresh")],
                    ]
                )
            )

        manager = object.__new__(RdControlModeManager)
        manager.app = app
        manager.guard = FakeGuard()
        manager.state_file = state_file
        manager.mode = RdControlMode.PB_MANAGED
        manager.persistence_ok = True
        install_rd_hands_off_release(app, manager)
        return app, manager

    async def test_active_auto_is_released_without_managed_stop_output_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            controller = FakeController()
            _app, manager = self._manager(f"{tmp}/mode.json", controller=controller)

            self.assertTrue(await manager.enter_hands_off())

            self.assertTrue(manager.hands_off)
            self.assertEqual(controller.stop_calls, 1)
            self.assertFalse(controller.is_active)
            self.assertEqual(manager.guard._orphan_output_seen_at, None)
            with open(manager.state_file, "r", encoding="utf-8") as handle:
                self.assertEqual(json.load(handle)["mode"], "hands_off")

    async def test_active_manual_runner_is_retired_without_calling_manual_stop(self):
        with tempfile.TemporaryDirectory() as tmp:
            manual = FakeManual()
            _app, manager = self._manager(f"{tmp}/mode.json", manual=manual)

            self.assertTrue(await manager.enter_hands_off())

            self.assertTrue(manager.hands_off)
            self.assertEqual(manual.retire_calls, 1)
            self.assertEqual(manual.state, ManualSessionState.STOPPED)
            self.assertEqual(manual.stop_reason, "released_to_rd_hands_off")
            self.assertIsNone(manual.cooling_started_at)
            self.assertIsNone(manual._previous_voltage_v)
            self.assertIsNone(manual._previous_current_a)
            self.assertEqual(manual.reset_calls, 1)
            self.assertEqual(manual.persist_calls, 1)

    async def test_active_mix_clock_is_terminalized_as_release(self):
        with tempfile.TemporaryDirectory() as tmp:
            controller = FakeMixController()
            _app, manager = self._manager(f"{tmp}/mode.json", controller=controller)

            self.assertTrue(await manager.enter_hands_off())

            self.assertEqual(
                controller._mix_active_authority.calls,
                [("mix-session", "RELEASED_TO_RD_HANDS_OFF")],
            )
            self.assertFalse(controller.is_active)

    async def test_edge_disarm_failure_keeps_managed_session_and_rolls_back_durable_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            controller = FakeController()
            _app, manager = self._manager(f"{tmp}/mode.json", controller=controller)
            lease = FakeLease(False)
            manager.guard.edge_lease_enforced = True
            manager.guard.edge_safety_lease = lease

            with self.assertRaisesRegex(RuntimeSafetyError, "disarm was not confirmed"):
                await manager.enter_hands_off()

            self.assertEqual(manager.mode, RdControlMode.PB_MANAGED)
            self.assertTrue(controller.is_active)
            self.assertEqual(controller.stop_calls, 0)
            self.assertEqual(lease.disarm_calls, 1)
            with open(manager.state_file, "r", encoding="utf-8") as handle:
                self.assertEqual(json.load(handle)["mode"], "pb_managed")

    async def test_unconfirmed_off_containment_still_blocks_release(self):
        with tempfile.TemporaryDirectory() as tmp:
            controller = FakeController()
            _app, manager = self._manager(f"{tmp}/mode.json", controller=controller)
            manager.guard._off_unconfirmed = True

            with self.assertRaisesRegex(RuntimeSafetyError, "unconfirmed"):
                await manager.enter_hands_off()

            self.assertEqual(manager.mode, RdControlMode.PB_MANAGED)
            self.assertTrue(controller.is_active)
            self.assertEqual(controller.stop_calls, 0)

    async def test_active_dashboard_requires_second_confirmation_before_release(self):
        with tempfile.TemporaryDirectory() as tmp:
            controller = FakeController()
            app, manager = self._manager(
                f"{tmp}/mode.json",
                controller=controller,
                install_ui=True,
            )

            markup = app._build_dashboard_keyboard(True, 1)
            callbacks = [
                button.callback_data
                for row in markup.inline_keyboard
                for button in row
                if button.callback_data
            ]
            self.assertIn("rd_hands_off_release_confirm", callbacks)
            self.assertNotIn("rd_hands_off_enable", callbacks)

            confirm = app.router.callback_query.handlers["_confirm_active_release"]
            call = FakeCall()
            await confirm(call)

            self.assertTrue(manager.pb_managed)
            self.assertTrue(controller.is_active)
            self.assertEqual(controller.stop_calls, 0)
            self.assertEqual(len(call.message.answers), 1)
            _text, kwargs = call.message.answers[0]
            confirm_markup = kwargs["reply_markup"]
            confirm_callbacks = [
                button.callback_data
                for row in confirm_markup.inline_keyboard
                for button in row
                if button.callback_data
            ]
            self.assertEqual(
                confirm_callbacks,
                ["rd_hands_off_release_execute", "rd_hands_off_release_cancel"],
            )

            execute = app.router.callback_query.handlers["_execute_active_release"]
            await execute(call)

            self.assertTrue(manager.hands_off)
            self.assertFalse(controller.is_active)
            self.assertEqual(controller.stop_calls, 1)

    async def test_release_confirmation_cancel_is_non_actuating(self):
        with tempfile.TemporaryDirectory() as tmp:
            controller = FakeController()
            app, manager = self._manager(
                f"{tmp}/mode.json",
                controller=controller,
                install_ui=True,
            )
            cancel = app.router.callback_query.handlers["_cancel_active_release"]
            call = FakeCall()

            await cancel(call)

            self.assertTrue(manager.pb_managed)
            self.assertTrue(controller.is_active)
            self.assertEqual(controller.stop_calls, 0)


if __name__ == "__main__":
    unittest.main()
