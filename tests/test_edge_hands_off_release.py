import asyncio
import unittest
from types import SimpleNamespace

from edge_safety_lease import EdgeSafetyLease, EdgeSafetyLeaseConfig, EdgeSafetyLeaseError
from hass_api import HassClient


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


class NativeButtonHass(FakeHass):
    def __init__(self, info):
        super().__init__()
        self.info = info
        self.inventory_calls = []

    async def get_button_info(self, entity_id):
        self.inventory_calls.append(entity_id)
        return self.info


class EdgeHandsOffReleaseTests(unittest.IsolatedAsyncioTestCase):
    async def test_hass_client_exposes_native_inventory_only_when_backend_supports_it(self):
        async def info(entity_id):
            return {"status": "ok", "exists": True, "native_type": "ButtonInfo",
                    "entity_id": entity_id}
        native = HassClient(backend=SimpleNamespace(get_button_info=info))
        ha_only = HassClient()
        self.assertTrue(callable(getattr(native, "get_button_info", None)))
        self.assertFalse(callable(getattr(ha_only, "get_button_info", None)))
        self.assertEqual((await native.get_button_info("button.test"))["entity_id"],
                         "button.test")

    async def test_native_button_info_without_state_passes_read_only_preflight(self):
        hass = NativeButtonHass({"status": "ok", "exists": True,
                                 "native_type": "ButtonInfo"})
        lease = EdgeSafetyLease(hass, hass.config)
        lease.suspend_renewals()
        prepared = await lease.prepare_hands_off_release()
        self.assertTrue(prepared.armed)
        self.assertEqual(hass.inventory_calls, [hass.config.hands_off_release_entity])
        self.assertEqual(hass.pressed, [])

    async def test_native_missing_or_wrong_type_fails_closed(self):
        for info in (
            {"status": "missing", "exists": False, "native_type": None},
            {"status": "wrong_type", "exists": True, "native_type": "SwitchInfo"},
        ):
            hass = NativeButtonHass(info)
            lease = EdgeSafetyLease(hass, hass.config)
            lease.suspend_renewals()
            with self.assertRaisesRegex(EdgeSafetyLeaseError, "native button"):
                await lease.prepare_hands_off_release()
            self.assertEqual(hass.pressed, [])

    async def test_native_inventory_transport_failure_fails_closed(self):
        hass = NativeButtonHass(None)
        async def fail(_entity_id):
            raise OSError("disconnected")
        hass.get_button_info = fail
        lease = EdgeSafetyLease(hass, hass.config)
        lease.suspend_renewals()
        with self.assertRaisesRegex(EdgeSafetyLeaseError, "inventory is unavailable"):
            await lease.prepare_hands_off_release()
        self.assertEqual(hass.pressed, [])

    async def test_ha_fallback_rejects_missing_and_unavailable(self):
        for value in (None, "unavailable"):
            hass = FakeHass()
            hass.states[hass.config.hands_off_release_entity] = value
            lease = EdgeSafetyLease(hass, hass.config)
            lease.suspend_renewals()
            with self.assertRaisesRegex(EdgeSafetyLeaseError, "missing/unavailable"):
                await lease.prepare_hands_off_release()
            self.assertEqual(hass.pressed, [])

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
