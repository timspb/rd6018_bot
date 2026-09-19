import asyncio
import unittest

from runtime.output.bridge import HardwareSnapshot
from runtime.telemetry import RuntimeTelemetryProvider, TelemetrySource


class RuntimeTelemetryAuthorityTests(unittest.TestCase):
    def test_prefers_fresh_esp_direct_and_compares_ha(self):
        async def esp():
            return HardwareSnapshot(100.0, "connected", False, 14.8, 1.0, 14.8, 5.0)

        async def ha():
            return HardwareSnapshot(100.0, "connected", False, 14.7, 1.1, 14.8, 5.0)

        provider = RuntimeTelemetryProvider(esp_direct_reader=esp, ha_reader=ha, clock=lambda: 100.5)
        selected, comparison = asyncio.run(provider.collect())
        self.assertEqual(selected.source, TelemetrySource.ESP_DIRECT)
        self.assertAlmostEqual(comparison.differences["voltage"], 0.1)
        self.assertAlmostEqual(comparison.differences["current"], -0.1)

    def test_falls_back_to_ha_when_esp_fails(self):
        async def esp():
            raise ConnectionError("esp down")

        async def ha():
            return HardwareSnapshot(200.0, "connected", False, 13.8, 0.2)

        provider = RuntimeTelemetryProvider(esp_direct_reader=esp, ha_reader=ha, clock=lambda: 200.1)
        selected, comparison = asyncio.run(provider.collect())
        self.assertEqual(selected.source, TelemetrySource.HA)
        self.assertTrue(any(item.startswith("esp_direct:ConnectionError") for item in comparison.failure_modes))

    def test_last_known_and_unknown_are_non_authorizing(self):
        async def esp():
            return HardwareSnapshot(300.0, "connected", False, 14.0, 0.3)

        provider = RuntimeTelemetryProvider(esp_direct_reader=esp, clock=lambda: 300.1)
        selected, _ = asyncio.run(provider.collect())
        self.assertEqual(selected.source, TelemetrySource.ESP_DIRECT)

        provider = RuntimeTelemetryProvider(clock=lambda: 400.0)
        selected, comparison = asyncio.run(provider.collect())
        self.assertEqual(selected.source, TelemetrySource.UNKNOWN)
        self.assertEqual(comparison.selected, TelemetrySource.UNKNOWN)
        self.assertEqual(selected.confidence, 0.0)

    def test_no_writer_methods_are_used(self):
        class Reader:
            async def get_snapshot(self):
                return HardwareSnapshot(500.0, "connected", False, 14.0, 0.3)

            def set_voltage(self, *_):
                raise AssertionError("writer must not be called")

            def turn_on(self, *_):
                raise AssertionError("writer must not be called")

        provider = RuntimeTelemetryProvider(esp_direct_reader=Reader(), clock=lambda: 500.1)
        selected, _ = asyncio.run(provider.collect())
        self.assertEqual(selected.source, TelemetrySource.ESP_DIRECT)


if __name__ == "__main__":
    unittest.main()
