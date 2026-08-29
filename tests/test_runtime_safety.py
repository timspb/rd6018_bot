import types
import unittest

from runtime_safety import OutputOffNotConfirmed, RuntimeSafetyError
from runtime_safety_strict import install_strict_runtime_safety


def live_state(**overrides):
    base = {
        "battery_voltage": 14.6,
        "current": 1.0,
        "temp_ext": 25.0,
        "temp_int": 32.0,
        "input_voltage": 64.0,
        "switch": "on",
        "ovp_triggered": "off",
        "ocp_triggered": "off",
        "set_voltage": 14.8,
        "set_current": 2.0,
        "ovp": 14.9,
        "ocp": 2.1,
    }
    base.update(overrides)
    return base


class FakeController:
    def __init__(self, *, active=True, ceiling=16.5):
        self.is_active = active
        self.ceiling = ceiling

    def _recipe_envelope(self):
        return types.SimpleNamespace(voltage_ceiling_v=self.ceiling)


class FakeHass:
    def __init__(self, live=None):
        self.live = live_state() if live is None else dict(live)
        self.turn_off_calls = 0
        self.turn_on_calls = 0
        self.setter_calls = []
        self.stuck_on = False
        self.fail_setter = None

    async def get_all_live(self):
        return dict(self.live)

    async def turn_off(self, entity_id=None):
        self.turn_off_calls += 1
        if not self.stuck_on:
            self.live["switch"] = "off"
        return not self.stuck_on

    async def turn_on(self, entity_id=None):
        self.turn_on_calls += 1
        self.live["switch"] = "on"
        return True

    async def _set(self, name, key, value):
        self.setter_calls.append((name, float(value)))
        if self.fail_setter == name:
            return False
        self.live[key] = float(value)
        return True

    async def set_voltage(self, value):
        return await self._set("set_voltage", "set_voltage", value)

    async def set_current(self, value):
        return await self._set("set_current", "set_current", value)

    async def set_ovp(self, value):
        return await self._set("set_ovp", "ovp", value)

    async def set_ocp(self, value):
        return await self._set("set_ocp", "ocp", value)


class FakeApp:
    def __init__(self, *, live=None, active=True, ceiling=16.5):
        self.hass = FakeHass(live)
        self.charge_controller = FakeController(active=active, ceiling=ceiling)
        self.notices = []

    def _charge_notify(self, message):
        self.notices.append(message)


