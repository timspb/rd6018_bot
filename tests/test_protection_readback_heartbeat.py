"""Regressions for delayed authoritative V2 protection readback."""
import unittest

from runtime.safety.runtime_guard import RuntimeSafetyError
from runtime.safety.strict_guard import install_strict_runtime_safety
from tests.test_runtime_safety import FakeApp


class ProtectionReadbackHeartbeatTests(unittest.IsolatedAsyncioTestCase):
    async def test_retired_ovp_ocp_setters_are_not_wrapped_by_runtime_guard(self):
        app = FakeApp()
        original_ovp = app.hass.set_ovp
        original_ocp = app.hass.set_ocp
        guard = install_strict_runtime_safety(app)
        self.assertIsNotNone(guard)
        self.assertIs(app.hass.set_ovp.__func__, original_ovp.__func__)
        self.assertIs(app.hass.set_ocp.__func__, original_ocp.__func__)
        self.assertEqual(app.hass.turn_off_calls, 0)
