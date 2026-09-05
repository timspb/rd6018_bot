import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from runtime_safety import OutputOffNotConfirmed, RuntimeSafetyError
from runtime_safety_v2 import V2RuntimeSafetyGuard


class DummyHass:
    def __init__(self, live):
        self.live = dict(live)
        self.base_url = ""
        self.turn_off_calls = 0
        self.off_confirms = True
        self.off_raises = False

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
        if self.off_raises:
            raise RuntimeError("synthetic OFF failure")
        if not self.off_confirms:
            return False
        self.live["switch"] = "off"
        metadata = self.live.get("_meta", {}).get("switch")
        if isinstance(metadata, dict):
            reported = datetime.now(timezone.utc).isoformat()
            metadata["last_reported"] = reported
            metadata["last_updated"] = reported
        return True

    async def set_voltage(self, value):
        self.live["set_voltage"] = value
        return True

    async def set_current(self, value):
        self.live["set_current"] = value
        return True

    async def set_ovp(self, value):
        self.live["ovp"] = value
        return True

    async def set_ocp(self, value):
        self.live["ocp"] = value
        return True


class DummyController:
    is_active = True

    def _recipe_envelope(self):
        return None

    def _get_target_v_i(self, temp_ext=None):
        return 14.8, 5.0


class V2RuntimeSafetyTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _live():
        return {
            "battery_voltage": 14.2,
            "voltage": 14.2,
            "current": 2.0,
            "temp_ext": 25.0,
            "temp_int": 35.0,
            "input_voltage": 40.0,
            "switch": "on",
            "is_cv": "on",
            "is_cc": "off",
            "ovp_triggered": "off",
            "ocp_triggered": "off",
            "set_voltage": 14.8,
            "set_current": 5.0,
            "ovp": 14.9,
            "ocp": 5.1,
        }

    @staticmethod
    def _with_freshness(live, *, ages=None, old_static=False):
        ages = dict(ages or {})
        now = datetime.now(timezone.utc)
        dynamic = (
            "battery_voltage",
            "current",
            "temp_ext",
            "temp_int",
            "voltage",
            "switch",
            "is_cv",
            "is_cc",
            "ovp_triggered",
            "ocp_triggered",
        )
        if live.get("protection_code") not in (None, "", "unknown", "unavailable"):
            dynamic = dynamic + ("protection_code",)
        if live.get("regulation_code") not in (None, "", "unknown", "unavailable"):
            dynamic = dynamic + ("regulation_code",)
        meta = {}
        live.setdefault("set_current_readback_v2", live.get("set_current"))
        for key in dynamic:
            age = float(ages.get(key, 0.0))
            reported = (now - timedelta(seconds=age)).isoformat()
            meta[key] = {
                "status": "ok",
                "last_reported": reported,
                "last_updated": reported,
            }
        age = float(ages.get("set_current_readback_v2", 0.0))
        reported = (now - timedelta(seconds=age)).isoformat()
        meta["set_current_readback_v2"] = {
            "status": "ok",
            "last_reported": reported,
            "last_updated": reported,
        }
        if old_static:
            old = (now - timedelta(hours=6)).isoformat()
            for key in ("set_voltage", "set_current", "ovp", "ocp", "input_voltage"):
                meta[key] = {
                    "status": "ok",
                    "last_reported": old,
                    "last_updated": old,
                }
        live["_meta"] = meta
        return live

    @staticmethod
    def _app(live, *, controller=None, manager=None):
        return SimpleNamespace(
            hass=DummyHass(live),
            charge_controller=controller or DummyController(),
            manual_session_manager=manager,
            _charge_notify=lambda *args, **kwargs: None,
        )

    @staticmethod
    def _guard(app):
        guard = V2RuntimeSafetyGuard(app)
        guard.edge_lease_enforced = False
        guard.OFF_CONFIRMATION_WINDOW_S = 0.0
        guard.OFF_CONFIRMATION_POLL_S = 0.0
        return guard

    async def test_low_vin_is_psu_health_evidence_not_charge_authority(self):
        app = self._app(self._with_freshness(self._live()))
        guard = self._guard(app)
        live = await guard.get_all_live()
        self.assertEqual(live["input_voltage"], 40.0)
        self.assertEqual(live["switch"], "on")

    async def test_missing_vin_is_not_critical_telemetry(self):
        live = self._live()
        live["input_voltage"] = None
        live = self._with_freshness(live)
        app = self._app(live)
        guard = self._guard(app)
        observed = await guard.get_all_live()
        self.assertIsNone(observed["input_voltage"])

    async def test_manual_session_is_managed_and_gets_17_5v_envelope(self):
        controller = DummyController()
        controller.is_active = False
        manager = SimpleNamespace(
            is_active=True,
            request=SimpleNamespace(voltage_v=17.5, current_a=1.0),
        )
        app = self._app(self._live(), controller=controller, manager=manager)
        guard = self._guard(app)
        self.assertTrue(guard.controller_active)
        self.assertAlmostEqual(guard._recipe_voltage_ceiling(), 17.5)
        self.assertEqual(guard._stage_target(self._live()), (17.5, 1.0))

    async def test_raw_opp_trip_forces_verified_off(self):
        live = self._live()
        live["protection_code"] = 3
        app = self._app(live)
        guard = self._guard(app)
        with self.assertRaisesRegex(RuntimeSafetyError, "OPP"):
            await guard.get_all_live()
        self.assertEqual(app.hass.live["switch"], "off")
        self.assertEqual(app.hass.turn_off_calls, 1)

    async def test_unknown_raw_protection_forces_verified_off(self):
        live = self._live()
        live["protection_code"] = 9
        app = self._app(live)
        guard = self._guard(app)
        with self.assertRaisesRegex(RuntimeSafetyError, "protection status is unknown"):
            await guard.get_all_live()
        self.assertEqual(app.hass.live["switch"], "off")

    async def test_missing_measured_output_voltage_while_on_fails_closed(self):
        live = self._live()
        live["voltage"] = None
        app = self._app(live)
        guard = self._guard(app)
        with self.assertRaisesRegex(RuntimeSafetyError, "telemetry voltage"):
            await guard.get_all_live()
        self.assertEqual(app.hass.live["switch"], "off")

    async def test_measured_output_voltage_over_recipe_ceiling_fails_closed(self):
        live = self._live()
        live["voltage"] = 16.7
        live["ovp"] = 17.0
        live = self._with_freshness(live)
        app = self._app(live)
        guard = self._guard(app)
        with self.assertRaisesRegex(RuntimeSafetyError, "measured output voltage"):
            await guard.get_all_live()
        self.assertEqual(app.hass.live["switch"], "off")

    async def test_measured_current_uses_working_12a_ceiling_not_ocp_ceiling(self):
        live = self._live()
        live["set_current"] = 12.0
        live["ocp"] = 12.2
        live["current"] = 12.10
        live = self._with_freshness(live)
        app = self._app(live)
        guard = self._guard(app)
        with self.assertRaisesRegex(RuntimeSafetyError, "working-current"):
            await guard.get_all_live()
        self.assertEqual(app.hass.live["switch"], "off")

    async def test_stale_battery_temperature_fails_closed_while_output_is_on(self):
        live = self._with_freshness(self._live(), ages={"temp_ext": 30.0})
        app = self._app(live)
        guard = self._guard(app)
        with self.assertRaisesRegex(RuntimeSafetyError, "temp_ext stale"):
            await guard.get_all_live()
        self.assertEqual(app.hass.live["switch"], "off")
        self.assertEqual(app.hass.turn_off_calls, 1)

    async def test_stale_measured_output_voltage_fails_closed(self):
        live = self._with_freshness(self._live(), ages={"voltage": 30.0})
        app = self._app(live)
        guard = self._guard(app)
        with self.assertRaisesRegex(RuntimeSafetyError, "voltage stale"):
            await guard.get_all_live()
        self.assertEqual(app.hass.live["switch"], "off")

    async def test_stale_output_switch_state_fails_closed(self):
        live = self._with_freshness(self._live(), ages={"switch": 30.0})
        app = self._app(live)
        guard = self._guard(app)
        with self.assertRaisesRegex(RuntimeSafetyError, "switch stale"):
            await guard.get_all_live()
        self.assertEqual(app.hass.live["switch"], "off")

    async def test_stale_legacy_protection_state_fails_closed(self):
        live = self._with_freshness(self._live(), ages={"ovp_triggered": 30.0})
        app = self._app(live)
        guard = self._guard(app)
        with self.assertRaisesRegex(RuntimeSafetyError, "ovp_triggered stale"):
            await guard.get_all_live()
        self.assertEqual(app.hass.live["switch"], "off")

    async def test_stale_raw_protection_code_fails_closed(self):
        live = self._live()
        live["protection_code"] = 0
        live = self._with_freshness(live, ages={"protection_code": 30.0})
        app = self._app(live)
        guard = self._guard(app)
        with self.assertRaisesRegex(RuntimeSafetyError, "protection_code stale"):
            await guard.get_all_live()
        self.assertEqual(app.hass.live["switch"], "off")

    async def test_stale_legacy_regulation_mode_fails_closed(self):
        live = self._with_freshness(self._live(), ages={"is_cv": 30.0})
        app = self._app(live)
        guard = self._guard(app)
        with self.assertRaisesRegex(RuntimeSafetyError, "is_cv stale"):
            await guard.get_all_live()
        self.assertEqual(app.hass.live["switch"], "off")

    async def test_stale_raw_regulation_code_fails_closed(self):
        live = self._live()
        live["regulation_code"] = 0
        live = self._with_freshness(live, ages={"regulation_code": 30.0})
        app = self._app(live)
        guard = self._guard(app)
        with self.assertRaisesRegex(RuntimeSafetyError, "regulation_code stale"):
            await guard.get_all_live()
        self.assertEqual(app.hass.live["switch"], "off")

    async def test_static_readback_timestamps_are_not_used_as_runtime_heartbeat(self):
        live = self._with_freshness(self._live(), old_static=True)
        app = self._app(live)
        guard = self._guard(app)
        observed = await guard.get_all_live()
        self.assertEqual(observed["switch"], "on")
        self.assertEqual(app.hass.turn_off_calls, 0)

    async def test_current_safety_uses_fresh_v2_readback_not_writable_projection(self):
        live = self._with_freshness(self._live())
        live["set_current"] = 99.0
        live["set_current_readback_v2"] = 5.0
        app = self._app(live)
        guard = self._guard(app)
        observed = await guard.get_all_live()
        self.assertEqual(observed["set_current"], 99.0)
        self.assertEqual(guard._current_evidence(observed), 5.0)

    async def test_stale_v2_current_heartbeat_fails_closed(self):
        live = self._with_freshness(self._live(), ages={"set_current_readback_v2": 21.0})
        app = self._app(live)
        guard = self._guard(app)
        with self.assertRaisesRegex(RuntimeSafetyError, "authoritative current readback V2"):
            await guard.get_all_live()
        self.assertEqual(app.hass.live["switch"], "off")

    async def test_missing_v2_current_readback_fails_closed(self):
        live = self._with_freshness(self._live())
        live.pop("set_current_readback_v2")
        live["_meta"].pop("set_current_readback_v2")
        app = self._app(live)
        guard = self._guard(app)
        with self.assertRaisesRegex(RuntimeSafetyError, "authoritative current readback V2"):
            await guard.get_all_live()
        self.assertEqual(app.hass.live["switch"], "off")

    async def test_rd6018_current_rounding_is_within_existing_tolerance(self):
        live = self._with_freshness(self._live())
        live["set_current_readback_v2"] = 0.199999988
        app = self._app(live)
        guard = self._guard(app)
        self.assertTrue(await guard._verify_numeric("set_current", 0.2))

    async def test_freshness_metadata_missing_for_dynamic_channel_fails_closed(self):
        live = self._with_freshness(self._live())
        del live["_meta"]["temp_int"]
        app = self._app(live)
        guard = self._guard(app)
        with self.assertRaisesRegex(RuntimeSafetyError, "metadata missing for temp_int"):
            await guard.get_all_live()
        self.assertEqual(app.hass.live["switch"], "off")

    async def test_off_unconfirmed_retries_shutdown_even_after_controller_retired(self):
        controller = DummyController()
        controller.is_active = False
        live = self._with_freshness(self._live())
        app = self._app(live, controller=controller)
        app.hass.off_confirms = False
        guard = self._guard(app)
        guard._off_unconfirmed = True

        with self.assertRaisesRegex(OutputOffNotConfirmed, "OFF"):
            await guard.get_all_live()

        self.assertTrue(guard._off_unconfirmed)
        self.assertEqual(app.hass.live["switch"], "on")
        self.assertEqual(app.hass.turn_off_calls, 1)
        self.assertIsNone(guard._orphan_output_seen_at)

        app.hass.off_confirms = True
        observed = await guard.get_all_live()
        self.assertEqual(observed["switch"], "off")
        self.assertFalse(guard._off_unconfirmed)
        self.assertEqual(app.hass.turn_off_calls, 2)
        self.assertIsNone(guard._orphan_output_seen_at)

    async def test_off_unconfirmed_with_unknown_switch_still_attempts_shutdown(self):
        controller = DummyController()
        controller.is_active = False
        live = self._with_freshness(self._live())
        live["switch"] = "unknown"
        app = self._app(live, controller=controller)
        app.hass.off_confirms = False
        guard = self._guard(app)
        guard._off_unconfirmed = True

        with self.assertRaises(OutputOffNotConfirmed):
            await guard.get_all_live()

        self.assertEqual(app.hass.turn_off_calls, 1)
        self.assertTrue(guard._off_unconfirmed)

    def test_v2_metadata_bridge_preserves_home_assistant_last_reported(self):
        app = self._app(self._live())
        self._guard(app)
        now = datetime.now(timezone.utc).isoformat()
        old = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        metadata = app.hass._entity_metadata(
            "sensor.example",
            {"last_updated": old, "last_reported": now},
            "ok",
        )
        self.assertEqual(metadata["last_updated"], old)
        self.assertEqual(metadata["last_reported"], now)


if __name__ == "__main__":
    unittest.main()
