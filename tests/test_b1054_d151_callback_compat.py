"""B1054: preserve immutable D151 observe(state) ABI without weakening Native freshness.

D151's read-only _fresh_measured_sensor_callbacks installs a one-positional
observe(state) wrapper around ESPHomeTransport._on_state. New transports
also carry generation and source_client; dispatch must check them FIRST.
This fixture reproduces that historical shape, without copying or rewriting
the SHA-pinned collector in the deployed node.
"""
from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from runtime.config.models import RDConfig
from runtime.physical.transports.esp128 import ESPHomeTransport
from tests.test_esp_home_transport import (
    _FakeClient, _config, SensorState, BinarySensorState,
)


class D151LegacyCallbackCompatibility(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        _FakeClient.instances.clear()
        _FakeClient.subscribe_calls = 0
        _FakeClient.remove_calls = 0
        _FakeClient.fail_subscribe = False
        _FakeClient.emit_initial = True
        _FakeClient.return_remover = True
        _FakeClient.connected_state = True
        self.client_patch = patch("runtime.physical.transports.esp128.APIClient", _FakeClient)
        self.env_patch = patch.dict(os.environ, {"ESPHOME_API_KEY": "test-only-key"})
        self.client_patch.start()
        self.env_patch.start()
        self.esp = ESPHomeTransport(_config(), RDConfig(60.0, 18.0, 1000.0))
        await self.esp.discover()

    async def asyncTearDown(self):
        try:
            await self.esp.close()
        finally:
            self.client_patch.stop()
            self.env_patch.stop()

    async def install_legacy_d151(self):
        original = self.esp._on_state
        received = []

        # Exact original D151 callback arity: def observe(state).
        def observe(state):
            original(state)
            if type(state).__name__ == "SensorState":
                received.append((state.key, state.state))
        self.esp._on_state = observe
        await self.esp._ensure_state_subscription()
        return received, original

    async def test_immutable_d151_legacy_wrapper_gets_typed_fresh_sensor_states(self):
        received, original = await self.install_legacy_d151()
        self.assertIn((3, 0.0), received)
        self.assertIn((2, 0.0), received)
        self.assertIn((1, 12.7), received)
        self.assertEqual(_FakeClient.subscribe_calls, 1)
        self.assertEqual(self.esp._state_cache[("SensorInfo", 3)]["SensorState"], 0.0)
        self.esp._on_state = original

    async def test_stale_generation_callback_cannot_reach_legacy_d151_observer(self):
        received, _ = await self.install_legacy_d151()
        previous = tuple(received)
        client = self.esp.client
        old_callback = next(iter(client.callbacks))
        old_generation = self.esp._native_connection_generation
        self.esp._on_connection_closed(
            None, connection_generation=old_generation, source_client=client
        )
        self.assertGreater(self.esp._native_connection_generation, old_generation)
        old_callback(SensorState(3, 1.0))  # stale/ON must NOT create OFF/ON proof
        self.assertEqual(tuple(received), previous)
        self.assertFalse(self.esp._state_cache)

    async def test_foreign_client_callback_cannot_reach_legacy_observer(self):
        received, _ = await self.install_legacy_d151()
        previous = tuple(received)
        old_client = self.esp.client
        old_callback = next(iter(old_client.callbacks))
        try:
            self.esp.client = object()
            old_callback(SensorState(3, 1.0))
            self.assertEqual(tuple(received), previous)
        finally:
            self.esp.client = old_client

    async def test_fresh_callback_after_reconnect_belongs_to_new_generation(self):
        received, _ = await self.install_legacy_d151()
        old_client = self.esp.client
        old_callback = next(iter(old_client.callbacks))
        old_generation = self.esp._native_connection_generation
        self.esp._on_connection_closed(
            None, connection_generation=old_generation, source_client=old_client
        )
        old_client.disconnected = True
        # Keep the *same* D151 one-argument observer across the reconnect.
        # A new generation may report new physical evidence; the old one may not.
        await self.esp._ensure_state_subscription()
        self.assertIsNot(self.esp.client, old_client)
        self.assertGreater(self.esp._native_connection_generation, old_generation)
        self.assertEqual(self.esp._state_cache[("SensorInfo", 3)]["SensorState"], 0.0)
        before_stale = tuple(received)
        old_callback(SensorState(3, 999.0))
        self.assertEqual(tuple(received), before_stale)
        self.assertEqual(self.esp._state_cache[("SensorInfo", 3)]["SensorState"], 0.0)

    async def test_modern_observer_gets_original_generation_and_client(self):
        original = self.esp._on_state
        captured = []

        def observe(state, *, connection_generation=None, source_client=None):
            captured.append((connection_generation, source_client))
            original(state, connection_generation=connection_generation,
                     source_client=source_client)

        self.esp._on_state = observe
        await self.esp._ensure_state_subscription()
        self.assertTrue(captured)
        self.assertTrue(all(g == self.esp._native_connection_generation for g, _ in captured))
        self.assertTrue(all(c is self.esp.client for _, c in captured))

    async def test_unsupported_callback_shape_fails_closed(self):
        calls = []

        def unsupported(state, second_required):
            calls.append(state)

        self.esp._on_state = unsupported
        with self.assertRaises(TypeError):
            await self.esp._ensure_state_subscription()
        self.assertEqual(calls, [])

    async def test_callback_internal_typeerror_is_not_swallowed_or_retried(self):
        calls = []

        def observe(state):
            calls.append(state)
            raise TypeError("callback-internal-error")

        self.esp._on_state = observe
        with self.assertRaisesRegex(TypeError, "callback-internal-error"):
            await self.esp._ensure_state_subscription()
        self.assertEqual(len(calls), 1)

    async def test_new_generation_still_rejects_stale_source_client(self):
        got = []
        self.esp._on_state = lambda state: got.append(state)
        await self.esp._ensure_state_subscription()
        captured = len(got)
        self.esp._dispatch_subscribed_state(
            SensorState(3, 1.0),
            connection_generation=self.esp._native_connection_generation,
            source_client=object(),
        )
        self.assertEqual(len(got), captured)


if __name__ == "__main__":
    unittest.main()
