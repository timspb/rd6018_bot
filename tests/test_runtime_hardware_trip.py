import types
import unittest

from runtime_safety_strict import install_strict_runtime_safety


class FakeHass:
    def __init__(self):
        self.live = {
            "battery_voltage": 14.8,
            "current": 1.0,
            "temp_ext": 25.0,
            "temp_int": 32.0,
            "input_voltage": 64.0,
            "switch": "on",
            "ovp_triggered": "on",
            "ocp_triggered": "off",
            "set_voltage": 14.8,
            "set_current": 2.0,
            "ovp": 14.9,
            "ocp": 2.1,
        }
        self.turn_off_calls = 0

    async def get_all_live(self):
        return dict(self.live)

    async def turn_off(self, entity_id=None):
        self.turn_off_calls += 1
        self.live["switch"] = "off"
        return True

    async def turn_on(self, entity_id=None):
        self.live["switch"] = "on"
        return True

    async def set_voltage(self, value):
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


class FakeApp:
    def __init__(self):
        self.hass = FakeHass()
        self.charge_controller = types.SimpleNamespace(
            is_active=True,
            _recipe_envelope=lambda: types.SimpleNamespace(voltage_ceiling_v=16.5),
        )

    def _charge_notify(self, message):
        pass


class RuntimeHardwareTripTests(unittest.IsolatedAsyncioTestCase):
    async def test_live_ovp_trip_forces_verified_off_before_legacy_dispatch(self):
        app = FakeApp()
        guard = install_strict_runtime_safety(app)
        guard.VERIFY_ATTEMPTS = 2
        guard.VERIFY_DELAY_S = 0.0

        trip_snapshot = await app.hass.get_all_live()

        self.assertEqual(trip_snapshot["ovp_triggered"], "on")
        self.assertEqual(app.hass.turn_off_calls, 1)
        self.assertEqual(app.hass.live["switch"], "off")


if __name__ == "__main__":
    unittest.main()
