import asyncio
import unittest

from edge_safety_lease import EdgeSafetyLease, EdgeSafetyLeaseConfig, EdgeSafetyLeaseError


class FakeHass:
    def __init__(self):
        self.config = EdgeSafetyLeaseConfig(ack_attempts=2, ack_delay_s=0.0)
        self.states = {
            self.config.renew_entity: "unknown",
            self.config.disarm_entity: "unknown",
            self.config.hands_off_release_entity: "unknown",
            self.config.armed_entity: "on",
            self.config.tripped_entity: "off",
            self.config.boot_quarantine_entity: "off",
            self.config.generation_entity: 10,
            self.config.modbus_age_entity: 1.0,
            self.config.remaining_entity: 850.0,
        }
        self.pressed = []

    async def get_state(self, entity_id):
        return self.states.get(entity_id), {}

    async def press_button(self, entity_id):
        self.pressed.append(entity_id)
        if entity_id == self.config.hands_off_release_entity:
            self.states[self.config.armed_entity] = "off"
            self.states[self.config.remaining_entity] = 0.0
            self.states[self.config.generation_entity] += 1
            return True
        if entity_id == self.config.renew_entity:
            self.states[self.config.armed_entity] = "on"
            self.states[self.config.remaining_entity] = self.config.lease_ttl_s
            self.states[self.config.generation_entity] += 1
            return True
        return True


class EdgeHandsOffReleaseTests(unittest.IsolatedAsyncioTestCase):
    async def test_live_hands_off_release_has_distinct_positive_ack(self):
        hass = FakeHass()
        lease = EdgeSafetyLease(hass, hass.config)
        lease.suspend_renewals()

        prepared = await lease.prepare_hands_off_release()
        released = await lease.release_to_hands_off(
            expected_generation=prepared.generation
        )

        self.assertTrue(lease.renewals_suspended)
        self.assertFalse(released.armed)
        self.assertEqual(released.generation, prepared.generation + 1)
        self.assertEqual(released.remaining_s, 0.0)
        self.assertEqual(
            hass.pressed,
            [hass.config.hands_off_release_entity],
        )

    async def test_missing_release_entity_fails_before_edge_command(self):
        hass = FakeHass()
        hass.states.pop(hass.config.hands_off_release_entity)
        lease = EdgeSafetyLease(hass, hass.config)
        lease.suspend_renewals()

        with self.assertRaisesRegex(EdgeSafetyLeaseError, "missing/unavailable"):
            await lease.prepare_hands_off_release()

        self.assertEqual(hass.pressed, [])

    async def test_suspended_renewal_cannot_race_after_hands_off_intent(self):
        hass = FakeHass()
        lease = EdgeSafetyLease(hass, hass.config)
        lease.suspend_renewals()

        with self.assertRaisesRegex(EdgeSafetyLeaseError, "suspended"):
            await lease.renew_if_due()

        self.assertNotIn(hass.config.renew_entity, hass.pressed)

    async def test_fresh_arm_explicitly_reopens_renewal_authority(self):
        hass = FakeHass()
        # Simulate the normal verified-OFF state required for a new initial arm.
        hass.states[hass.config.armed_entity] = "off"
        hass.states[hass.config.remaining_entity] = 0.0
        lease = EdgeSafetyLease(hass, hass.config)
        lease.suspend_renewals()

        state = await lease.arm()

        self.assertFalse(lease.renewals_suspended)
        self.assertTrue(state.armed)
        self.assertEqual(state.remaining_s, hass.config.lease_ttl_s)


if __name__ == "__main__":
    unittest.main()
