import unittest
from types import SimpleNamespace

from runtime_safety import RuntimeSafetyError
from runtime_safety_v2 import V2RuntimeSafetyGuard


class _Hass:
    def __init__(self):
        self.base_url = ""
        self.live = {
            "battery_voltage": 14.2,
            "voltage": 14.2,
            "current": 2.0,
            "temp_ext": 25.0,
            "temp_int": 35.0,
            "switch": "on",
            "is_cv": "on",
            "is_cc": "off",
            "ovp_triggered": "off",
            "ocp_triggered": "off",
            "set_voltage": 14.8,
            "set_current": 5.0,
            "ovp": 14.9,
            "ocp": 5.1,
        }
        self.off_calls = 0

    @staticmethod
    def _entity_metadata(entity_id, data, status):
        return {"entity_id": entity_id, "status": status}

    async def get_all_live(self):
        return dict(self.live)

    async def turn_on(self, entity_id=None):
        return True

    async def turn_off(self, entity_id=None):
        self.off_calls += 1
        self.live["switch"] = "off"
        return True

    async def set_voltage(self, value):
        return True

    async def set_current(self, value):
        return True

    async def set_ovp(self, value):
        return True

    async def set_ocp(self, value):
        return True


class _Controller:
    is_active = True

    def _recipe_envelope(self):
        return None

    def _get_target_v_i(self, temp_ext=None):
        return 14.8, 5.0


class RuntimeMetadataRequiredTests(unittest.IsolatedAsyncioTestCase):
    async def test_managed_energized_session_without_meta_fails_closed(self):
        hass = _Hass()
        app = SimpleNamespace(
            hass=hass,
            charge_controller=_Controller(),
            manual_session_manager=None,
            _charge_notify=lambda *args, **kwargs: None,
        )
        guard = V2RuntimeSafetyGuard(app)
        guard.edge_lease_enforced = False
        guard.OFF_CONFIRMATION_WINDOW_S = 0.0
        guard.OFF_CONFIRMATION_POLL_S = 0.0

        with self.assertRaisesRegex(RuntimeSafetyError, "freshness metadata is missing"):
            await guard.get_all_live()

        self.assertEqual(hass.off_calls, 1)
        self.assertEqual(hass.live["switch"], "off")


if __name__ == "__main__":
    unittest.main()
