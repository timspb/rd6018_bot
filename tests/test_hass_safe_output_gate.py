import unittest

from config import ENTITY_MAP
from hass_api import HassClient
from safe_output import SafetyViolation


def live_state(**overrides):
    base = {
        "battery_voltage": 12.4,
        "voltage": 0.0,
        "current": 0.0,
        "temp_ext": 25.0,
        "temp_int": 32.0,
        "input_voltage": 64.0,
        "switch": "off",
        "ovp_triggered": "off",
        "ocp_triggered": "off",
        "set_voltage": 16.3,
        "set_current": 2.0,
        "ovp": 16.4,
        "ocp": 2.1,
    }
    base.update(overrides)
    return base


class FakeHassClient(HassClient):
    def __init__(self):
        super().__init__("http://127.0.0.1:8123", token="test")
        self.live = live_state()
        self.service_calls = []

    async def set_value(self, entity_id, value):
        mapping = {
            ENTITY_MAP["set_voltage"]: "set_voltage",
            ENTITY_MAP["set_current"]: "set_current",
            ENTITY_MAP["ovp"]: "ovp",
            ENTITY_MAP["ocp"]: "ocp",
        }
        key = mapping.get(entity_id)
        if key is None:
            return False
        self.live[key] = float(value)
        return True

    async def get_all_live(self):
        return dict(self.live)

    async def _switch_service(self, service, entity_id=None):
        self.service_calls.append(service)
        if service == "turn_on":
            self.live["switch"] = "on"
            # The RD output-voltage sensor follows the programmed setpoint in this
            # synthetic happy path. Post-enable safety intentionally requires this
            # measured channel instead of treating Vset as physical proof.
            self.live["voltage"] = float(self.live["set_voltage"])
        elif service == "turn_off":
            self.live["switch"] = "off"
            self.live["voltage"] = 0.0
        return True


class HassSafeOutputGateTests(unittest.IsolatedAsyncioTestCase):
    async def _program(self, client):
        self.assertTrue(await client.set_ovp(16.4))
        self.assertTrue(await client.set_ocp(2.1))
        self.assertTrue(await client.set_voltage(16.3))
        self.assertTrue(await client.set_current(2.0))

    async def test_direct_turn_on_without_programming_transaction_is_blocked(self):
        client = FakeHassClient()
        self.assertFalse(await client.turn_on())
        self.assertEqual(client.service_calls, [])

    async def test_complete_programming_is_read_back_before_enable(self):
        client = FakeHassClient()
        await self._program(client)

        self.assertTrue(await client.turn_on())
        self.assertEqual(client.service_calls, ["turn_on"])

    async def test_missing_battery_temperature_blocks_enable(self):
        client = FakeHassClient()
        client.live["temp_ext"] = None
        await self._program(client)

        self.assertFalse(await client.turn_on())
        self.assertEqual(client.service_calls, [])

    async def test_missing_internal_temperature_blocks_enable(self):
        client = FakeHassClient()
        client.live["temp_int"] = "unavailable"
        await self._program(client)

        self.assertFalse(await client.turn_on())
        self.assertEqual(client.service_calls, [])

    async def test_hot_power_supply_blocks_enable(self):
        client = FakeHassClient()
        client.live["temp_int"] = 56.0
        await self._program(client)

        self.assertFalse(await client.turn_on())
        self.assertEqual(client.service_calls, [])

    async def test_voltage_programmed_before_ovp_is_not_an_arm_sequence(self):
        client = FakeHassClient()
        await client.set_voltage(16.3)
        await client.set_ocp(2.1)
        await client.set_current(2.0)
        await client.set_ovp(16.4)

        self.assertFalse(await client.turn_on())
        self.assertEqual(client.service_calls, [])

    async def test_recipe_aware_enable_rejects_target_above_recipe_ceiling(self):
        client = FakeHassClient()
        result = await client.safe_enable_output(
            voltage_v=16.4,
            current_a=2.0,
            ovp_v=16.5,
            ocp_a=2.1,
            recipe_voltage_ceiling_v=16.3,
        )

        self.assertFalse(result.enabled)
        self.assertIn(
            SafetyViolation.REQUEST_OVER_RECIPE_CEILING,
            result.violations,
        )
        self.assertEqual(client.service_calls, [])

    async def test_recipe_aware_enable_allows_explicit_expert_ceiling(self):
        client = FakeHassClient()
        result = await client.safe_enable_output(
            voltage_v=17.5,
            current_a=3.0,
            ovp_v=17.6,
            ocp_a=3.1,
            recipe_voltage_ceiling_v=17.5,
        )

        self.assertTrue(result.enabled)
        self.assertEqual(client.service_calls, ["turn_on"])


if __name__ == "__main__":
    unittest.main()
