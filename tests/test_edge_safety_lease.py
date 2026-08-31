import unittest

from edge_safety_lease import (
    EDGE_ENTITY_PREFIX,
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
        prefix = EDGE_ENTITY_PREFIX
        self.states = {
            f"binary_sensor.{prefix}_safety_lease_armed": "off",
            f"binary_sensor.{prefix}_safety_lease_tripped": "off",
            f"binary_sensor.{prefix}_safety_boot_quarantine": "off",
            f"sensor.{prefix}_safety_lease_generation": 10,
            f"sensor.{prefix}_safety_modbus_age": 2.0,
            f"sensor.{prefix}_safety_lease_remaining": 0.0,
        }
        self.presses = []
        self.renew_ack = True
        self.renew_remaining_s = 900.0
        self.disarm_ack = True

    async def get_state(self, entity_id):
        return self.states.get(entity_id), {}

    async def press_button(self, entity_id):
        self.presses.append(entity_id)
        if entity_id.endswith("safety_lease_renew"):
            if self.renew_ack:
                self.states[f"binary_sensor.{EDGE_ENTITY_PREFIX}_safety_lease_armed"] = "on"
                self.states[f"sensor.{EDGE_ENTITY_PREFIX}_safety_lease_generation"] += 1
                self.states[f"sensor.{EDGE_ENTITY_PREFIX}_safety_lease_remaining"] = self.renew_remaining_s
            return True
        if entity_id.endswith("safety_lease_disarm"):
            if self.disarm_ack:
                self.states[f"binary_sensor.{EDGE_ENTITY_PREFIX}_safety_lease_armed"] = "off"
                self.states[f"sensor.{EDGE_ENTITY_PREFIX}_safety_lease_remaining"] = 0.0
            return True
        return False


class EdgeSafetyLeaseTests(unittest.IsolatedAsyncioTestCase):
    def _lease(self, hass=None, clock=None):
        hass = hass or FakeHass()
        clock = clock or Clock()
        config = EdgeSafetyLeaseConfig(ack_attempts=1, ack_delay_s=0.0)
        return hass, clock, EdgeSafetyLease(hass, config, monotonic=clock)

    def test_default_entity_ids_match_deployed_rd6018_node(self):
        config = EdgeSafetyLeaseConfig()
        self.assertEqual(EDGE_ENTITY_PREFIX, "rd6018_rd_6018")
        self.assertEqual(config.lease_ttl_s, 15 * 60)
        self.assertEqual(config.renew_interval_s, 5 * 60)
        self.assertEqual(
            config.armed_entity,
            "binary_sensor.rd6018_rd_6018_safety_lease_armed",
        )
        self.assertEqual(
            config.generation_entity,
            "sensor.rd6018_rd_6018_safety_lease_generation",
        )
        self.assertEqual(
            config.modbus_age_entity,
            "sensor.rd6018_rd_6018_safety_modbus_age",
        )
        self.assertEqual(
            config.remaining_entity,
            "sensor.rd6018_rd_6018_safety_lease_remaining",
        )

    async def test_arm_requires_generation_change_and_fresh_direct_modbus(self):
        hass, clock, lease = self._lease()

        state = await lease.arm()

        self.assertTrue(state.armed)
        self.assertFalse(state.tripped)
        self.assertFalse(state.boot_quarantine)
        self.assertEqual(state.generation, 11)
        self.assertLessEqual(state.modbus_age_s, 20.0)
        self.assertGreaterEqual(
            state.remaining_s,
            lease.config.lease_ttl_s - lease.config.ack_remaining_slack_s,
        )
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
        hass.states[f"sensor.{EDGE_ENTITY_PREFIX}_safety_modbus_age"] = 21.0

        with self.assertRaisesRegex(EdgeSafetyLeaseError, "Modbus is stale"):
            await lease.arm()

        self.assertEqual(hass.presses, [])

    async def test_boot_quarantine_has_explicit_initial_arm_error(self):
        hass, _clock, lease = self._lease()
        hass.states[f"binary_sensor.{EDGE_ENTITY_PREFIX}_safety_boot_quarantine"] = "on"

        with self.assertRaisesRegex(EdgeSafetyLeaseError, "boot quarantine"):
            await lease.arm()

        self.assertEqual(hass.presses, [])

    async def test_latched_trip_has_explicit_initial_arm_error(self):
        hass, _clock, lease = self._lease()
        hass.states[f"binary_sensor.{EDGE_ENTITY_PREFIX}_safety_lease_tripped"] = "on"

        with self.assertRaisesRegex(EdgeSafetyLeaseError, "trip is latched"):
            await lease.arm()

        self.assertEqual(hass.presses, [])

    async def test_missing_telemetry_names_exact_entity(self):
        hass, _clock, lease = self._lease()
        missing = f"sensor.{EDGE_ENTITY_PREFIX}_safety_lease_remaining"
        hass.states[missing] = None

        with self.assertRaisesRegex(EdgeSafetyLeaseError, missing):
            await lease.arm()

        self.assertEqual(hass.presses, [])

    async def test_short_timeout_cannot_ack_a_nominal_fifteen_minute_lease(self):
        hass, _clock, lease = self._lease()
        hass.renew_remaining_s = 450.0

        with self.assertRaises(EdgeSafetyLeaseError):
            await lease.arm()

        self.assertEqual(len(hass.presses), 1)
        self.assertIsNone(lease.last_ack_age_s)

    async def test_five_minute_renewal_cadence_preserves_fifteen_minute_lease(self):
        hass, clock, lease = self._lease()
        await lease.arm()
        generation_key = f"sensor.{EDGE_ENTITY_PREFIX}_safety_lease_generation"
        first_generation = hass.states[generation_key]

        clock.now += 4 * 60
        state = await lease.renew_if_due()
        self.assertEqual(state.generation, first_generation)
        self.assertEqual(len(hass.presses), 1)

        clock.now += 61
        state = await lease.renew_if_due()
        self.assertGreater(state.generation, first_generation)
        self.assertEqual(len(hass.presses), 2)
        self.assertGreaterEqual(
            state.remaining_s,
            lease.config.lease_ttl_s - lease.config.ack_remaining_slack_s,
        )

    async def test_between_renewals_unexpectedly_short_remaining_time_fails(self):
        hass, clock, lease = self._lease()
        await lease.arm()
        clock.now += 2 * 60
        hass.states[f"sensor.{EDGE_ENTITY_PREFIX}_safety_lease_remaining"] = 250.0

        with self.assertRaises(EdgeSafetyLeaseError):
            await lease.renew_if_due()

    async def test_disarm_requires_edge_to_report_not_armed_and_quarantine_clear(self):
        hass, _clock, lease = self._lease()
        await lease.arm()

        self.assertTrue(await lease.disarm())
        self.assertIsNone(lease.last_ack_age_s)

        hass.states[f"binary_sensor.{EDGE_ENTITY_PREFIX}_safety_lease_armed"] = "on"
        hass.disarm_ack = False
        self.assertFalse(await lease.disarm())

    def test_invalid_renewal_geometry_is_rejected(self):
        with self.assertRaises(ValueError):
            EdgeSafetyLease(
                FakeHass(),
                EdgeSafetyLeaseConfig(lease_ttl_s=600.0, renew_interval_s=600.0),
            )


if __name__ == "__main__":
    unittest.main()
