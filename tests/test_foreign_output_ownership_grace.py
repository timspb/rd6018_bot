import time
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from runtime_safety import RuntimeSafetyError
from runtime_safety_v2 import V2RuntimeSafetyGuard


def _stamp(age_s=0.0):
    return (datetime.now(timezone.utc) - timedelta(seconds=float(age_s))).isoformat()


def _meta(age_s=0.0):
    stamp = _stamp(age_s)
    return {"status": "ok", "last_reported": stamp, "last_updated": stamp}


def _foreign_live(*, protection_code=0, switch_age=0.0, protection_age=0.0):
    return {
        "switch": "on",
        "protection_code": protection_code,
        # Deliberately not a valid Pb snapshot. These fields must not seize an
        # externally programmed PSU before ownership is explicitly resolved.
        "battery_voltage": None,
        "voltage": None,
        "current": None,
        "temp_ext": "unavailable",
        "temp_int": None,
        "_meta": {
            "switch": _meta(switch_age),
            "protection_code": _meta(protection_age),
        },
    }


class FakeHass:
    def __init__(self, live):
        self.live = dict(live)
        self.turn_off_calls = 0

    @staticmethod
    def _entity_metadata(entity_id, data, status):
        return {
            "entity_id": entity_id,
            "status": status,
            "last_updated": data.get("last_updated"),
        }

    async def get_all_live(self):
        return dict(self.live)

    async def turn_on(self, entity_id=None):
        self.live["switch"] = "on"
        return True

    async def turn_off(self, entity_id=None):
        self.turn_off_calls += 1
        self.live["switch"] = "off"
        stamp = _stamp()
        self.live.setdefault("_meta", {})["switch"] = {
            "status": "ok",
            "last_reported": stamp,
            "last_updated": stamp,
        }
        return True

    async def set_voltage(self, value):
        return True

    async def set_current(self, value):
        return True

    async def set_ovp(self, value):
        return True

    async def set_ocp(self, value):
        return True


class ForeignOutputOwnershipGraceTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _system(live, *, managed=False):
        controller = SimpleNamespace(is_active=bool(managed))
        app = SimpleNamespace(
            hass=FakeHass(live),
            charge_controller=controller,
            manual_session_manager=None,
            _charge_notify=lambda *args, **kwargs: None,
        )
        guard = V2RuntimeSafetyGuard(app)
        guard.edge_lease_enforced = False
        guard.OFF_CONFIRMATION_WINDOW_S = 0.0
        guard.OFF_CONFIRMATION_POLL_S = 0.0
        return app, controller, guard

    async def test_foreign_output_gets_decision_window_without_pb_telemetry(self):
        app, _controller, guard = self._system(_foreign_live())

        observed = await guard.get_all_live()

        self.assertEqual(observed["switch"], "on")
        self.assertIsNotNone(guard._orphan_output_seen_at)
        self.assertEqual(app.hass.turn_off_calls, 0)

    async def test_foreign_output_window_expires_to_verified_off(self):
        app, _controller, guard = self._system(_foreign_live())
        await guard.get_all_live()
        guard._orphan_output_seen_at = time.monotonic() - guard.ORPHAN_OUTPUT_GRACE_S - 1.0

        with self.assertRaisesRegex(RuntimeSafetyError, "ownership decision"):
            await guard.get_all_live()

        self.assertEqual(app.hass.turn_off_calls, 1)
        self.assertEqual(app.hass.live["switch"], "off")

    async def test_foreign_output_protection_trip_still_forces_immediate_off(self):
        app, _controller, guard = self._system(_foreign_live(protection_code=1))

        with self.assertRaisesRegex(RuntimeSafetyError, "OVP"):
            await guard.get_all_live()

        self.assertEqual(app.hass.turn_off_calls, 1)
        self.assertEqual(app.hass.live["switch"], "off")
        self.assertIsNone(guard._orphan_output_seen_at)

    async def test_foreign_output_stale_protection_evidence_is_not_graced(self):
        app, _controller, guard = self._system(
            _foreign_live(protection_code=0, protection_age=30.0)
        )

        with self.assertRaisesRegex(RuntimeSafetyError, "protection_code stale"):
            await guard.get_all_live()

        self.assertEqual(app.hass.turn_off_calls, 1)

    async def test_foreign_output_stale_switch_evidence_is_not_graced(self):
        app, _controller, guard = self._system(_foreign_live(switch_age=30.0))

        with self.assertRaisesRegex(RuntimeSafetyError, "switch stale"):
            await guard.get_all_live()

        self.assertEqual(app.hass.turn_off_calls, 1)

    async def test_foreign_output_observed_psu_overtemperature_is_immediate_off(self):
        live = _foreign_live()
        live["temp_int"] = 60.0
        app, _controller, guard = self._system(live)

        with self.assertRaisesRegex(RuntimeSafetyError, "temperature 60.0C"):
            await guard.get_all_live()

        self.assertEqual(app.hass.turn_off_calls, 1)

    async def test_managed_session_still_fails_closed_on_missing_battery_temperature(self):
        live = _foreign_live()
        live.update(
            {
                "battery_voltage": 14.2,
                "voltage": 14.2,
                "current": 2.0,
                "temp_ext": "unavailable",
                "temp_int": 35.0,
            }
        )
        app, _controller, guard = self._system(live, managed=True)

        with self.assertRaisesRegex(RuntimeSafetyError, "temp_ext"):
            await guard.get_all_live()

        self.assertEqual(app.hass.turn_off_calls, 1)

    async def test_d061_full_preflight_helper_remains_pb_strict(self):
        _app, _controller, guard = self._system(_foreign_live())

        error = guard._critical_telemetry_error(
            _foreign_live(),
            require_programming=True,
        )

        self.assertIsNotNone(error)
        self.assertIn("battery_voltage", error)


if __name__ == "__main__":
    unittest.main()
