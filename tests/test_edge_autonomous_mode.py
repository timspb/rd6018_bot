import unittest

from edge_autonomous_mode import EdgeAutonomousAuthority
from edge_safety_lease import EdgeSafetyLease, EdgeSafetyLeaseConfig, EdgeSafetyLeaseError


class FakeHass:
    def __init__(self):
        self.config = EdgeSafetyLeaseConfig(ack_attempts=2, ack_delay_s=0.0)
        prefix = self.config.renew_entity.removeprefix("button.").removesuffix(
            "_safety_lease_renew"
        )
        self.autonomous = f"binary_sensor.{prefix}_safety_autonomous_mode"
        self.enter = f"button.{prefix}_safety_enter_autonomous"
        self.exit = f"button.{prefix}_safety_exit_autonomous"
        self.states = {
            self.config.renew_entity: "unknown",
            self.config.disarm_entity: "unknown",
            self.config.hands_off_release_entity: "unknown",
            self.config.armed_entity: "off",
            self.config.tripped_entity: "off",
            self.config.boot_quarantine_entity: "off",
            self.config.generation_entity: 10,
            self.config.modbus_age_entity: 1.0,
            self.config.remaining_entity: 0.0,
            self.autonomous: "off",
            self.enter: "unknown",
            self.exit: "unknown",
        }
        self.pressed = []

    async def get_state(self, entity_id):
        return self.states.get(entity_id), {}

    async def press_button(self, entity_id):
        self.pressed.append(entity_id)
        if entity_id == self.enter:
            self.states[self.autonomous] = "on"
            self.states[self.config.generation_entity] += 1
            return True
        if entity_id == self.exit:
            self.states[self.autonomous] = "off"
            self.states[self.config.generation_entity] += 1
            return True
        return True


class EdgeAutonomousModeTests(unittest.IsolatedAsyncioTestCase):
    async def test_enter_requires_and_acks_explicit_persistent_mode(self):
        hass = FakeHass()
        authority = EdgeAutonomousAuthority(EdgeSafetyLease(hass, hass.config))

        state = await authority.enter()

        self.assertTrue(await authority.read_autonomous())
        self.assertFalse(state.armed)
        self.assertEqual(state.generation, 11)
        self.assertEqual(hass.pressed, [hass.enter])
        self.assertTrue(authority.lease.renewals_suspended)

    async def test_exit_is_distinct_and_never_arms_managed_lease(self):
        hass = FakeHass()
        hass.states[hass.autonomous] = "on"
        authority = EdgeAutonomousAuthority(EdgeSafetyLease(hass, hass.config))

        state = await authority.exit()

        self.assertFalse(await authority.read_autonomous())
        self.assertFalse(state.armed)
        self.assertEqual(state.generation, 11)
        self.assertEqual(hass.pressed, [hass.exit])

    async def test_managed_lease_must_be_unarmed_before_autonomous_entry(self):
        hass = FakeHass()
        hass.states[hass.config.armed_entity] = "on"
        hass.states[hass.config.remaining_entity] = hass.config.lease_ttl_s
        authority = EdgeAutonomousAuthority(EdgeSafetyLease(hass, hass.config))

        with self.assertRaisesRegex(EdgeSafetyLeaseError, "unarmed"):
            await authority.enter()

        self.assertEqual(hass.pressed, [])

    async def test_missing_mode_evidence_is_fail_closed(self):
        hass = FakeHass()
        hass.states[hass.autonomous] = "unknown"
        authority = EdgeAutonomousAuthority(EdgeSafetyLease(hass, hass.config))

        with self.assertRaisesRegex(EdgeSafetyLeaseError, "missing/unavailable"):
            await authority.enter()

        self.assertEqual(hass.pressed, [])

    async def test_generation_must_change_for_positive_ack(self):
        hass = FakeHass()

        async def no_generation_press(entity_id):
            hass.pressed.append(entity_id)
            if entity_id == hass.enter:
                hass.states[hass.autonomous] = "on"
                return True
            return True

        hass.press_button = no_generation_press
        authority = EdgeAutonomousAuthority(EdgeSafetyLease(hass, hass.config))

        with self.assertRaisesRegex(EdgeSafetyLeaseError, "not positively acknowledged"):
            await authority.enter()


if __name__ == "__main__":
    unittest.main()
