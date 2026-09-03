import tempfile
import types
import unittest

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from rd_control_mode import RdControlMode, install_rd_control_mode
from runtime_safety import OutputOffNotConfirmed, RuntimeSafetyError
from runtime_safety_v2 import V2RuntimeSafetyGuard
from v2_startup import start_profile_transactional


class DummyHass:
    def __init__(self, live):
        self.live = dict(live)
        self.base_url = ""
        self.turn_on_calls = 0
        self.turn_off_calls = 0
        self.set_voltage_calls = 0
        self.off_confirms = True

    @staticmethod
    def _entity_metadata(entity_id, data, status):
        return {
            "entity_id": entity_id,
            "status": status,
            "last_updated": data.get("last_updated"),
        }

    async def get_all_live(self):
        return dict(self.live)

    async def turn_on(self, entity_id=None):
        self.turn_on_calls += 1
        self.live["switch"] = "on"
        return True

    async def turn_off(self, entity_id=None):
        self.turn_off_calls += 1
        if not self.off_confirms:
            return False
        self.live["switch"] = "off"
        return True

    async def set_voltage(self, value):
        self.set_voltage_calls += 1
        self.live["set_voltage"] = value
        return True

    async def set_current(self, value):
        self.live["set_current"] = value
        return True

    async def set_ovp(self, value):
        self.live["ovp"] = value
        return True

    async def set_ocp(self, value):
        self.live["ocp"] = value
        return True


class DummyController:
    def __init__(self):
        self.is_active = False
        self.start_calls = 0

    def _recipe_envelope(self):
        return None

    def _get_target_v_i(self, temp_ext=None):
        return 14.8, 5.0

    def start(self, *args, **kwargs):
        self.start_calls += 1
        self.is_active = True


class DummyCallbackRegistry:
    def __call__(self, *args, **kwargs):
        def decorator(func):
            return func
        return decorator


class DummyRouter:
    def __init__(self):
        self.callback_query = DummyCallbackRegistry()


class DummyMessage:
    def __init__(self):
        self.answers = []
        self.from_user = types.SimpleNamespace(id=1)
        self.chat = types.SimpleNamespace(id=1)

    async def answer(self, text, **kwargs):
        self.answers.append(str(text))


class RdControlModeTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _generic_psu_live():
        return {
            "battery_voltage": 18.0,
            "voltage": 18.15,
            "current": 1.2,
            "temp_ext": "unavailable",
            "temp_int": 35.0,
            "input_voltage": 40.0,
            "switch": "on",
            "ovp_triggered": "off",
            "ocp_triggered": "off",
            "set_voltage": 18.2,
            "set_current": 2.0,
            "ovp": 18.0,
            "ocp": 2.1,
        }

    def _app(self, state_file, *, install_ui=False):
        app = types.SimpleNamespace(
            hass=DummyHass(self._generic_psu_live()),
            charge_controller=DummyController(),
            manual_session_manager=None,
            _charge_notify=lambda *args, **kwargs: None,
            rd_control_mode_file=state_file,
        )
        guard = V2RuntimeSafetyGuard(app)
        guard.edge_lease_enforced = False
        guard.OFF_CONFIRMATION_WINDOW_S = 0.0
        guard.OFF_CONFIRMATION_POLL_S = 0.0
        guard.install()
        app.runtime_safety_guard = guard

        if install_ui:
            app.router = DummyRouter()
            app.ParseMode = types.SimpleNamespace(HTML="HTML")
            app._check_chat_and_respond = lambda call: True
            app.ENTITY_MAP = {"switch": "switch.rd6018"}
            app._build_dashboard_keyboard = (
                lambda is_on, user_id, back_to_dashboard=False: InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text="stop" if is_on else "start",
                                callback_data=(
                                    "power_toggle" if is_on else "charge_modes"
                                ),
                            )
                        ],
                        [InlineKeyboardButton(text="refresh", callback_data="refresh")],
                        [InlineKeyboardButton(text="timer", callback_data="menu_off")],
                    ]
                )
            )
            app._compact_dashboard_caption = (
                lambda live, chart_mode, mode, idle_warning: f"body:{idle_warning}"
            )

        manager = install_rd_control_mode(app, install_ui=install_ui)
        return app, manager, guard

    async def test_hands_off_observes_non_pb_state_without_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            app, manager, _guard = self._app(f"{tmp}/mode.json")
            await manager.enter_hands_off()

            live = await app.hass.get_all_live()

            self.assertEqual(live["set_voltage"], 18.2)
            self.assertEqual(live["temp_ext"], "unavailable")
            self.assertLess(live["ovp"], live["set_voltage"])
            self.assertEqual(app.hass.turn_off_calls, 0)
            self.assertTrue(manager.hands_off)

    async def test_hands_off_blocks_bot_actuators_without_actuating(self):
        with tempfile.TemporaryDirectory() as tmp:
            app, manager, _guard = self._app(f"{tmp}/mode.json")
            await manager.enter_hands_off()

            with self.assertRaisesRegex(RuntimeSafetyError, "HANDS_OFF"):
                await app.hass.set_voltage(12.0)
            with self.assertRaisesRegex(RuntimeSafetyError, "HANDS_OFF"):
                await app.hass.turn_on()
            with self.assertRaisesRegex(RuntimeSafetyError, "HANDS_OFF"):
                await app.hass.turn_off()
            with self.assertRaisesRegex(RuntimeSafetyError, "HANDS_OFF"):
                app.charge_controller.start("Ca/Ca", 60)

            self.assertEqual(app.hass.set_voltage_calls, 0)
            self.assertEqual(app.hass.turn_on_calls, 0)
            self.assertEqual(app.hass.turn_off_calls, 0)
            self.assertEqual(app.charge_controller.start_calls, 0)
            self.assertEqual(app.hass.live["set_voltage"], 18.2)
            self.assertEqual(app.hass.live["switch"], "on")

    async def test_explicit_hands_off_output_off_is_raw_and_verified(self):
        with tempfile.TemporaryDirectory() as tmp:
            app, manager, _guard = self._app(f"{tmp}/mode.json")
            await manager.enter_hands_off()

            self.assertTrue(await manager.operator_output_off())
            self.assertEqual(app.hass.turn_off_calls, 1)
            self.assertEqual(app.hass.live["switch"], "off")
            self.assertTrue(manager.hands_off)

    async def test_failed_explicit_off_does_not_restore_pb_authority(self):
        with tempfile.TemporaryDirectory() as tmp:
            app, manager, guard = self._app(f"{tmp}/mode.json")
            await manager.enter_hands_off()
            app.hass.off_confirms = False

            with self.assertRaises(OutputOffNotConfirmed):
                await manager.operator_output_off()

            self.assertTrue(manager.hands_off)
            self.assertTrue(guard._off_unconfirmed)
            self.assertEqual(app.hass.live["switch"], "on")

    async def test_return_to_pb_requires_confirmed_off(self):
        with tempfile.TemporaryDirectory() as tmp:
            app, manager, _guard = self._app(f"{tmp}/mode.json")
            await manager.enter_hands_off()

            with self.assertRaisesRegex(RuntimeSafetyError, "requires confirmed Output OFF"):
                await manager.return_pb_control()
            self.assertTrue(manager.hands_off)
            self.assertEqual(app.hass.turn_off_calls, 0)

            await manager.operator_output_off()
            self.assertTrue(await manager.return_pb_control())
            self.assertEqual(manager.mode, RdControlMode.PB_MANAGED)

    async def test_hands_off_persists_across_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_file = f"{tmp}/mode.json"
            _app1, manager1, _guard1 = self._app(state_file)
            await manager1.enter_hands_off()

            app2, manager2, _guard2 = self._app(state_file)
            self.assertTrue(manager2.hands_off)
            live = await app2.hass.get_all_live()
            self.assertEqual(live["set_voltage"], 18.2)
            self.assertEqual(app2.hass.turn_off_calls, 0)

    async def test_corrupt_state_never_infers_hands_off(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_file = f"{tmp}/mode.json"
            with open(state_file, "w", encoding="utf-8") as handle:
                handle.write("{broken")
            _app, manager, _guard = self._app(state_file)
            self.assertEqual(manager.mode, RdControlMode.PB_MANAGED)
            self.assertFalse(manager.persistence_ok)

    async def test_active_managed_session_cannot_drop_safety_boundary(self):
        with tempfile.TemporaryDirectory() as tmp:
            app, manager, _guard = self._app(f"{tmp}/mode.json")
            app.charge_controller.is_active = True

            with self.assertRaisesRegex(RuntimeSafetyError, "active managed charge"):
                await manager.enter_hands_off()

            self.assertTrue(manager.pb_managed)

    async def test_off_unconfirmed_containment_cannot_be_bypassed(self):
        with tempfile.TemporaryDirectory() as tmp:
            _app, manager, guard = self._app(f"{tmp}/mode.json")
            guard._off_unconfirmed = True

            with self.assertRaisesRegex(RuntimeSafetyError, "unconfirmed"):
                await manager.enter_hands_off()

            self.assertTrue(manager.pb_managed)

    async def test_normal_profile_start_rejected_before_session_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            app, manager, _guard = self._app(f"{tmp}/mode.json")
            await manager.enter_hands_off()
            message = DummyMessage()
            pending = types.SimpleNamespace(
                battery_id="bat",
                intent=types.SimpleNamespace(value="normal"),
                condition=object(),
                profile="Ca/Ca",
                capacity_ah=60.0,
            )

            started = await start_profile_transactional(app, message, pending)

            self.assertFalse(started)
            self.assertEqual(app.charge_controller.start_calls, 0)
            self.assertTrue(any("не лезь" in text for text in message.answers))
            self.assertEqual(app.hass.turn_off_calls, 0)

    async def test_auto_mix_entrypoint_rejected_before_session_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            app, manager, _guard = self._app(f"{tmp}/mode.json", install_ui=True)
            await manager.enter_hands_off()
            import v2_mix_mode

            message = DummyMessage()
            pending = types.SimpleNamespace(profile="Ca/Ca", capacity_ah=60.0)
            started = await v2_mix_mode.start_mix_transactional(app, message, pending)

            self.assertFalse(started)
            self.assertTrue(any("не лезь" in text for text in message.answers))
            self.assertEqual(app.charge_controller.start_calls, 0)
            self.assertEqual(app.hass.turn_off_calls, 0)

    async def test_dashboard_exposes_hands_off_and_removes_charge_actions(self):
        with tempfile.TemporaryDirectory() as tmp:
            app, manager, _guard = self._app(f"{tmp}/mode.json", install_ui=True)

            managed = app._build_dashboard_keyboard(True, 1)
            managed_callbacks = [
                button.callback_data
                for row in managed.inline_keyboard
                for button in row
                if button.callback_data
            ]
            self.assertIn("rd_hands_off_enable", managed_callbacks)

            await manager.enter_hands_off()
            hands_off = app._build_dashboard_keyboard(True, 1)
            callbacks = [
                button.callback_data
                for row in hands_off.inline_keyboard
                for button in row
                if button.callback_data
            ]
            self.assertIn("rd_hands_off_output_off", callbacks)
            self.assertIn("rd_hands_off_disable", callbacks)
            self.assertNotIn("power_toggle", callbacks)
            self.assertNotIn("charge_modes", callbacks)
            self.assertNotIn("menu_off", callbacks)

            caption = app._compact_dashboard_caption({}, "30m", "CV", "orphan warning")
            self.assertIn("РЕЖИМ РД — НЕ ЛЕЗЬ", caption)
            self.assertNotIn("orphan warning", caption)


if __name__ == "__main__":
    unittest.main()
