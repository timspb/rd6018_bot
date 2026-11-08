"""Regressions for delayed authoritative V2 protection readback."""
import unittest

from runtime.safety.runtime_guard import RuntimeSafetyError
from runtime.safety.strict_guard import install_strict_runtime_safety
from tests.test_runtime_safety import FakeApp


class ProtectionReadbackHeartbeatTests(unittest.IsolatedAsyncioTestCase):
    async def test_ovp_waits_for_later_authoritative_mirror(self):
        app = FakeApp()
        reads = 0

        async def delayed_live():
            nonlocal reads
            reads += 1
            if reads >= 22:
                app.hass.live["ovp_readback_v2"] = 16.6
            return dict(app.hass.live)

        async def accepted_ovp(value):
            app.hass.setter_calls.append(("set_ovp", float(value)))
            app.hass.live["ovp"] = float(value)
            return True

        app.hass.get_all_live = delayed_live
        app.hass.set_ovp = accepted_ovp
        guard = install_strict_runtime_safety(app)
        guard.READBACK_VERIFY_DELAY_S = 0.001
        self.assertTrue(await app.hass.set_ovp(16.6))
        self.assertGreaterEqual(reads, 22)
        self.assertEqual(app.hass.turn_off_calls, 0)

    async def test_unconfirmed_ovp_still_forces_off(self):
        app = FakeApp()

        async def accepted_without_readback(value):
            app.hass.live["ovp"] = float(value)
            return True

        app.hass.set_ovp = accepted_without_readback
        guard = install_strict_runtime_safety(app)
        guard.READBACK_VERIFY_DELAY_S = 0.001
        guard.REGISTER_READBACK_VERIFY_TIMEOUT_S = 0.02
        with self.assertRaises(RuntimeSafetyError):
            await app.hass.set_ovp(16.6)
        self.assertEqual(app.hass.turn_off_calls, 1)
        self.assertEqual(app.hass.live["switch"], "off")

    async def test_ocp_waits_for_later_authoritative_mirror(self):
        app = FakeApp()
        reads = 0

        async def delayed_live():
            nonlocal reads
            reads += 1
            if reads >= 22:
                app.hass.live["ocp_readback_v2"] = 2.6
            return dict(app.hass.live)

        async def accepted_ocp(value):
            app.hass.live["ocp"] = float(value)
            return True

        app.hass.get_all_live = delayed_live
        app.hass.set_ocp = accepted_ocp
        guard = install_strict_runtime_safety(app)
        guard.READBACK_VERIFY_DELAY_S = 0.001
        self.assertTrue(await app.hass.set_ocp(2.6))
        self.assertGreaterEqual(reads, 22)
        self.assertEqual(app.hass.turn_off_calls, 0)
