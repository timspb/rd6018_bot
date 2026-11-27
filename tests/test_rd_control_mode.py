import tempfile
from datetime import datetime, timedelta, timezone
import types
import unittest

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from rd_control_mode import RdControlMode, install_rd_control_mode
from runtime.safety.runtime_guard import OutputOffNotConfirmed, RuntimeSafetyError
from runtime.safety.managed_guard import ManagedRuntimeSafetyGuard
from application.execution_port import get_or_create_execution_port
from application.start_transaction_service import start_profile_transactional


class DummyHass:
    def __init__(self, live):
        self.live = dict(live)
        self.base_url = ""
        self.turn_on_calls = 0
        self.turn_off_calls = 0
        self.turn_off_entities = []
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
        self.turn_off_entities.append(entity_id)
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


class FakeReturnEdgeLease:
    def __init__(
        self,
        *,
        armed=False,
        tripped=False,
        boot_quarantine=False,
        modbus_age_s=0.5,
        remaining_s=0.0,
    ):
        self.state = types.SimpleNamespace(
            armed=armed,
            tripped=tripped,
            boot_quarantine=boot_quarantine,
            generation=7,
            modbus_age_s=modbus_age_s,
            remaining_s=remaining_s,
        )
        self.config = types.SimpleNamespace(
            max_modbus_age_s=20.0,
            ack_remaining_slack_s=2.0,
        )
        self.suspended = False
        self.disarm_calls = 0

    def suspend_renewals(self):
        self.suspended = True

    def _fresh_modbus(self, state):
        return state.modbus_age_s <= self.config.max_modbus_age_s

    async def read_state(self):
        return types.SimpleNamespace(**vars(self.state))

    async def disarm(self):
        self.disarm_calls += 1
        self.state.armed = False
        self.state.remaining_s = 0.0
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

    def _app(self, state_file, *, install_ui=False, include_ovp_ocp_setters=True):
        hass = DummyHass(self._generic_psu_live())
        if not include_ovp_ocp_setters:
            hass.set_ovp = None
            hass.set_ocp = None
        app = types.SimpleNamespace(
            hass=hass,
            charge_controller=DummyController(),
            manual_session_manager=None,
            _charge_notify=lambda *args, **kwargs: None,
            rd_control_mode_file=state_file,
        )
        guard = ManagedRuntimeSafetyGuard(app)
        guard.edge_lease_enforced = False
        guard.OFF_CONFIRMATION_WINDOW_S = 0.0
        guard.OFF_CONFIRMATION_POLL_S = 0.0
        guard.install(patch_adapter=False)
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
        get_or_create_execution_port(app)
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

    async def test_edge_autonomous_observation_blocks_pb_paths_without_actuation(self):
        with tempfile.TemporaryDirectory() as tmp:
            app, manager, _guard = self._app(f"{tmp}/mode.json")
            app.hass.live["autonomous_mode"] = "on"

            live = await app.hass.get_all_live()
            manager._observe_edge_mode(live)

            self.assertTrue(manager.edge_autonomous)
            self.assertEqual(live["autonomous_mode"], "on")
            with self.assertRaisesRegex(RuntimeSafetyError, "AUTONOMOUS"):
                await app.execution_port.request_verified_on()
            with self.assertRaisesRegex(RuntimeSafetyError, "AUTONOMOUS"):
                app.execution_port.authorize_managed_start()
            self.assertEqual(app.hass.turn_on_calls, 0)
            self.assertEqual(app.charge_controller.start_calls, 0)

    async def test_optional_ovp_ocp_setters_do_not_break_hass_client_composition(self):
        with tempfile.TemporaryDirectory() as tmp:
            app, manager, _guard = self._app(
                f"{tmp}/mode.json", include_ovp_ocp_setters=False
            )
            self.assertIsNone(app.hass.set_ovp)
            self.assertIsNone(app.hass.set_ocp)
            await manager.enter_hands_off()
            live = await app.hass.get_all_live()
            self.assertEqual(live["switch"], "on")
            self.assertEqual(app.hass.turn_off_calls, 0)

    async def test_hands_off_and_autonomous_block_all_setpoint_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            app, manager, _guard = self._app(f"{tmp}/mode.json")
            await manager.enter_hands_off()
            for write in (
                app.execution_port.program_voltage,
                app.execution_port.program_current,
            ):
                with self.assertRaises(RuntimeSafetyError):
                    await write(1.0)

            app.hass.live["autonomous_mode"] = "on"
            manager._observe_edge_mode(await app.hass.get_all_live())
            for write in (
                app.execution_port.program_voltage,
                app.execution_port.program_current,
            ):
                with self.assertRaises(RuntimeSafetyError):
                    await write(1.0)
            with self.assertRaises(RuntimeSafetyError):
                await app.execution_port.request_verified_off()
            self.assertEqual(app.hass.turn_off_calls, 0)

    async def test_edge_autonomous_blocks_restore_without_invoking_controller(self):
        with tempfile.TemporaryDirectory() as tmp:
            app, manager, _guard = self._app(f"{tmp}/mode.json")
            app.hass.live["autonomous_mode"] = "on"
            received = []

            def restore(*args, **kwargs):
                received.append((args, kwargs))
                return True, "Mix Mode"

            app.charge_controller.try_restore_session = restore
            app.rd_control_mode_manager = None
            app.hass._rd_control_mode_wrapped = False
            manager = install_rd_control_mode(app, install_ui=False)
            manager._observe_edge_mode(await app.hass.get_all_live())
            app.charge_controller.try_restore_session(
                14.2, 0.3, 70.0, output_is_on=True, is_cv=True, is_cc=False
            )

            self.assertTrue(manager.edge_autonomous)
            self.assertEqual(received, [])

    def test_restore_wrapper_forwards_extended_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            app, _manager, _guard = self._app(f"{tmp}/mode.json")
            received = []

            def restore(*args, **kwargs):
                received.append((args, kwargs))
                return False, None

            app.charge_controller.try_restore_session = restore
            install_rd_control_mode(app, install_ui=False)

            app.charge_controller.try_restore_session(
                14.2,
                0.3,
                70.0,
                output_is_on=True,
                is_cv=True,
                is_cc=False,
            )

            self.assertEqual(
                received,
                [
                    (
                        (14.2, 0.3, 70.0),
                        {"output_is_on": True, "is_cv": True, "is_cc": False},
                    )
                ],
            )

    async def test_hands_off_blocks_bot_actuators_without_actuating(self):
        with tempfile.TemporaryDirectory() as tmp:
            app, manager, _guard = self._app(f"{tmp}/mode.json")
            await manager.enter_hands_off()

            with self.assertRaisesRegex(RuntimeSafetyError, "HANDS_OFF"):
                await app.execution_port.program_voltage(12.0)
            with self.assertRaisesRegex(RuntimeSafetyError, "HANDS_OFF"):
                await app.execution_port.request_verified_on()
            with self.assertRaisesRegex(RuntimeSafetyError, "HANDS_OFF"):
                await app.execution_port.request_verified_off()
            with self.assertRaisesRegex(RuntimeSafetyError, "HANDS_OFF"):
                app.execution_port.authorize_managed_start()

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

            port = app.execution_port
            self.assertIs(port._execution_owner, _guard)
            self.assertTrue(await manager.operator_output_off("switch.test"))
            self.assertEqual(app.hass.turn_off_calls, 1)
            self.assertEqual(app.hass.turn_off_entities, ["switch.test"])
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

    async def test_false_explicit_off_returns_without_residual_lease_disarm(self):
        with tempfile.TemporaryDirectory() as tmp:
            app, manager, guard = self._app(f"{tmp}/mode.json")
            await manager.enter_hands_off()
            calls = []
            disarm_calls = []

            async def request_off(entity_id=None, *, allow_hands_off_operator_off=False):
                calls.append((entity_id, allow_hands_off_operator_off))
                return False

            async def disarm():
                disarm_calls.append(True)

            app.execution_port.request_emergency_off = request_off
            guard._disarm_edge_lease_best_effort = disarm
            self.assertFalse(await manager.operator_output_off("switch.test"))
            self.assertEqual(calls, [("switch.test", True)])
            self.assertEqual(disarm_calls, [])
            self.assertTrue(manager.hands_off)

    async def test_return_to_pb_requires_confirmed_off(self):
        with tempfile.TemporaryDirectory() as tmp:
            app, manager, _guard = self._app(f"{tmp}/mode.json")
            await manager.enter_hands_off()

            with self.assertRaisesRegex(
                RuntimeSafetyError,
                "Output OFF|freshness metadata",
            ):
                await manager.return_pb_control()
            self.assertTrue(manager.hands_off)
            # The composed Safety owner may fail closed on unmanaged Output ON
            # when the fake transport supplies no freshness metadata.
            self.assertGreaterEqual(app.hass.turn_off_calls, 1)

            await manager.operator_output_off()
            self.assertTrue(await manager.return_pb_control())
            self.assertEqual(manager.mode, RdControlMode.PB_MANAGED)

    @staticmethod
    def _fresh_output_metadata(source_key="switch", *, age_s=0.0):
        reported = (datetime.now(timezone.utc) - timedelta(seconds=age_s)).isoformat()
        return {
            "status": "ok",
            "source_key": source_key,
            "last_reported": reported,
            "last_updated": reported,
        }

    async def test_return_pb_rejects_stale_off_heartbeat(self):
        with tempfile.TemporaryDirectory() as tmp:
            app, manager, _guard = self._app(f"{tmp}/mode.json")
            await manager.enter_hands_off()
            app.hass.live["switch"] = "off"
            app.hass.live["_meta"] = {
                "switch": self._fresh_output_metadata(age_s=60.0)
            }

            with self.assertRaisesRegex(RuntimeSafetyError, "fresh confirmed Output OFF"):
                await manager.return_pb_control()

            self.assertTrue(manager.hands_off)

    async def test_return_pb_uses_canonical_v2_output_over_legacy_switch(self):
        with tempfile.TemporaryDirectory() as tmp:
            app, manager, _guard = self._app(f"{tmp}/mode.json")
            await manager.enter_hands_off()
            app.hass.live["switch"] = "off"
            app.hass.live["output_state_code_v2"] = 1
            app.hass.live["_meta"] = {
                "switch": self._fresh_output_metadata(
                    "output_state_code_v2"
                ),
                "output_state_code_v2": self._fresh_output_metadata(
                    "output_state_code_v2"
                ),
            }

            with self.assertRaisesRegex(RuntimeSafetyError, "fresh confirmed Output OFF"):
                await manager.return_pb_control()

            self.assertTrue(manager.hands_off)

    async def test_return_pb_rejects_stale_v2_heartbeat_even_if_switch_alias_is_fresh(self):
        with tempfile.TemporaryDirectory() as tmp:
            app, manager, _guard = self._app(f"{tmp}/mode.json")
            await manager.enter_hands_off()
            app.hass.live["switch"] = "off"
            app.hass.live["output_state_code_v2"] = 0
            app.hass.live["_meta"] = {
                "switch": self._fresh_output_metadata(
                    "output_state_code_v2"
                ),
                "output_state_code_v2": self._fresh_output_metadata(
                    "output_state_code_v2",
                    age_s=60.0,
                ),
            }

            with self.assertRaisesRegex(RuntimeSafetyError, "fresh confirmed Output OFF"):
                await manager.return_pb_control()

            self.assertTrue(manager.hands_off)

    async def test_return_pb_accepts_fresh_v2_off_when_legacy_alias_is_stale(self):
        with tempfile.TemporaryDirectory() as tmp:
            app, manager, _guard = self._app(f"{tmp}/mode.json")
            await manager.enter_hands_off()
            app.hass.live["switch"] = "off"
            app.hass.live["output_state_code_v2"] = 0
            app.hass.live["_meta"] = {
                "switch": self._fresh_output_metadata(
                    "output_state_code_v2",
                    age_s=60.0,
                ),
                "output_state_code_v2": self._fresh_output_metadata(
                    "output_state_code_v2"
                ),
            }

            self.assertTrue(await manager.return_pb_control())
            self.assertTrue(manager.pb_managed)

    async def test_return_pb_rejects_v2_off_without_source_heartbeat(self):
        with tempfile.TemporaryDirectory() as tmp:
            app, manager, _guard = self._app(f"{tmp}/mode.json")
            await manager.enter_hands_off()
            app.hass.live["switch"] = "off"
            app.hass.live["output_state_code_v2"] = 0
            app.hass.live.pop("_meta", None)

            with self.assertRaisesRegex(RuntimeSafetyError, "fresh confirmed Output OFF"):
                await manager.return_pb_control()

            self.assertTrue(manager.hands_off)

    async def test_return_pb_uses_fresh_canonical_v2_off_and_retires_armed_lease(self):
        with tempfile.TemporaryDirectory() as tmp:
            app, manager, guard = self._app(f"{tmp}/mode.json")
            await manager.enter_hands_off()
            app.hass.live["switch"] = "on"
            app.hass.live["output_state_code_v2"] = 0
            app.hass.live["_meta"] = {
                "switch": self._fresh_output_metadata(
                    "output_state_code_v2"
                ),
                "output_state_code_v2": self._fresh_output_metadata(
                    "output_state_code_v2"
                ),
            }
            lease = FakeReturnEdgeLease(armed=True, remaining_s=300.0)
            guard.edge_lease_enforced = True
            guard.edge_safety_lease = lease

            self.assertTrue(await manager.return_pb_control())

            self.assertTrue(manager.pb_managed)
            self.assertEqual(lease.disarm_calls, 1)
            self.assertTrue(lease.suspended)

    async def test_return_pb_does_not_repeat_an_already_confirmed_lease_disarm(self):
        with tempfile.TemporaryDirectory() as tmp:
            app, manager, guard = self._app(f"{tmp}/mode.json")
            await manager.enter_hands_off()
            app.hass.live["switch"] = "off"
            lease = FakeReturnEdgeLease(armed=False, remaining_s=0.0)
            guard.edge_lease_enforced = True
            guard.edge_safety_lease = lease

            self.assertTrue(await manager.return_pb_control())

            self.assertTrue(manager.pb_managed)
            self.assertEqual(lease.disarm_calls, 0)
            self.assertTrue(lease.suspended)

    async def test_return_pb_fails_closed_when_required_edge_lease_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            app, manager, guard = self._app(f"{tmp}/mode.json")
            await manager.enter_hands_off()
            app.hass.live["switch"] = "off"
            guard.edge_lease_enforced = True
            guard.edge_safety_lease = None

            with self.assertRaisesRegex(RuntimeSafetyError, "required edge safety lease is unavailable"):
                await manager.return_pb_control()

            self.assertTrue(manager.hands_off)

    async def test_return_pb_refuses_unhealthy_edge_lease(self):
        with tempfile.TemporaryDirectory() as tmp:
            app, manager, guard = self._app(f"{tmp}/mode.json")
            await manager.enter_hands_off()
            app.hass.live["switch"] = "off"
            lease = FakeReturnEdgeLease(tripped=True)
            guard.edge_lease_enforced = True
            guard.edge_safety_lease = lease

            with self.assertRaisesRegex(RuntimeSafetyError, "tripped, quarantined or stale"):
                await manager.return_pb_control()

            self.assertTrue(manager.hands_off)
            self.assertEqual(lease.disarm_calls, 0)

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
            import mix_mode

            message = DummyMessage()
            pending = types.SimpleNamespace(profile="Ca/Ca", capacity_ah=60.0)
            started = await mix_mode.start_mix_transactional(app, message, pending)

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
