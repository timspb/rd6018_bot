import unittest
from types import SimpleNamespace

from runtime_safety import RuntimeSafetyError
from runtime_safety_strict import StrictRuntimeSafetyGuard


class AuditHass:
    def __init__(self, *, output_on=False):
        self.base_url = ""
        self.live = {
            "battery_voltage": 14.2,
            "voltage": 14.2 if output_on else 0.0,
            "current": 1.0 if output_on else 0.0,
            "temp_ext": 25.0,
            "temp_int": 32.0,
            "input_voltage": 64.0,
            "switch": "on" if output_on else "off",
            "ovp_triggered": "off",
            "ocp_triggered": "off",
            "set_voltage": 14.8,
            "set_current": 2.0,
            "ovp": 14.9,
            "ocp": 2.1,
        }
        self.turn_on_calls = 0
        self.turn_off_calls = 0
        self.set_current_calls = 0
        self.fail_live_when_on = False

    async def get_all_live(self):
        if self.fail_live_when_on and self.live["switch"] == "on":
            raise RuntimeError("synthetic post-enable telemetry loss")
        return dict(self.live)

    async def turn_on(self, entity_id=None):
        self.turn_on_calls += 1
        self.live["switch"] = "on"
        return True

    async def turn_off(self, entity_id=None):
        self.turn_off_calls += 1
        self.live["switch"] = "off"
        self.live["voltage"] = 0.0
        self.live["current"] = 0.0
        return True

    async def set_voltage(self, value):
        self.live["set_voltage"] = float(value)
        return True

    async def set_current(self, value):
        self.set_current_calls += 1
        self.live["set_current"] = float(value)
        return True

    async def set_ovp(self, value):
        self.live["ovp"] = float(value)
        return True

    async def set_ocp(self, value):
        self.live["ocp"] = float(value)
        return True


class AuditController:
    def __init__(self, active=True):
        self.is_active = active

    def _recipe_envelope(self):
        return SimpleNamespace(voltage_ceiling_v=16.5)

    def _get_target_v_i(self, temp_ext=None):
        return 14.8, 2.0


class StrictRuntimeAuditTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _guard(*, active=True, output_on=False):
        hass = AuditHass(output_on=output_on)
        app = SimpleNamespace(
            hass=hass,
            charge_controller=AuditController(active=active),
            _charge_notify=lambda *args, **kwargs: None,
        )
        guard = StrictRuntimeSafetyGuard(app)
        guard.edge_lease_enforced = False
        guard.VERIFY_ATTEMPTS = 1
        guard.VERIFY_DELAY_S = 0.0
        guard.install()
        return app, guard

    async def test_post_enable_telemetry_exception_is_proved_off_before_escape(self):
        app, _guard = self._guard(active=True, output_on=False)
        app.hass.fail_live_when_on = True

        with self.assertRaises(RuntimeError):
            await app.hass.turn_on()

        self.assertEqual(app.hass.turn_on_calls, 1)
        self.assertGreaterEqual(app.hass.turn_off_calls, 1)
        self.assertEqual(app.hass.live["switch"], "off")

    async def test_unmanaged_live_current_write_forces_off_before_raw_write(self):
        app, _guard = self._guard(active=False, output_on=True)

        with self.assertRaises(RuntimeSafetyError):
            await app.hass.set_current(3.0)

        self.assertEqual(app.hass.set_current_calls, 0)
        self.assertGreaterEqual(app.hass.turn_off_calls, 1)
        self.assertEqual(app.hass.live["switch"], "off")


if __name__ == "__main__":
    unittest.main()
