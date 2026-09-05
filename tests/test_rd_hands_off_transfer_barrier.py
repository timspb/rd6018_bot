import tempfile
import types
import unittest

from rd_control_mode import install_rd_control_mode
from rd_hands_off_release import install_rd_hands_off_release
from runtime_safety import RuntimeSafetyError
from runtime_safety_v2 import V2RuntimeSafetyGuard


class DummyHass:
    def __init__(self):
        self.live = {
            "battery_voltage": 18.0,
            "voltage": 18.15,
            "current": 1.0,
            "temp_ext": "unavailable",
            "temp_int": 30.0,
            "input_voltage": 40.0,
            "switch": "on",
            "ovp_triggered": "off",
            "ocp_triggered": "off",
            "set_voltage": 18.2,
            "set_current": 1.0,
            "ovp": 18.0,
            "ocp": 1.2,
        }
        self.turn_off_calls = 0
        self.turn_on_calls = 0
        self.set_voltage_calls = 0

    async def get_all_live(self):
        return dict(self.live)

    async def turn_off(self, entity_id=None):
        self.turn_off_calls += 1
        self.live["switch"] = "off"
        return True

    async def turn_on(self, entity_id=None):
        self.turn_on_calls += 1
        self.live["switch"] = "on"
        return True

    async def set_voltage(self, value):
        self.set_voltage_calls += 1
        self.live["set_voltage"] = float(value)
        return True

    async def set_current(self, value):
        self.live["set_current"] = float(value)
        return True

    async def set_ovp(self, value):
        self.live["ovp"] = float(value)
        return True

    async def set_ocp(self, value):
        self.live["ocp"] = float(value)
        return True


class DummyController:
    is_active = False

    def _recipe_envelope(self):
        return None

    def start(self, *args, **kwargs):
        self.is_active = True


class HandsOffTransferBarrierTests(unittest.IsolatedAsyncioTestCase):
    async def test_precommit_barrier_blocks_on_and_setpoints_but_keeps_verified_off_direction(self):
        with tempfile.TemporaryDirectory() as tmp:
            hass = DummyHass()
            app = types.SimpleNamespace(
                hass=hass,
                charge_controller=DummyController(),
                manual_session_manager=None,
                rd_control_mode_file=f"{tmp}/mode.json",
                _charge_notify=lambda *args, **kwargs: None,
            )
            guard = V2RuntimeSafetyGuard(app)
            guard.edge_lease_enforced = False
            guard.OFF_CONFIRMATION_WINDOW_S = 0.0
            guard.OFF_CONFIRMATION_POLL_S = 0.0
            guard.install()
            app.runtime_safety_guard = guard

            manager = install_rd_control_mode(app, install_ui=False)
            install_rd_hands_off_release(app, manager)
            manager._release_in_progress = True

            # A non-Pb live state must be readable without triggering the managed
            # guard/lease path during transfer preparation.
            live = await app.hass.get_all_live()
            self.assertEqual(live["set_voltage"], 18.2)
            self.assertEqual(hass.turn_off_calls, 0)

            with self.assertRaises(RuntimeSafetyError):
                await app.hass.turn_on()
            with self.assertRaises(RuntimeSafetyError):
                await app.hass.set_voltage(12.0)

            # OFF is the only managed actuator direction that stays legal until the
            # durable ownership commit.
            self.assertTrue(await app.hass.turn_off())
            self.assertEqual(hass.turn_off_calls, 1)
            self.assertEqual(hass.live["switch"], "off")


if __name__ == "__main__":
    unittest.main()
