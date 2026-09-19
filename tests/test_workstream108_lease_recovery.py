import asyncio
import unittest
from pathlib import Path

from edge_safety_lease import EDGE_ENTITY_PREFIX, EdgeSafetyLease, EdgeSafetyLeaseConfig


class FakeHass:
    def __init__(self):
        p = EDGE_ENTITY_PREFIX
        self.states = {
            f"binary_sensor.{p}_safety_lease_armed": "off",
            f"binary_sensor.{p}_safety_lease_tripped": "off",
            f"binary_sensor.{p}_safety_boot_quarantine": "off",
            f"sensor.{p}_safety_lease_generation": 10,
            f"sensor.{p}_safety_modbus_age": 1.0,
            f"sensor.{p}_safety_lease_remaining": 0.0,
        }
        self.presses = []

    async def get_state(self, entity_id):
        return self.states.get(entity_id), {}

    async def press_button(self, entity_id):
        self.presses.append(entity_id)
        p = EDGE_ENTITY_PREFIX
        if entity_id.endswith("safety_lease_renew"):
            self.states[f"binary_sensor.{p}_safety_lease_armed"] = "on"
            self.states[f"sensor.{p}_safety_lease_generation"] += 1
            self.states[f"sensor.{p}_safety_lease_remaining"] = 900.0
            return True
        if entity_id.endswith("safety_lease_disarm"):
            self.states[f"binary_sensor.{p}_safety_lease_armed"] = "off"
            self.states[f"sensor.{p}_safety_lease_remaining"] = 0.0
            return True
        return False


class Workstream108LeaseRecoveryTests(unittest.IsolatedAsyncioTestCase):
    def _lease(self):
        hass = FakeHass()
        config = EdgeSafetyLeaseConfig(
            ack_attempts=1,
            ack_delay_s=0.0,
            disarm_ack_attempts=1,
            disarm_ack_delay_s=0.0,
        )
        return hass, EdgeSafetyLease(hass, config)

    async def test_managed_arm_renew_expiry_and_recovery(self):
        hass, lease = self._lease()

        armed = await lease.arm()
        self.assertTrue(armed.armed)
        self.assertEqual(len(hass.presses), 1)

        renewed = await lease.renew(force=True)
        self.assertTrue(renewed.armed)
        self.assertEqual(len(hass.presses), 2)

        # Controlled model of edge expiry: no host STOP/DONE call is made.
        p = EDGE_ENTITY_PREFIX
        hass.states[f"binary_sensor.{p}_safety_lease_armed"] = "off"
        hass.states[f"binary_sensor.{p}_safety_lease_tripped"] = "on"
        hass.states[f"sensor.{p}_safety_lease_remaining"] = 0.0
        expired = await lease.read_state()
        self.assertTrue(expired.tripped)
        self.assertFalse(expired.armed)
        self.assertNotIn("STOP", hass.presses)
        self.assertNotIn("DONE", hass.presses)

        # Recovery is explicit: clear the edge trip in the model, then disarm.
        # No lifecycle event is synthesized by the lease boundary.
        hass.states[f"binary_sensor.{p}_safety_lease_tripped"] = "off"
        self.assertTrue(await lease.disarm())
        recovered = await lease.read_state()
        self.assertFalse(recovered.armed)
        self.assertFalse(recovered.tripped)

    async def test_lease_state_does_not_create_lifecycle_events(self):
        hass, lease = self._lease()
        await lease.arm()
        p = EDGE_ENTITY_PREFIX
        hass.states[f"binary_sensor.{p}_safety_lease_tripped"] = "on"
        hass.states[f"sensor.{p}_safety_lease_remaining"] = 0.0
        await lease.read_state()

        # The lease API exposes authority/readback only; it has no lifecycle event
        # emitter and no controller/session mutation surface.
        self.assertFalse(hasattr(lease, "emit_event"))
        self.assertFalse(hasattr(lease, "stop_session"))
        self.assertFalse(hasattr(lease, "mark_done"))

    def test_arm_requires_managed_controller_and_autonomous_is_separate(self):
        strict = Path("runtime_safety_strict.py").read_text(encoding="utf-8")
        lease_yaml = Path(
            "esphome/packages/rd6018_safety_lease.yaml"
        ).read_text(encoding="utf-8")
        self.assertIn("if not self.controller_active:", strict)
        self.assertIn("await self._arm_edge_lease()", strict)
        self.assertIn("autonomous && !managed", lease_yaml)
        self.assertIn("if (id(rd6018_safety_autonomous_mode)) return;", lease_yaml)

    def test_expiry_is_containment_not_synthetic_done_or_stop(self):
        lease_yaml = Path(
            "esphome/packages/rd6018_safety_lease.yaml"
        ).read_text(encoding="utf-8")
        interval = lease_yaml.split("interval:\n", 1)[1]
        self.assertIn("id(rd6018_safety_lease_tripped) = true;", interval)
        self.assertIn("switch.turn_off: rd6018_safety_output", interval)
        self.assertNotIn("SESSION_STOPPED", interval)
        self.assertNotIn("DONE", interval)


if __name__ == "__main__":
    unittest.main()
