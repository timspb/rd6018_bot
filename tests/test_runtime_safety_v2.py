import unittest
from types import SimpleNamespace

from runtime_safety_v2 import V2RuntimeSafetyGuard


class DummyHass:
    def __init__(self, live):
        self.live = dict(live)
        self.base_url = ""

    async def get_all_live(self):
        return dict(self.live)

    async def turn_on(self, entity_id=None):
        self.live["switch"] = "on"
        return True

    async def turn_off(self, entity_id=None):
        self.live["switch"] = "off"
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


class DummyController:
    is_active = True

    def _recipe_envelope(self):
        return None

    def _get_target_v_i(self, temp_ext=None):
        return 14.8, 5.0


class V2RuntimeSafetyTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _live():
        return {
            "battery_voltage": 14.2,
            "current": 2.0,
            "temp_ext": 25.0,
            "temp_int": 35.0,
            "input_voltage": 40.0,
            "switch": "on",
            "ovp_triggered": "off",
            "ocp_triggered": "off",
            "set_voltage": 14.8,
            "set_current": 5.0,
            "ovp": 14.9,
            "ocp": 5.1,
        }

    async def test_low_vin_is_psu_health_evidence_not_charge_authority(self):
        app = SimpleNamespace(
            hass=DummyHass(self._live()),
            charge_controller=DummyController(),
            manual_session_manager=None,
            _charge_notify=lambda *args, **kwargs: None,
        )
        guard = V2RuntimeSafetyGuard(app)
        guard.edge_lease_enforced = False
        live = await guard.get_all_live()
        self.assertEqual(live["input_voltage"], 40.0)
        self.assertEqual(live["switch"], "on")

    async def test_missing_vin_is_not_critical_telemetry(self):
        live = self._live()
        live["input_voltage"] = None
        app = SimpleNamespace(
            hass=DummyHass(live),
            charge_controller=DummyController(),
            manual_session_manager=None,
            _charge_notify=lambda *args, **kwargs: None,
        )
        guard = V2RuntimeSafetyGuard(app)
        guard.edge_lease_enforced = False
        observed = await guard.get_all_live()
        self.assertIsNone(observed["input_voltage"])

    async def test_manual_session_is_managed_and_gets_17_5v_envelope(self):
        controller = DummyController()
        controller.is_active = False
        manager = SimpleNamespace(
            is_active=True,
            request=SimpleNamespace(voltage_v=17.5, current_a=1.0),
        )
        app = SimpleNamespace(
            hass=DummyHass(self._live()),
            charge_controller=controller,
            manual_session_manager=manager,
            _charge_notify=lambda *args, **kwargs: None,
        )
        guard = V2RuntimeSafetyGuard(app)
        guard.edge_lease_enforced = False
        self.assertTrue(guard.controller_active)
        self.assertAlmostEqual(guard._recipe_voltage_ceiling(), 17.5)
        self.assertEqual(guard._stage_target(self._live()), (17.5, 1.0))


if __name__ == "__main__":
    unittest.main()