class RuntimeSafetyTests(unittest.IsolatedAsyncioTestCase):
    def _install(self, app):
        guard = install_strict_runtime_safety(app)
        guard.VERIFY_ATTEMPTS = 2
        guard.VERIFY_DELAY_S = 0.0
        return guard

    async def test_valid_active_snapshot_passes_unchanged(self):
        app = FakeApp()
        self._install(app)

        live = await app.hass.get_all_live()

        self.assertEqual(live["switch"], "on")
        self.assertEqual(app.hass.turn_off_calls, 0)

    async def test_missing_external_temperature_forces_verified_off(self):
        app = FakeApp(live=live_state(temp_ext=None))
        self._install(app)

        with self.assertRaises(RuntimeSafetyError):
            await app.hass.get_all_live()

        self.assertEqual(app.hass.turn_off_calls, 1)
        self.assertEqual(app.hass.live["switch"], "off")
        self.assertTrue(app.notices)

    async def test_psu_overtemperature_forces_verified_off_at_shared_boundary(self):
        app = FakeApp(live=live_state(temp_int=55.0))
        self._install(app)

        with self.assertRaises(RuntimeSafetyError):
            await app.hass.get_all_live()

        self.assertEqual(app.hass.turn_off_calls, 1)
        self.assertEqual(app.hass.live["switch"], "off")

    async def test_missing_telemetry_while_already_off_freezes_session_without_reenable(self):
        app = FakeApp(live=live_state(switch="off", temp_ext=None))
        self._install(app)

        with self.assertRaises(RuntimeSafetyError):
            await app.hass.get_all_live()

        self.assertEqual(app.hass.turn_off_calls, 0)
        self.assertEqual(app.hass.live["switch"], "off")

    async def test_runtime_input_undervoltage_forces_output_off(self):
        app = FakeApp(live=live_state(input_voltage=55.0))
        self._install(app)

        with self.assertRaises(RuntimeSafetyError):
            await app.hass.get_all_live()

        self.assertEqual(app.hass.live["switch"], "off")
        self.assertEqual(app.hass.turn_off_calls, 1)

    async def test_live_recipe_ceiling_drift_forces_output_off(self):
        app = FakeApp(live=live_state(set_voltage=16.7, ovp=16.8), ceiling=16.5)
        self._install(app)

        with self.assertRaises(RuntimeSafetyError):
            await app.hass.get_all_live()

        self.assertEqual(app.hass.live["switch"], "off")

    async def test_live_voltage_change_requires_confirmed_ovp_margin(self):
        app = FakeApp(live=live_state(ovp=14.9, set_voltage=14.8))
        self._install(app)

        with self.assertRaises(RuntimeSafetyError):
            await app.hass.set_voltage(16.0)

        self.assertEqual(app.hass.live["switch"], "off")
        self.assertFalse(any(name == "set_voltage" for name, _ in app.hass.setter_calls))

    async def test_live_current_change_requires_confirmed_ocp_margin(self):
        app = FakeApp(live=live_state(ocp=2.1, set_current=2.0))
        self._install(app)

        with self.assertRaises(RuntimeSafetyError):
            await app.hass.set_current(4.0)

        self.assertEqual(app.hass.live["switch"], "off")
        self.assertFalse(any(name == "set_current" for name, _ in app.hass.setter_calls))

    async def test_ovp_cannot_be_lowered_below_active_voltage_envelope(self):
        app = FakeApp(live=live_state(set_voltage=14.8, ovp=14.9))
        self._install(app)

        with self.assertRaises(RuntimeSafetyError):
            await app.hass.set_ovp(14.0)

        self.assertEqual(app.hass.live["switch"], "off")
        self.assertFalse(any(name == "set_ovp" for name, _ in app.hass.setter_calls))

    async def test_ocp_cannot_be_lowered_below_active_current_envelope(self):
        app = FakeApp(live=live_state(set_current=2.0, ocp=2.1))
        self._install(app)

        with self.assertRaises(RuntimeSafetyError):
            await app.hass.set_ocp(1.0)

        self.assertEqual(app.hass.live["switch"], "off")
        self.assertFalse(any(name == "set_ocp" for name, _ in app.hass.setter_calls))

    async def test_failed_live_ovp_programming_aborts_sequence_and_forces_off(self):
        app = FakeApp()
        app.hass.fail_setter = "set_ovp"
        self._install(app)

        with self.assertRaises(RuntimeSafetyError):
            await app.hass.set_ovp(15.0)

        self.assertEqual(app.hass.live["switch"], "off")
        self.assertEqual(app.hass.turn_off_calls, 1)

    async def test_idle_controller_cannot_energize_output(self):
        app = FakeApp(
            active=False,
            live=live_state(switch="off", current=0.0),
        )
        self._install(app)

        with self.assertRaises(RuntimeSafetyError):
            await app.hass.turn_on()

        self.assertEqual(app.hass.turn_on_calls, 0)
        self.assertEqual(app.hass.live["switch"], "off")

    async def test_unconfirmed_off_blocks_future_enable(self):
        app = FakeApp()
        app.hass.stuck_on = True
        self._install(app)

        with self.assertRaises(OutputOffNotConfirmed):
            await app.hass.turn_off()
        with self.assertRaises(OutputOffNotConfirmed):
            await app.hass.turn_on()

        self.assertEqual(app.hass.turn_on_calls, 0)

    async def test_unmanaged_output_gets_one_restore_grace_then_is_forced_off(self):
        app = FakeApp(active=False)
        guard = self._install(app)
        guard.ORPHAN_OUTPUT_GRACE_S = 0.0

        first = await app.hass.get_all_live()
        self.assertEqual(first["switch"], "on")

        with self.assertRaises(RuntimeSafetyError):
            await app.hass.get_all_live()

        self.assertEqual(app.hass.live["switch"], "off")

    async def test_hardware_trip_is_left_for_existing_trip_handler(self):
        app = FakeApp(live=live_state(ovp_triggered="on", switch="off"))
        self._install(app)

        live = await app.hass.get_all_live()

        self.assertEqual(live["ovp_triggered"], "on")
        self.assertEqual(app.hass.turn_off_calls, 0)


if __name__ == "__main__":
    unittest.main()
