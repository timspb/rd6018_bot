import asyncio
import unittest

from runtime.telemetry import HALossRecoveryWindow, HALossState


class HALossRecoveryTests(unittest.TestCase):
    def test_loss_before_deadline_does_not_request_containment(self):
        now = [100.0]
        provider = HALossRecoveryWindow(window_s=840.0, clock=lambda: now[0])
        status = asyncio.run(provider.observe_ha_loss())
        self.assertEqual(status.state, HALossState.HA_DEGRADED)
        now[0] = 500.0
        status = asyncio.run(provider.observe_ha_loss())
        self.assertEqual(status.state, HALossState.HA_DEGRADED)
        self.assertFalse(provider.claim_containment())

    def test_direct_probe_is_read_only_and_moves_to_recovering(self):
        now = [200.0]
        calls = []

        async def direct_reader():
            calls.append("read")
            return {"timestamp": now[0], "connection_state": "connected", "voltage": 14.8, "current": 1.2}

        provider = HALossRecoveryWindow(direct_reader=direct_reader, window_s=840.0, clock=lambda: now[0])
        status = asyncio.run(provider.observe_ha_loss())
        self.assertEqual(status.state, HALossState.RECOVERING)
        self.assertEqual(calls, ["read"])
        self.assertIsNotNone(status.last_direct_telemetry_at)

    def test_ha_recovery_returns_to_connected(self):
        now = [300.0]
        provider = HALossRecoveryWindow(window_s=840.0, clock=lambda: now[0])
        asyncio.run(provider.observe_ha_loss())
        provider.observe_ha_success()
        self.assertEqual(provider.status.state, HALossState.HA_CONNECTED)

    def test_timeout_allows_existing_containment_once(self):
        now = [400.0]
        provider = HALossRecoveryWindow(window_s=840.0, clock=lambda: now[0])
        asyncio.run(provider.observe_ha_loss())
        now[0] = 1240.0
        status = asyncio.run(provider.observe_ha_loss())
        self.assertEqual(status.state, HALossState.CONTAINMENT_REQUIRED)
        self.assertTrue(provider.claim_containment())
        self.assertFalse(provider.claim_containment())


if __name__ == "__main__":
    unittest.main()
