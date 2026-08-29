import unittest

from edge_safety_lease import (
    EdgeSafetyLease,
    EdgeSafetyLeaseConfig,
    EdgeSafetyLeaseError,
)


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


class FakeHass:
    def __init__(self):
        self.states = {
            "binary_sensor.rd_6018_safety_lease_armed": "off",
            "sensor.rd_6018_safety_lease_generation": 10,
            "sensor.rd_6018_safety_modbus_age": 2.0,
            "sensor.rd_6018_safety_lease_remaining": 0.0,
        }
        self.presses = []
        self.renew_ack = True
        self.disarm_ack = True

    async def get_state(self, entity_id):
        return self.states.get(entity_id), {}

    async def press_button(self, entity_id):
        self.presses.append(entity_id)
        if entity_id.endswith("safety_lease_renew"):
            if self.renew_ack:
                self.states["binary_sensor.rd_6018_safety_lease_armed"] = "on"
                self.states["sensor.rd_6018_safety_lease_generation"] += 1
                self.states["sensor.rd_6018_safety_lease_remaining"] = 1800.0
            return True
        if entity_id.endswith("safety_lease_disarm"):
            if self.disarm_ack:
                self.states["binary_sensor.rd_6018_safety_lease_armed"] = "off"
                self.states["sensor.rd_6018_safety_lease_remaining"] = 0.0
            return True
        return False


class EdgeSafetyLeaseTests(unittest.IsolatedAsyncioTestCase):
    def _lease(self, hass=None, clock=None):
        hass = hass or FakeHass()
        clock = clock or Clock()
        config = EdgeSafetyLeaseConfig(ack_attempts=1, ack_delay_s=0.0)
        return hass, clock, EdgeSafetyLease(hass, config, monotonic=clock)

    async def test_arm_requires_generation_change_and_fresh_direct_modbus(self):
        hass, clock, lease = self._lease()

        state = await lease.arm()

        self.assertTrue(state.armed)
        self.assertEqual(state.generation, 11)
        self.assertLessEqual(state.modbus_age_s, 20.0)
        self.assertEqual(lease.last_ack_age_s, 0.0)
        self.assertEqual(len(hass.presses), 1)

    async def test_http_accept_without_generation_change_is_not_an_ack(self):
        hass, _clock, lease = self._lease()
        hass.renew_ack = False

        with self.assertRaises(EdgeSafetyLeaseError):
            await lease.arm()

        self.assertEqual(len(hass.presses), 1)

    async def test_stale_direct_modbus_blocks_renew_before_button_press(self):
        hass, _clock, lease = self._lease()
        hass.states["sensor.rd_6018_safety_modbus_age"] = 21.0

        with self.assertRaises(EdgeSafetyLeaseError):
            await lease.arm()

        self.assertEqual(hass.presses, [])

    async def test_ten_minute_renewal_cadence_preserves_thirty_minute_lease(self):
        hass, clock, lease = self._lease()
        await lease.arm()
        first_generation = hass.states["sensor.rd_6018_safety_lease_generation"]

        clock.now += 9 * 60
        state = await lease.renew_if_due()
        self.assertEqual(state.generation, first_generation)
        self.assertEqual(len(hass.presses), 1)

        clock.now += 61
        state = await lease.renew_if_due()
        self.assertGreater(state.generation, first_generation)
        self.assertEqual(len(hass.presses), 2)
        self.assertGreater(state.remaining_s, lease.config.renew_interval_s)

    async def test_disarm_requires_edge_to_report_not_armed(self):
        hass, _clock, lease = self._lease()
        await lease.arm()

        self.assertTrue(await lease.disarm())
        self.assertIsNone(lease.last_ack_age_s)

        hass.states["binary_sensor.rd_6018_safety_lease_armed"] = "on"
        hass.disarm_ack = False
        self.assertFalse(await lease.disarm())


if __name__ == "__main__":
    unittest.main()
