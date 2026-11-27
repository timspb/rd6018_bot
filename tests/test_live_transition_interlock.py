import types
import unittest

from runtime.safety.runtime_guard import RuntimeSafetyError
from runtime.safety.strict_guard import StrictRuntimeSafetyGuard


def live_state(**overrides):
    base = {
        "battery_voltage": 14.72,
        "voltage": 14.72,
        "current": 0.09,
        "temp_ext": 23.0,
        "temp_int": 32.0,
        "input_voltage": 64.0,
        "switch": "on",
        "set_voltage": 14.72,
        "set_current": 7.20,
        "set_current_readback_v2": 7.20,
        "set_voltage_readback_v2": 14.72,
        "_meta": {
            "set_voltage_readback_v2": {"status": "ok", "age_s": 0.0},
            "set_current_readback_v2": {"status": "ok", "age_s": 0.0},
        },
    }
    base.update(overrides)
    for source, key in (("set_voltage_readback_v2", "set_voltage"), ("set_current_readback_v2", "set_current")):
        if key in overrides:
            base[source] = float(base[key])
    if "set_current" in overrides and "set_current_readback_v2" not in overrides:
        base["set_current_readback_v2"] = float(base["set_current"])
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
        readback_key = {
            "set_voltage": "set_voltage_readback_v2",
            "set_current": "set_current_readback_v2",
        }.get(key)
        if readback_key:
            self.live[readback_key] = float(value)
            self.live.setdefault("_meta", {})[readback_key] = {
                "status": "ok",
                "age_s": 0.0,
            }
        return True

    async def set_voltage(self, value):
        ok = await self._set("set_voltage", "set_voltage", value)
        if ok and self.follow_voltage_setpoint:
            self.live["voltage"] = float(value)
        return ok

    async def set_current(self, value):
        return await self._set("set_current", "set_current", value)

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
            ),
            target_v=16.00,
            target_i=2.00,
        )
        guard = self._guard(app)

        ok = await guard.set_voltage(16.00)

        self.assertTrue(ok)
        self.assertEqual(app.hass.setter_calls, [("set_voltage", 16.00)])

if __name__ == "__main__":
    unittest.main()
