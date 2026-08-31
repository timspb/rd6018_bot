import unittest

from edge_live_adoption import EdgeLiveAdoption, EdgeLiveAdoptionConfig
from edge_safety_lease import EdgeSafetyLease, EdgeSafetyLeaseConfig, EdgeSafetyLeaseError


class FakeHass:
    def __init__(self):
        self.lease_config = EdgeSafetyLeaseConfig(ack_attempts=2, ack_delay_s=0.0)
        self.adopt_config = EdgeLiveAdoptionConfig(
            entity="button.test_safety_lease_adopt_live_output"
        )
        self.states = {
            self.adopt_config.entity: "unknown",
            self.lease_config.armed_entity: "off",
            self.lease_config.tripped_entity: "off",
            self.lease_config.boot_quarantine_entity: "off",
            self.lease_config.generation_entity: 21,
            self.lease_config.modbus_age_entity: 1.0,
            self.lease_config.remaining_entity: 0.0,
        }
        self.pressed = []
        self.ack = True

    async def get_state(self, entity_id):
        return self.states.get(entity_id), {}

    async def press_button(self, entity_id):
        self.pressed.append(entity_id)
        if entity_id == self.adopt_config.entity and self.ack:
            self.states[self.lease_config.armed_entity] = "on"
            self.states[self.lease_config.remaining_entity] = self.lease_config.lease_ttl_s
            self.states[self.lease_config.generation_entity] += 1
        return True


class EdgeLiveAdoptionTests(unittest.IsolatedAsyncioTestCase):
    async def test_live_adoption_has_distinct_positive_ack(self):
        hass = FakeHass()
        lease = EdgeSafetyLease(hass, hass.lease_config)
        adoption = EdgeLiveAdoption(lease, hass.adopt_config)

        prepared = await adoption.prepare()
        self.assertTrue(lease.renewals_suspended)
        adopted = await adoption.adopt(expected_generation=prepared.generation)

        self.assertTrue(adopted.armed)
        self.assertEqual(adopted.generation, prepared.generation + 1)
        self.assertEqual(adopted.remaining_s, hass.lease_config.lease_ttl_s)
        self.assertFalse(lease.renewals_suspended)
        self.assertEqual(hass.pressed, [hass.adopt_config.entity])

    async def test_missing_entity_fails_before_command(self):
        hass = FakeHass()
        hass.states.pop(hass.adopt_config.entity)
        lease = EdgeSafetyLease(hass, hass.lease_config)
        adoption = EdgeLiveAdoption(lease, hass.adopt_config)

        with self.assertRaisesRegex(EdgeSafetyLeaseError, "missing/unavailable"):
            await adoption.prepare()
        self.assertEqual(hass.pressed, [])

    async def test_already_armed_lease_is_not_live_adoptable(self):
        hass = FakeHass()
        hass.states[hass.lease_config.armed_entity] = "on"
        hass.states[hass.lease_config.remaining_entity] = 850.0
        lease = EdgeSafetyLease(hass, hass.lease_config)
        adoption = EdgeLiveAdoption(lease, hass.adopt_config)

        with self.assertRaisesRegex(EdgeSafetyLeaseError, "unarmed HANDS_OFF"):
            await adoption.prepare()
        self.assertEqual(hass.pressed, [])

    async def test_ambiguous_ack_keeps_renewals_suspended(self):
        hass = FakeHass()
        hass.ack = False
        lease = EdgeSafetyLease(hass, hass.lease_config)
        adoption = EdgeLiveAdoption(lease, hass.adopt_config)
        prepared = await adoption.prepare()

        with self.assertRaisesRegex(EdgeSafetyLeaseError, "not positively acknowledged"):
            await adoption.adopt(expected_generation=prepared.generation)

        self.assertTrue(lease.renewals_suspended)
        self.assertEqual(hass.pressed, [hass.adopt_config.entity])

    async def test_generation_change_after_preflight_is_rejected(self):
        hass = FakeHass()
        lease = EdgeSafetyLease(hass, hass.lease_config)
        adoption = EdgeLiveAdoption(lease, hass.adopt_config)
        prepared = await adoption.prepare()
        hass.states[hass.lease_config.generation_entity] += 1

        with self.assertRaisesRegex(EdgeSafetyLeaseError, "generation changed"):
            await adoption.adopt(expected_generation=prepared.generation)
        self.assertEqual(hass.pressed, [])


if __name__ == "__main__":
    unittest.main()
