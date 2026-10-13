import unittest

from edge_live_adoption import EdgeLiveAdoption, EdgeLiveAdoptionConfig
from edge_safety_lease import EdgeSafetyLease, EdgeSafetyLeaseConfig, EdgeSafetyLeaseError
from hass_api import HassClient


class NativePhysicalBackend:
    """Hardware-free physical backend returning ESPHome-shaped native reports."""

    def __init__(self):
        self.lease = EdgeSafetyLeaseConfig(ack_attempts=1, ack_delay_s=0)
        self.values = {
            "safety_autonomous_mode": False,
            "safety_lease_ttl": 900,
            "protection_status_code": 0,
            "safety_lease_armed": False,
            "safety_lease_tripped": False,
            "safety_boot_quarantine": False,
            "safety_lease_generation": 10,
            "safety_modbus_age": 1,
            "safety_lease_remaining": 0,
        }
        self.types = {
            "safety_autonomous_mode": "BinarySensorState",
            "safety_lease_armed": "BinarySensorState",
            "safety_lease_tripped": "BinarySensorState",
            "safety_boot_quarantine": "BinarySensorState",
        }
        self.ages = {}
        self.button_commands = []
        self.state_reads = []

    async def get_state(self, entity_id):
        self.state_reads.append(entity_id)
        suffix = entity_id.rsplit(".", 1)[-1]
        logical = next((name for name in self.values if suffix.endswith(name)), None)
        if logical is None:
            return None, {"source": "esp_native_api", "status": "missing", "age_s": None}
        suffix = logical
        return self.values[suffix], {
            "source": "esp_native_api",
            "status": "ok",
            "native_type": self.types.get(suffix, "SensorState"),
            "entity_type": "BinarySensorInfo" if self.types.get(suffix) == "BinarySensorState" else "SensorInfo",
            "age_s": self.ages.get(suffix, 0.5),
        }

    async def get_button_info(self, entity_id):
        return {"status": "ok", "exists": True, "native_type": "ButtonInfo"}

    async def press_button(self, entity_id):
        self.button_commands.append(entity_id)
        return True

    async def close(self):
        return None


def make_adoption(backend):
    hass = HassClient(backend=backend)
    lease = EdgeSafetyLease(hass, backend.lease)
    adoption = EdgeLiveAdoption(lease, EdgeLiveAdoptionConfig(
        entity="button.test_safety_lease_adopt_live_output",
        protection_entity="sensor.test_protection_status_code",
        ttl_entity="sensor.test_safety_lease_ttl",
        autonomous_entity="binary_sensor.test_safety_autonomous_mode",
    ))
    return hass, lease, adoption


class D061NativeReadContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_physical_backend_prepare_reads_native_contract_and_reaches_adoptable(self):
        backend = NativePhysicalBackend()
        hass, lease, adoption = make_adoption(backend)
        try:
            state = await adoption.prepare()
            self.assertFalse(state.armed)
            self.assertEqual(state.generation, 10)
            self.assertIn(adoption.config.autonomous_entity, backend.state_reads)
            self.assertIn(adoption.config.ttl_entity, backend.state_reads)
            self.assertIn(adoption.config.protection_entity, backend.state_reads)
            self.assertEqual(backend.button_commands, [])
        finally:
            await hass.close()

    async def test_autonomous_native_negative_cases(self):
        for kind in ("missing", "wrong_type", "true"):
            with self.subTest(kind=kind):
                backend = NativePhysicalBackend()
                if kind == "missing":
                    backend.values.pop("safety_autonomous_mode")
                elif kind == "wrong_type":
                    backend.types["safety_autonomous_mode"] = "SensorState"
                else:
                    backend.values["safety_autonomous_mode"] = True
                hass, _, adoption = make_adoption(backend)
                try:
                    with self.assertRaises(EdgeSafetyLeaseError):
                        await adoption.prepare()
                    self.assertEqual(backend.button_commands, [])
                finally:
                    await hass.close()

    async def test_ttl_native_negative_cases(self):
        for kind in ("missing", "wrong_type", "stale", "wrong_value"):
            with self.subTest(kind=kind):
                backend = NativePhysicalBackend()
                if kind == "missing":
                    backend.values.pop("safety_lease_ttl")
                elif kind == "wrong_type":
                    backend.types["safety_lease_ttl"] = "BinarySensorState"
                elif kind == "stale":
                    backend.ages["safety_lease_ttl"] = 21
                else:
                    backend.values["safety_lease_ttl"] = 1800
                hass, _, adoption = make_adoption(backend)
                try:
                    with self.assertRaises(EdgeSafetyLeaseError):
                        await adoption.prepare()
                    self.assertEqual(backend.button_commands, [])
                finally:
                    await hass.close()

    async def test_protection_native_negative_cases(self):
        for kind in ("missing", "wrong_type", "stale", "nonzero"):
            with self.subTest(kind=kind):
                backend = NativePhysicalBackend()
                if kind == "missing":
                    backend.values.pop("protection_status_code")
                elif kind == "wrong_type":
                    backend.types["protection_status_code"] = "NumberState"
                elif kind == "stale":
                    backend.ages["protection_status_code"] = 21
                else:
                    backend.values["protection_status_code"] = 3
                hass, _, adoption = make_adoption(backend)
                try:
                    with self.assertRaises(EdgeSafetyLeaseError):
                        await adoption.prepare()
                    self.assertEqual(backend.button_commands, [])
                finally:
                    await hass.close()
