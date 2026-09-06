import types
import unittest
from unittest.mock import patch

from diagnostic_probe import current_readback_evidence
from rd6018_telemetry import canonical_programmed_readback
from runtime_safety import RuntimeSafetyError, RuntimeSafetyGuard


def live_state(*, v2_age_s=0.0, include_v2=True, legacy_current=2.0, v2_current=2.0):
    live = {
        "battery_voltage": 14.6,
        "current": 1.0,
        "temp_ext": 25.0,
        "temp_int": 32.0,
        "input_voltage": 64.0,
        "switch": "on",
        "ovp_triggered": "off",
        "ocp_triggered": "off",
        "set_voltage": 14.8,
        "set_current": legacy_current,
        "ovp": 14.9,
        "ocp": 2.1,
        "_meta": {},
    }
    if include_v2:
        live["set_current_readback_v2"] = v2_current
        live["_meta"]["set_current_readback_v2"] = {
            "status": "ok",
            "age_s": v2_age_s,
        }
    return live


class FakeController:
    is_active = True

    def _recipe_envelope(self):
        return types.SimpleNamespace(voltage_ceiling_v=16.5)


class FakeHass:
    def __init__(self, live, *, mirror_v2=False):
        self.live = live
        self.mirror_v2 = mirror_v2
        self.turn_off_calls = 0
        self.set_current_calls = 0

    async def get_all_live(self):
        return dict(self.live)

    async def turn_on(self, entity_id=None):
        self.live["switch"] = "on"
        return True

    async def turn_off(self, entity_id=None):
        self.turn_off_calls += 1
        self.live["switch"] = "off"
        return True

    async def set_voltage(self, value):
        self.live["set_voltage"] = float(value)
        return True

    async def set_current(self, value):
        self.set_current_calls += 1
        self.live["set_current"] = float(value)
        if self.mirror_v2:
            self.live["set_current_readback_v2"] = float(value)
            self.live["_meta"]["set_current_readback_v2"] = {
                "status": "ok",
                "age_s": 0.0,
            }
        return True

    async def set_ovp(self, value):
        self.live["ovp"] = float(value)
        return True

    async def set_ocp(self, value):
        self.live["ocp"] = float(value)
        return True


class FakeApp:
    def __init__(self, live, *, mirror_v2=False):
        self.hass = FakeHass(live, mirror_v2=mirror_v2)
        self.charge_controller = FakeController()
        self.notices = []

    def _charge_notify(self, message):
        self.notices.append(message)


class CurrentReadbackAuthorityTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _guard(app):
        guard = RuntimeSafetyGuard(app)
        guard.OFF_CONFIRMATION_WINDOW_S = 0.0
        guard.OFF_CONFIRMATION_POLL_S = 0.0
        guard.READBACK_VERIFY_ATTEMPTS = 1
        guard.READBACK_VERIFY_DELAY_S = 0.0
        guard.install()
        return guard

    async def test_fresh_v2_current_readback_is_runtime_authority(self):
        app = FakeApp(live_state(legacy_current=99.0, v2_current=2.0))
        self._guard(app)

        observed = await app.hass.get_all_live()

        self.assertEqual(observed["set_current"], 99.0)
        self.assertEqual(canonical_programmed_readback(observed, "set_current"), 2.0)
        self.assertEqual(app.hass.turn_off_calls, 0)

    async def test_stale_v2_current_fails_closed_without_legacy_fallback(self):
        app = FakeApp(live_state(v2_age_s=30.0, legacy_current=2.0, v2_current=2.0))
        self._guard(app)

        with self.assertRaisesRegex(RuntimeSafetyError, "authoritative current readback V2"):
            await app.hass.get_all_live()

        self.assertEqual(app.hass.turn_off_calls, 1)
        self.assertEqual(app.hass.live["switch"], "off")

    async def test_missing_v2_current_fails_closed_without_legacy_fallback(self):
        app = FakeApp(live_state(include_v2=False, legacy_current=2.0))
        self._guard(app)

        with self.assertRaisesRegex(RuntimeSafetyError, "authoritative current readback V2"):
            await app.hass.get_all_live()

        self.assertEqual(app.hass.turn_off_calls, 1)
        self.assertEqual(app.hass.live["switch"], "off")

    async def test_current_write_verification_does_not_fallback_to_legacy_number(self):
        app = FakeApp(live_state(legacy_current=2.0, v2_current=2.0), mirror_v2=False)
        self._guard(app)

        with self.assertRaisesRegex(RuntimeSafetyError, "current readback"):
            await app.hass.set_current(1.5)

        self.assertEqual(app.hass.set_current_calls, 1)
        self.assertEqual(app.hass.live["set_current"], 1.5)
        self.assertEqual(app.hass.live["set_current_readback_v2"], 2.0)
        self.assertEqual(app.hass.turn_off_calls, 1)

    async def test_current_write_passes_when_fresh_v2_mirror_confirms(self):
        app = FakeApp(live_state(legacy_current=2.0, v2_current=2.0), mirror_v2=True)
        self._guard(app)

        self.assertTrue(await app.hass.set_current(1.5))

        self.assertEqual(app.hass.live["set_current_readback_v2"], 1.5)
        self.assertEqual(app.hass.turn_off_calls, 0)

    def test_d064_compatibility_facade_delegates_to_canonical_accessor(self):
        live = live_state(legacy_current=0.01, v2_current=2.0)
        with patch("diagnostic_probe.canonical_programmed_readback", return_value=2.0) as accessor:
            self.assertEqual(current_readback_evidence(live), 2.0)
        accessor.assert_called_once_with(live, "set_current")


if __name__ == "__main__":
    unittest.main()
