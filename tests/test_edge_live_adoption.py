import unittest
from datetime import datetime, timedelta, timezone

from edge_live_adoption import EdgeLiveAdoption, EdgeLiveAdoptionConfig
from edge_safety_lease import EdgeSafetyLease, EdgeSafetyLeaseConfig, EdgeSafetyLeaseError


def _iso(age_s: float = 0.0) -> str:
    return (datetime.now(timezone.utc) - timedelta(seconds=float(age_s))).isoformat()


class FakeHass:
    def __init__(self):
        self.lease_config = EdgeSafetyLeaseConfig(ack_attempts=2, ack_delay_s=0.0)
        self.adopt_config = EdgeLiveAdoptionConfig(
            entity="button.test_safety_lease_adopt_live_output",
            protection_entity="sensor.test_protection_status_code",
            ttl_entity="sensor.test_safety_lease_ttl",
        )
        self.states = {
            # HA button entities commonly report unknown even when available.
            self.adopt_config.entity: "unknown",
            self.adopt_config.protection_entity: 0,
            self.adopt_config.ttl_entity: self.lease_config.lease_ttl_s,
            self.lease_config.armed_entity: "off",
            self.lease_config.tripped_entity: "off",
            self.lease_config.boot_quarantine_entity: "off",
            self.lease_config.generation_entity: 21,
            self.lease_config.modbus_age_entity: 1.0,
            self.lease_config.remaining_entity: 0.0,
        }
        self.attrs = {
            self.adopt_config.protection_entity: {
                "_ha_last_reported": _iso(),
                "_ha_last_updated": _iso(),
            }
        }
        self.pressed = []
        self.ack = True
        self.protection_after_press = None

    async def get_state(self, entity_id):
        return self.states.get(entity_id), dict(self.attrs.get(entity_id, {}))

    async def press_button(self, entity_id):
        self.pressed.append(entity_id)
        if entity_id == self.adopt_config.entity and self.ack:
            self.states[self.lease_config.armed_entity] = "on"
            self.states[self.lease_config.remaining_entity] = self.lease_config.lease_ttl_s
            self.states[self.lease_config.generation_entity] += 1
            if self.protection_after_press is not None:
                self.states[self.adopt_config.protection_entity] = self.protection_after_press
                self.attrs[self.adopt_config.protection_entity] = {
                    "_ha_last_reported": _iso(),
                    "_ha_last_updated": _iso(),
                }
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

    async def test_unknown_button_state_is_available_not_missing(self):
        hass = FakeHass()
        lease = EdgeSafetyLease(hass, hass.lease_config)
        adoption = EdgeLiveAdoption(lease, hass.adopt_config)

        prepared = await adoption.prepare()

        self.assertEqual(prepared.generation, 21)
        self.assertEqual(hass.pressed, [])

    async def test_missing_entity_fails_before_command(self):
        hass = FakeHass()
        hass.states.pop(hass.adopt_config.entity)
        lease = EdgeSafetyLease(hass, hass.lease_config)
        adoption = EdgeLiveAdoption(lease, hass.adopt_config)

        with self.assertRaisesRegex(EdgeSafetyLeaseError, "missing/unavailable"):
            await adoption.prepare()
        self.assertEqual(hass.pressed, [])

    async def test_unavailable_entity_fails_before_command(self):
        hass = FakeHass()
        hass.states[hass.adopt_config.entity] = "unavailable"
        lease = EdgeSafetyLease(hass, hass.lease_config)
        adoption = EdgeLiveAdoption(lease, hass.adopt_config)

        with self.assertRaisesRegex(EdgeSafetyLeaseError, "missing/unavailable"):
            await adoption.prepare()
        self.assertEqual(hass.pressed, [])

    async def test_missing_ttl_contract_blocks_before_edge_command(self):
        hass = FakeHass()
        hass.states.pop(hass.adopt_config.ttl_entity)
        lease = EdgeSafetyLease(hass, hass.lease_config)
        adoption = EdgeLiveAdoption(lease, hass.adopt_config)

        with self.assertRaisesRegex(EdgeSafetyLeaseError, "TTL contract entity"):
            await adoption.prepare()

        self.assertEqual(hass.pressed, [])

    async def test_old_thirty_minute_edge_is_rejected_before_edge_command(self):
        hass = FakeHass()
        hass.states[hass.adopt_config.ttl_entity] = 1800.0
        lease = EdgeSafetyLease(hass, hass.lease_config)
        adoption = EdgeLiveAdoption(lease, hass.adopt_config)

        with self.assertRaisesRegex(EdgeSafetyLeaseError, "requires 900s lease TTL, got 1800s"):
            await adoption.prepare()

        self.assertEqual(hass.pressed, [])
        self.assertTrue(lease.renewals_suspended)

    async def test_missing_raw_protection_code_blocks_before_edge_command(self):
        hass = FakeHass()
        hass.states.pop(hass.adopt_config.protection_entity)
        lease = EdgeSafetyLease(hass, hass.lease_config)
        adoption = EdgeLiveAdoption(lease, hass.adopt_config)

        with self.assertRaisesRegex(EdgeSafetyLeaseError, "protection-code entity"):
            await adoption.prepare()

        self.assertEqual(hass.pressed, [])
        self.assertTrue(lease.renewals_suspended)

    async def test_legacy_no_trip_cannot_replace_raw_protection_code(self):
        hass = FakeHass()
        hass.states.pop(hass.adopt_config.protection_entity)
        # Legacy bits saying "no OVP/no OCP" are intentionally irrelevant to D061.
        hass.states["binary_sensor.test_over_voltage_protection"] = "off"
        hass.states["binary_sensor.test_over_current_protection"] = "off"
        lease = EdgeSafetyLease(hass, hass.lease_config)
        adoption = EdgeLiveAdoption(lease, hass.adopt_config)

        with self.assertRaisesRegex(EdgeSafetyLeaseError, "protection-code entity"):
            await adoption.prepare()

        self.assertEqual(hass.pressed, [])

    async def test_raw_opp_blocks_before_edge_command(self):
        hass = FakeHass()
        hass.states[hass.adopt_config.protection_entity] = 3
        lease = EdgeSafetyLease(hass, hass.lease_config)
        adoption = EdgeLiveAdoption(lease, hass.adopt_config)

        with self.assertRaisesRegex(EdgeSafetyLeaseError, "OPP"):
            await adoption.prepare()

        self.assertEqual(hass.pressed, [])

    async def test_stale_raw_protection_blocks_before_edge_command(self):
        hass = FakeHass()
        hass.attrs[hass.adopt_config.protection_entity] = {
            "_ha_last_reported": _iso(hass.lease_config.max_modbus_age_s + 5.0)
        }
        lease = EdgeSafetyLease(hass, hass.lease_config)
        adoption = EdgeLiveAdoption(lease, hass.adopt_config)

        with self.assertRaisesRegex(EdgeSafetyLeaseError, "protection status is stale"):
            await adoption.prepare()

        self.assertEqual(hass.pressed, [])

    async def test_missing_raw_protection_timestamp_blocks_before_edge_command(self):
        hass = FakeHass()
        hass.attrs[hass.adopt_config.protection_entity] = {}
        lease = EdgeSafetyLease(hass, hass.lease_config)
        adoption = EdgeLiveAdoption(lease, hass.adopt_config)

        with self.assertRaisesRegex(EdgeSafetyLeaseError, "freshness timestamp"):
            await adoption.prepare()

        self.assertEqual(hass.pressed, [])

    async def test_successful_adoption_keeps_raw_protection_gate_on_every_managed_poll(self):
        hass = FakeHass()
        lease = EdgeSafetyLease(hass, hass.lease_config)
        adoption = EdgeLiveAdoption(lease, hass.adopt_config)
        prepared = await adoption.prepare()
        await adoption.adopt(expected_generation=prepared.generation)

        hass.states[hass.adopt_config.protection_entity] = "unavailable"
        with self.assertRaisesRegex(EdgeSafetyLeaseError, "protection-code entity"):
            await lease.renew_if_due()

        self.assertEqual(hass.pressed, [hass.adopt_config.entity])

    async def test_post_ack_raw_protection_loss_keeps_renewals_suspended(self):
        hass = FakeHass()
        hass.protection_after_press = 3
        lease = EdgeSafetyLease(hass, hass.lease_config)
        adoption = EdgeLiveAdoption(lease, hass.adopt_config)
        prepared = await adoption.prepare()

        with self.assertRaisesRegex(EdgeSafetyLeaseError, "OPP"):
            await adoption.adopt(expected_generation=prepared.generation)

        self.assertTrue(lease.renewals_suspended)
        self.assertEqual(hass.pressed, [hass.adopt_config.entity])

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

    def test_default_entities_are_derived_from_deployed_renew_entity(self):
        hass = FakeHass()
        lease = EdgeSafetyLease(hass, hass.lease_config)
        adoption = EdgeLiveAdoption(lease)

        self.assertEqual(
            adoption.config.entity,
            hass.lease_config.renew_entity.replace(
                "_safety_lease_renew",
                "_safety_lease_adopt_live_output",
            ),
        )
        prefix = hass.lease_config.renew_entity.removeprefix("button.").removesuffix(
            "_safety_lease_renew"
        )
        self.assertEqual(
            adoption.config.protection_entity,
            f"sensor.{prefix}_protection_status_code",
        )
        self.assertEqual(
            adoption.config.ttl_entity,
            f"sensor.{prefix}_safety_lease_ttl",
        )


if __name__ == "__main__":
    unittest.main()
