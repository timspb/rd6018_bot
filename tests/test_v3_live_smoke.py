import unittest
import os
import time
from datetime import datetime
from unittest.mock import patch

from runtime.bench.live import LiveSmokeRunner
from runtime.config import load_config
from runtime.output.bridge import HardwareSnapshot
from runtime.physical.transports import PhysicalSnapshotComparator
from runtime.physical.transports.ha102 import HA102Transport


def _offline_config():
    # Strict ESP profile validation remains intact; no physical connection.
    with patch.dict(os.environ, {"ESPHOME_API_HOST": "127.0.0.1", "ESPHOME_API_PORT": "6053"}):
        return load_config("config")


class V3LiveSmokeTests(unittest.IsolatedAsyncioTestCase):
    async def test_runner_with_mocked_factory(self):
        config = _offline_config()
        runner = LiveSmokeRunner(config)

        class FakeTransport:
            config = type("Profile", (), {"name": "fake", "entities": {"v": "v"}})()

            async def discover(self): return ("v",)
            async def get_snapshot(self):
                return HardwareSnapshot(time.time(), "connected", False, 12, 0, 12.5, 0.1, 25, 12)
            async def get_capabilities(self): return None
            async def health_check(self): return {"connected": True}
            async def close(self): pass

        class FakeFactory:
            def create(self, name): return FakeTransport()

        import runtime.bench.live.runner as module
        original = module.PhysicalTransportFactory
        module.PhysicalTransportFactory = lambda config: FakeFactory()
        try:
            evidence = await runner.run("test")
        finally:
            module.PhysicalTransportFactory = original
        self.assertEqual(len(evidence.runs), 2)
        self.assertEqual([item.quality for item in evidence.runs], ["VALID", "VALID"])
        self.assertEqual(evidence.comparison.status, "MATCH")

    async def test_connected_but_incomplete_snapshot_is_invalid(self):
        config = _offline_config()
        runner = LiveSmokeRunner(config)

        class FakeTransport:
            async def discover(self): return ()
            async def get_snapshot(self): return HardwareSnapshot(1, "connected")
            async def get_capabilities(self): return None
            async def health_check(self): return {"connected": True}
            async def close(self): pass

        class FakeFactory:
            def create(self, name): return FakeTransport()

        import runtime.bench.live.runner as module
        original = module.PhysicalTransportFactory
        module.PhysicalTransportFactory = lambda config: FakeFactory()
        try:
            evidence = await runner.run("test")
        finally:
            module.PhysicalTransportFactory = original
        self.assertEqual([item.quality for item in evidence.runs], ["INVALID", "INVALID"])
        self.assertTrue(all("missing_fields:" in item.errors[0] for item in evidence.runs))

    async def test_stale_ha_source_snapshot_must_be_blocked(self):
        config = _offline_config()
        runner = LiveSmokeRunner(config)
        stale_source_time = "2000-01-01T00:00:00+00:00"
        ha_values = {
            "output_state": "0",
            "voltage": "12.0",
            "current": "0.0",
            "configured_voltage": "12.5",
            "configured_current": "0.1",
            "temperature": "25.0",
            "battery_voltage": "12.0",
        }
        ha_transport = HA102Transport(config.transports["ha102"], config.rd)

        async def fake_get(entity_id):
            key = next(key for key, value in ha_transport.config.entities.items() if value == entity_id)
            return {
                "state": ha_values.get(key),
                "last_reported": stale_source_time,
                "last_updated": stale_source_time,
            }

        ha_transport._get = fake_get
        esp_snapshot = HardwareSnapshot(
            time.time(), "connected", False, 12.0, 0.0, 12.5, 0.1, 25.0, 12.0
        )

        class FakeESPTransport:
            async def discover(self): return ("output",)
            async def get_snapshot(self): return esp_snapshot
            async def get_capabilities(self): return None
            async def health_check(self): return {"connected": True}
            async def close(self): pass

        class FakeFactory:
            def create(self, name):
                return ha_transport if name == "ha102" else FakeESPTransport()

        import runtime.bench.live.runner as module
        original = module.PhysicalTransportFactory
        module.PhysicalTransportFactory = lambda config: FakeFactory()
        try:
            evidence = await runner.run("test")
        finally:
            module.PhysicalTransportFactory = original

        from tools.live_physical_smoke import _payload

        payload = _payload(evidence)
        self.assertEqual(evidence.ha_snapshot.output_state, esp_snapshot.output_state)
        self.assertEqual(evidence.ha_snapshot.measured_voltage, esp_snapshot.measured_voltage)
        self.assertEqual(evidence.ha_snapshot.measured_current, esp_snapshot.measured_current)
        self.assertEqual(evidence.ha_snapshot.configured_voltage, esp_snapshot.configured_voltage)
        self.assertEqual(evidence.ha_snapshot.configured_current, esp_snapshot.configured_current)
        self.assertEqual(evidence.ha_snapshot.temperature, esp_snapshot.temperature)
        self.assertEqual(evidence.ha_snapshot.battery_voltage, esp_snapshot.battery_voltage)
        # A single diagnostic timestamp must reflect the oldest HA source
        # sample, not the time when the HTTP response was fetched.
        self.assertEqual(
            evidence.ha_snapshot.timestamp,
            datetime.fromisoformat(stale_source_time).timestamp(),
        )
        self.assertLess(abs(evidence.esp_snapshot.timestamp - time.time()), 10)
        self.assertEqual([item.quality for item in evidence.runs], ["VALID", "VALID"])
        self.assertEqual(evidence.comparison.status, "MISMATCH")
        self.assertIn("timestamp", evidence.comparison.fields)
        self.assertEqual(payload["status"], "BLOCKED")

    def test_evidence_and_tolerance(self):
        a = HardwareSnapshot(100, "connected", False, 14.4, 2)
        b = HardwareSnapshot(105, "connected", False, 14.44, 2.04)
        self.assertEqual(PhysicalSnapshotComparator.compare(a, b, .06, 10, .06).status, "MATCH")
        self.assertEqual(PhysicalSnapshotComparator.compare(a, b, .01, 1, .01).status, "MISMATCH")
