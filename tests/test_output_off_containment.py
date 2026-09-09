import unittest
from datetime import datetime, timezone
from types import SimpleNamespace

from runtime_safety import OutputOffNotConfirmed
from runtime_safety_v2 import V2RuntimeSafetyGuard


class DummyHass:
    def __init__(self, live):
        self.live = dict(live)
        self.base_url = ""
        self.turn_off_calls = 0
        self.off_confirms = False

    @staticmethod
    def _entity_metadata(entity_id, data, status):
        return {
            "entity_id": entity_id,
            "status": status,
            "last_updated": data.get("last_updated"),
        }

    async def get_all_live(self):
        return dict(self.live)

    async def turn_off(self, entity_id=None):
        self.turn_off_calls += 1
        if self.off_confirms:
            self.live["switch"] = "off"
            now = datetime.now(timezone.utc).isoformat()
            self.live.setdefault("_meta", {}).setdefault("switch", {}).update(
                {"status": "ok", "last_reported": now, "last_updated": now}
            )
            return True
        return False

    async def turn_on(self, entity_id=None):
        self.live["switch"] = "on"
        return True

    async def set_voltage(self, value):
        return True

    async def set_current(self, value):
        return True

    async def set_ovp(self, value):
        return True

    async def set_ocp(self, value):
        return True


class DummyController:
    is_active = False

    def _recipe_envelope(self):
        return None

    def _get_target_v_i(self, temp_ext=None):
        return 14.8, 1.0


def live_with_switch(state, *, fresh=True):
    now = datetime.now(timezone.utc).isoformat()
    metadata = {
        "status": "ok",
        "last_reported": now if fresh else None,
        "last_updated": now if fresh else None,
    }
    return {
        "switch": state,
        "battery_voltage": None,
        "current": None,
        "temp_ext": None,
        "temp_int": None,
        "_meta": {"switch": metadata},
    }


class OutputOffContainmentTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _guard(live):
        notices = []
        app = SimpleNamespace(
            hass=DummyHass(live),
            charge_controller=DummyController(),
            manual_session_manager=None,
            _charge_notify=notices.append,
        )
        guard = V2RuntimeSafetyGuard(app)
        guard.edge_lease_enforced = False
        guard.OFF_CONFIRMATION_WINDOW_S = 0.0
        guard.OFF_CONFIRMATION_POLL_S = 0.0
        return app, guard, notices

    async def test_unknown_output_is_passive_containment_not_command_loop(self):
        app, guard, notices = self._guard(live_with_switch("unknown"))
        guard._off_unconfirmed = True
        guard._off_unconfirmed_notice_active = True

        with self.assertRaisesRegex(OutputOffNotConfirmed, "unknown/stale"):
            await guard.get_all_live()
        with self.assertRaisesRegex(OutputOffNotConfirmed, "unknown/stale"):
            await guard.get_all_live()

        self.assertEqual(app.hass.turn_off_calls, 0)
        self.assertEqual(notices, [])
        self.assertTrue(guard._off_unconfirmed)

    async def test_one_failed_off_emits_one_alarm_for_same_incident(self):
        app, guard, notices = self._guard(live_with_switch("unknown"))

        with self.assertRaises(OutputOffNotConfirmed):
            await guard._ensure_output_off("synthetic incident")
        with self.assertRaisesRegex(OutputOffNotConfirmed, "unknown/stale"):
            await guard.get_all_live()
        with self.assertRaisesRegex(OutputOffNotConfirmed, "unknown/stale"):
            await guard.get_all_live()

        self.assertEqual(app.hass.turn_off_calls, 1)
        self.assertEqual(len(notices), 1)
        self.assertIn("Output OFF", notices[0])

    async def test_fresh_confirmed_off_self_heals_without_other_telemetry(self):
        app, guard, notices = self._guard(live_with_switch("off"))
        guard._off_unconfirmed = True
        guard._off_unconfirmed_notice_active = True

        observed = await guard.get_all_live()

        self.assertEqual(observed["switch"], "off")
        self.assertFalse(guard._off_unconfirmed)
        self.assertFalse(guard._off_unconfirmed_notice_active)
        self.assertEqual(app.hass.turn_off_calls, 0)
        self.assertEqual(notices, [])

    async def test_fresh_on_retries_off_only_at_bounded_cadence(self):
        app, guard, _notices = self._guard(live_with_switch("on"))
        guard._off_unconfirmed = True
        guard._off_unconfirmed_notice_active = True
        guard.OFF_UNCONFIRMED_RETRY_S = 3600.0

        with self.assertRaisesRegex(OutputOffNotConfirmed, "still reports ON"):
            await guard.get_all_live()
        first_calls = app.hass.turn_off_calls
        with self.assertRaisesRegex(OutputOffNotConfirmed, "still reports ON"):
            await guard.get_all_live()

        self.assertEqual(first_calls, 1)
        self.assertEqual(app.hass.turn_off_calls, 1)
        self.assertTrue(guard._off_unconfirmed)


if __name__ == "__main__":
    unittest.main()
