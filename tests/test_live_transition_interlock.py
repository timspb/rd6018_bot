import types
import unittest

from runtime_safety import RuntimeSafetyError
from runtime_safety_strict import StrictRuntimeSafetyGuard


def live_state(**overrides):
    base = {
        "battery_voltage": 14.72,
        "voltage": 14.72,
        "current": 0.09,
        "temp_ext": 23.0,
        "temp_int": 32.0,
        "input_voltage": 64.0,
        "switch": "on",
        "ovp_triggered": "off",
        "ocp_triggered": "off",
        "set_voltage": 14.72,
        "set_current": 7.20,
        "ovp": 14.82,
        "ocp": 7.30,
    }
    base.update(overrides)
    return base


class FakeController:
    def __init__(self, *, target_v=16.50, target_i=2.16, active=True):
        self.target_v = target_v
        self.target_i = target_i
        self.is_active = active

    def _recipe_envelope(self):
        return types.SimpleNamespace(voltage_ceiling_v=16.50)

    def _get_target_v_i(self, temp_ext=None):
        return self.target_v, self.target_i


class FakeHass:
    def __init__(self, live=None, *, follow_voltage_setpoint=False):
        self.live = live_state() if live is None else dict(live)
        self.setter_calls = []
        self.turn_off_calls = 0
        self.follow_voltage_setpoint = follow_voltage_setpoint

    async def get_all_live(self):
        return dict(self.live)

    async def turn_off(self, entity_id=None):
        self.turn_off_calls += 1
        self.live["switch"] = "off"
        return True

    async def turn_on(self, entity_id=None):
        self.live["switch"] = "on"
        return True

    async def _set(self, name, key, value):
        self.setter_calls.append((name, float(value)))
        self.live[key] = float(value)
        return True

    async def set_voltage(self, value):
        ok = await self._set("set_voltage", "set_voltage", value)
        if ok and self.follow_voltage_setpoint:
            self.live["voltage"] = float(value)
        return ok

    async def set_current(self, value):
        return await self._set("set_current", "set_current", value)

    async def set_ovp(self, value):
        return await self._set("set_ovp", "ovp", value)

    async def set_ocp(self, value):
        return await self._set("set_ocp", "ocp", value)


class FakeApp:
    def __init__(
        self,
        *,
        live=None,
        target_v=16.50,
        target_i=2.16,
        follow_voltage_setpoint=False,
    ):
        self.hass = FakeHass(
            live,
            follow_voltage_setpoint=follow_voltage_setpoint,
        )
        self.charge_controller = FakeController(target_v=target_v, target_i=target_i)
        self.notices = []

    def _charge_notify(self, message):
        self.notices.append(message)


class LiveTransitionInterlockTests(unittest.IsolatedAsyncioTestCase):
    def _guard(self, app):
        guard = StrictRuntimeSafetyGuard(app)
        guard.OFF_CONFIRMATION_WINDOW_S = 0.0
        guard.OFF_CONFIRMATION_POLL_S = 0.0
        guard.TRANSITION_SETTLE_POLL_S = 0.0
        return guard

    async def test_main_to_mix_voltage_raise_preconditions_lower_current_first(self):
        app = FakeApp(
            live=live_state(
                set_voltage=14.72,
                set_current=7.20,
                current=0.09,
                ovp=16.60,
                ocp=7.30,
            ),
            target_v=16.50,
            target_i=2.16,
        )
        guard = self._guard(app)

        ok = await guard.set_voltage(16.50)

        self.assertTrue(ok)
        self.assertEqual(
            app.hass.setter_calls[:2],
            [("set_current", 2.16), ("set_voltage", 16.50)],
        )
        self.assertEqual(app.hass.live["switch"], "on")

    async def test_voltage_raise_does_not_precondition_when_stage_current_is_not_lower(self):
        app = FakeApp(
            live=live_state(
                set_voltage=14.20,
                set_current=2.00,
                current=1.50,
                ovp=16.60,
                ocp=2.20,
            ),
            target_v=16.00,
            target_i=2.00,
        )
        guard = self._guard(app)

        ok = await guard.set_voltage(16.00)

        self.assertTrue(ok)
        self.assertEqual(app.hass.setter_calls, [("set_voltage", 16.00)])

    async def test_temperature_compensation_drop_lowers_voltage_before_ovp(self):
        app = FakeApp(
            live=live_state(
                set_voltage=14.82,
                voltage=14.82,
                set_current=7.20,
                current=0.40,
                ovp=14.92,
                ocp=7.30,
            ),
            target_v=14.72,
            target_i=7.20,
            follow_voltage_setpoint=True,
        )
        guard = self._guard(app)

        ok = await guard.set_ovp(14.82)

        self.assertTrue(ok)
        self.assertEqual(
            app.hass.setter_calls[:2],
            [("set_voltage", 14.72), ("set_ovp", 14.82)],
        )
        self.assertEqual(app.hass.live["switch"], "on")

    async def test_ocp_tightening_refuses_to_cut_through_unsettled_measured_current(self):
        app = FakeApp(
            live=live_state(
                set_current=2.16,
                current=3.00,
                ocp=7.30,
            )
        )
        guard = self._guard(app)
        guard.TRANSITION_SETTLE_TIMEOUT_S = 0.0

        with self.assertRaises(RuntimeSafetyError):
            await guard.set_ocp(2.26)

        self.assertFalse(any(name == "set_ocp" for name, _ in app.hass.setter_calls))
        self.assertEqual(app.hass.turn_off_calls, 1)
        self.assertEqual(app.hass.live["switch"], "off")

    async def test_ocp_tightening_is_allowed_after_measured_current_is_below_margin(self):
        app = FakeApp(
            live=live_state(
                set_current=2.16,
                current=2.10,
                ocp=7.30,
            )
        )
        guard = self._guard(app)

        ok = await guard.set_ocp(2.26)

        self.assertTrue(ok)
        self.assertIn(("set_ocp", 2.26), app.hass.setter_calls)
        self.assertEqual(app.hass.live["switch"], "on")

    async def test_ovp_tightening_refuses_to_cut_through_unsettled_voltage(self):
        app = FakeApp(
            live=live_state(
                set_voltage=14.70,
                voltage=15.20,
                ovp=16.60,
            ),
            target_v=14.70,
            target_i=7.20,
        )
        guard = self._guard(app)
        guard.TRANSITION_SETTLE_TIMEOUT_S = 0.0

        with self.assertRaises(RuntimeSafetyError):
            await guard.set_ovp(14.82)

        self.assertFalse(any(name == "set_ovp" for name, _ in app.hass.setter_calls))
        self.assertEqual(app.hass.turn_off_calls, 1)


if __name__ == "__main__":
    unittest.main()
