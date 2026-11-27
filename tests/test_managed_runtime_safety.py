import asyncio
import time
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from runtime.safety.runtime_guard import OutputOffNotConfirmed, RuntimeSafetyError, RuntimeSafetyGuard
from runtime.safety.managed_guard import ManagedRuntimeSafetyGuard, install_managed_runtime_safety


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
            # Model a switch report received after the OFF command, with room
            # for Windows wall-clock/timestamp quantization.
            reported = (datetime.now(timezone.utc) + timedelta(milliseconds=10)).isoformat()
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


class LeaseOrderHass(DummyHass):
    def __init__(self, live, events):
        super().__init__(live)
        self.events = events

    async def turn_on(self, entity_id=None):
        self.events.append("output_on")
        result = await super().turn_on(entity_id)
        metadata = self.live.get("_meta", {}).get("switch")
        if isinstance(metadata, dict):
            reported = datetime.now(timezone.utc).isoformat()
            metadata["last_reported"] = reported
            metadata["last_updated"] = reported
        return result


class CountingEdgeLease:
    def __init__(self, events):
        self.events = events
        self.arm_calls = 0
        self.renew_calls = 0
        self.disarm_calls = 0
        self.renewals_suspended = True

    async def arm(self):
        self.arm_calls += 1
        self.events.append("lease_arm")
        self.renewals_suspended = False
        return SimpleNamespace(
            armed=True,
            tripped=False,
            boot_quarantine=False,
            generation=self.arm_calls,
            remaining_s=900.0,
            modbus_age_s=1.0,
        )

    async def renew_if_due(self):
        if self.renewals_suspended:
            raise RuntimeError("renewals suspended")
        self.renew_calls += 1
        self.events.append("lease_renew")
        return SimpleNamespace(
            armed=True,
            tripped=False,
            boot_quarantine=False,
            generation=self.arm_calls + self.renew_calls,
            remaining_s=900.0,
            modbus_age_s=1.0,
        )

    async def disarm(self):
        self.disarm_calls += 1
        self.events.append("lease_disarm")
        self.renewals_suspended = True
        return True

    def suspend_renewals(self):
        self.renewals_suspended = True

    def resume_renewals(self):
        self.renewals_suspended = False


class LeaseOrderHass(DummyHass):
    def __init__(self, live, events):
        super().__init__(live)
        self.events = events

    async def turn_on(self, entity_id=None):
        self.events.append("output_on")
        result = await super().turn_on(entity_id)
        metadata = self.live.get("_meta", {}).get("switch")
        if isinstance(metadata, dict):
            reported = datetime.now(timezone.utc).isoformat()
            metadata["last_reported"] = reported
            metadata["last_updated"] = reported
        return result


class CountingEdgeLease:
    def __init__(self, events):
        self.events = events
        self.arm_calls = 0
        self.renew_calls = 0
        self.disarm_calls = 0
        self.renewals_suspended = True

    async def arm(self):
        self.arm_calls += 1
        self.events.append("lease_arm")
        self.renewals_suspended = False
        return SimpleNamespace(
            armed=True,
            tripped=False,
            boot_quarantine=False,
            generation=self.arm_calls,
            remaining_s=900.0,
            modbus_age_s=1.0,
        )

    async def renew_if_due(self):
        if self.renewals_suspended:
            raise RuntimeError("renewals suspended")
        self.renew_calls += 1
        self.events.append("lease_renew")
        return SimpleNamespace(
            armed=True,
            tripped=False,
            boot_quarantine=False,
            generation=self.arm_calls + self.renew_calls,
            remaining_s=900.0,
            modbus_age_s=1.0,
        )

    async def disarm(self):
        self.disarm_calls += 1
        self.events.append("lease_disarm")
        self.renewals_suspended = True
        return True

    def suspend_renewals(self):
        self.renewals_suspended = True

    def resume_renewals(self):
        self.renewals_suspended = False


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
        for key, source in (
            ("set_voltage", "set_voltage_readback_v2"),
            ("set_current", "set_current_readback_v2"),
            ("ovp", "ovp_readback_v2"),
            ("ocp", "ocp_readback_v2"),
        ):
            live.setdefault(source, live.get(key))
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
        for key in ("set_voltage_readback_v2", "ovp_readback_v2", "ocp_readback_v2"):
            age = float(ages.get(key, 0.0))
            reported = (now - timedelta(seconds=age)).isoformat()
            meta[key] = {"status": "ok", "last_reported": reported, "last_updated": reported}
        if old_static:
            old = (now - timedelta(hours=6)).isoformat()
            for key in (
                "set_voltage", "set_current", "ovp", "ocp",
                "set_voltage_readback_v2", "set_current_readback_v2",
                "ovp_readback_v2", "ocp_readback_v2", "input_voltage",
            ):
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
        guard = ManagedRuntimeSafetyGuard(app)
        guard.edge_lease_enforced = False
        guard.OFF_CONFIRMATION_WINDOW_S = 0.0
        guard.OFF_CONFIRMATION_POLL_S = 0.0
        return guard


    async def _assert_managed_wait_then_fail(self, guard, app, reason):
        """An unhealthy callback is never fresh, but gets one 300s wait."""
        self.assertEqual(guard.TELEMETRY_UNAVAILABLE_GRACE_S, 300.0)
        for tick in (100.0, 399.0):
            with patch("runtime.safety.managed_guard.time.monotonic", return_value=tick):
                observed = await guard.get_all_live()
            self.assertIs(observed.get("_managed_telemetry_recovery_pending"), True)
            self.assertEqual(app.hass.turn_off_calls, 0)
            self.assertEqual(guard._telemetry_unavailable_since, 100.0)
        with patch("runtime.safety.managed_guard.time.monotonic", return_value=400.0):
            with self.assertRaisesRegex(RuntimeSafetyError, reason):
                await guard.get_all_live()
        self.assertEqual(app.hass.turn_off_calls, 1)

    async def test_one_existing_lease_arms_before_output_on_and_off_state_never_renews(self):
        events = []
        live = self._with_freshness(self._live())
        live["switch"] = "off"
        app = self._app(live)
        app.hass = LeaseOrderHass(live, events)
        lease = CountingEdgeLease(events)
        app.edge_safety_lease = lease
        guard = ManagedRuntimeSafetyGuard(app)
        app.runtime_safety_guard = guard

        self.assertIs(guard.edge_safety_lease, lease)
        self.assertIs(app.edge_safety_lease, lease)
        self.assertTrue(guard.edge_lease_enforced)

        self.assertTrue(await guard.turn_on())

        self.assertEqual(lease.arm_calls, 1)
        self.assertEqual(events[:2], ["lease_arm", "output_on"])
        self.assertEqual(lease.renew_calls, 0)

        await guard.get_all_live()
        self.assertEqual(lease.renew_calls, 1)

        self.assertTrue(await guard.turn_off())
        self.assertTrue(lease.renewals_suspended)
        renewals_before_off_poll = lease.renew_calls
        await guard.get_all_live()
        self.assertEqual(lease.renew_calls, renewals_before_off_poll)
        self.assertEqual(lease.arm_calls, 1)

    async def test_one_existing_lease_arms_before_output_on_and_off_state_never_renews(self):
        events = []
        live = self._with_freshness(self._live())
        live["switch"] = "off"
        app = self._app(live)
        app.hass = LeaseOrderHass(live, events)
        lease = CountingEdgeLease(events)
        app.edge_safety_lease = lease
        guard = ManagedRuntimeSafetyGuard(app)
        app.runtime_safety_guard = guard

        self.assertIs(guard.edge_safety_lease, lease)
        self.assertIs(app.edge_safety_lease, lease)
        self.assertTrue(guard.edge_lease_enforced)

        self.assertTrue(await guard.turn_on())

        self.assertEqual(lease.arm_calls, 1)
        self.assertEqual(events[:2], ["lease_arm", "output_on"])
        self.assertEqual(lease.renew_calls, 0)

        await guard.get_all_live()
        self.assertEqual(lease.renew_calls, 1)

        self.assertTrue(await guard.turn_off())
        self.assertTrue(lease.renewals_suspended)
        renewals_before_off_poll = lease.renew_calls
        await guard.get_all_live()
        self.assertEqual(lease.renew_calls, renewals_before_off_poll)
        self.assertEqual(lease.arm_calls, 1)

    async def test_cancelled_start_arm_never_submits_physical_output_on(self):
        events = []

        class CancelAfterEdgeAppliedLease(CountingEdgeLease):
            async def arm(self):
                self.arm_calls += 1
                self.events.append("lease_arm_command")
                # Model ESP applying the arm command while its positive ACK is
                # still pending. Cancellation must leave the local lease suspended.
                self.renewals_suspended = False
                self.arm_started.set()
                try:
                    await asyncio.Event().wait()
                except asyncio.CancelledError:
                    self.renewals_suspended = True
                    self.events.append("lease_arm_cancelled_suspended")
                    raise

        live = self._with_freshness(self._live())
        live["switch"] = "off"
        app = self._app(live)
        app.charge_controller.is_active = True
        app.hass = LeaseOrderHass(live, events)
        lease = CancelAfterEdgeAppliedLease(events)
        lease.arm_started = asyncio.Event()
        app.edge_safety_lease = lease
        guard = ManagedRuntimeSafetyGuard(app)
        app.runtime_safety_guard = guard

        start_task = asyncio.create_task(guard.turn_on())
        await asyncio.wait_for(lease.arm_started.wait(), timeout=1.0)
        start_task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await asyncio.wait_for(start_task, timeout=1.0)

        self.assertEqual(lease.arm_calls, 1)
        self.assertTrue(lease.renewals_suspended)
        self.assertEqual(app.hass.turn_off_calls, 0)
        self.assertEqual(app.hass.live["switch"], "off")
        self.assertNotIn("output_on", events)
        self.assertLess(events.index("lease_arm_command"), events.index("lease_arm_cancelled_suspended"))

    async def test_telemetry_recovery_epoch_clears_after_safe_idle_retirement(self):
        """An old callback incident must not leak into a later charge session."""
        live = self._with_freshness(self._live(), ages={"battery_voltage": 23.7})
        app = self._app(live)
        guard = self._guard(app)
        with patch("runtime.safety.managed_guard.time.monotonic", return_value=100.0):
            pending = await guard.get_all_live()
        self.assertIs(pending.get("_managed_telemetry_recovery_pending"), True)
        self.assertEqual(guard._telemetry_unavailable_since, 100.0)
        app.charge_controller.is_active = False
        app.hass.live["switch"] = "unknown"
        with patch("runtime.safety.managed_guard.time.monotonic", return_value=101.0):
            await guard.get_all_live()
        self.assertEqual(guard._telemetry_unavailable_since, 100.0)
        app.hass.live["switch"] = "off"
        app.hass.live["_meta"]["switch"]["status"] = "stale"
        with patch("runtime.safety.managed_guard.time.monotonic", return_value=102.0):
            await guard.get_all_live()
        self.assertEqual(guard._telemetry_unavailable_since, 100.0)
        app.hass.live["_meta"]["switch"]["status"] = "ok"
        with patch("runtime.safety.managed_guard.time.monotonic", return_value=103.0):
            await guard.get_all_live()
        self.assertIsNone(guard._telemetry_unavailable_since)

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

    async def test_mix_adoption_is_a_managed_high_voltage_safety_owner(self):
        live = self._with_freshness(self._live())
        app = self._app(live)
        app.rd_managed_mix_adoption = SimpleNamespace(managed_authority=True)
        guard = self._guard(app)

        self.assertTrue(guard.managed_mix_active)
        self.assertTrue(guard.controller_active)
        self.assertTrue(guard._temp_integrity_hv_active())
        guard._renew_edge_lease_or_fail = AsyncMock()
        await guard.get_all_live()
        guard._renew_edge_lease_or_fail.assert_awaited_once_with(output_state=True)

        live_with_trip = self._with_freshness(self._live())
        live_with_trip["protection_code"] = 3
        trip_app = self._app(live_with_trip)
        trip_app.rd_managed_mix_adoption = SimpleNamespace(managed_authority=True)
        trip_guard = self._guard(trip_app)
        with self.assertRaisesRegex(RuntimeSafetyError, "OPP"):
            await trip_guard.get_all_live()
        self.assertEqual(trip_app.hass.live["switch"], "off")
        self.assertEqual(trip_app.hass.turn_off_calls, 1)

    async def test_raw_opp_trip_forces_verified_off(self):
        live = self._live()
        live["protection_code"] = 3
        app = self._app(live)
        guard = self._guard(app)
        with self.assertRaisesRegex(RuntimeSafetyError, "OPP"):
            await guard.get_all_live()
        self.assertEqual(app.hass.live["switch"], "off")
        self.assertEqual(app.hass.turn_off_calls, 1)

    async def test_unknown_raw_protection_does_not_bypass_vset_guard(self):
        live = self._live()
        live["protection_code"] = 9
        app = self._app(live)
        guard = self._guard(app)
        with self.assertRaisesRegex(RuntimeSafetyError, "authoritative set_voltage readback V2 is missing/stale"):
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

    async def test_complete_readback_outage_gets_300_second_grace(self):
        live = self._with_freshness(self._live())
        for key in ("battery_voltage", "voltage", "current", "temp_ext", "temp_int", "switch"):
            live[key] = None
        app = self._app(live)
        guard = self._guard(app)
        with patch("runtime.safety.managed_guard.time.monotonic", side_effect=[100.0, 399.0, 401.0] + [401.0] * 20):
            await guard.get_all_live()
            self.assertEqual(app.hass.turn_off_calls, 0)
            await guard.get_all_live()
            self.assertEqual(app.hass.turn_off_calls, 0)
            with self.assertRaisesRegex(RuntimeSafetyError, "battery_voltage"):
                await guard.get_all_live()
        self.assertEqual(app.hass.turn_off_calls, 1)

    async def test_native_disconnect_partial_readback_does_not_stop_before_300s(self):
        live = self._with_freshness(self._live())
        live["set_voltage_readback_v2"] = None
        live["_native_link_outage_since"] = 100.0
        app = self._app(live)
        guard = self._guard(app)
        with patch("runtime.safety.managed_guard.time.monotonic",
                   side_effect=[101.0, 250.0, 399.0, 400.0] + [400.0] * 30):
            for _ in range(3):
                await guard.get_all_live()
                self.assertEqual(app.hass.turn_off_calls, 0)
                self.assertEqual(guard._telemetry_unavailable_since, 100.0)
            with self.assertRaisesRegex(RuntimeSafetyError, "authoritative set_voltage"):
                await guard.get_all_live()
        self.assertEqual(app.hass.turn_off_calls, 1)

    async def test_native_partial_recovery_keeps_same_outage_epoch(self):
        live = self._with_freshness(self._live())
        live["set_voltage_readback_v2"] = None
        live["_native_link_outage_since"] = 100.0
        app = self._app(live)
        guard = self._guard(app)
        with patch("runtime.safety.managed_guard.time.monotonic",
                   side_effect=[110.0, 220.0, 395.0]):
            await guard.get_all_live()
            app.hass.live["current"] = 0.25
            await guard.get_all_live()
            self.assertEqual(guard._telemetry_unavailable_since, 100.0)
            self.assertEqual(app.hass.turn_off_calls, 0)
            app.hass.live["set_voltage_readback_v2"] = 14.8
            app.hass.live.pop("_native_link_outage_since")
            await guard.get_all_live()
        self.assertIsNone(guard._telemetry_unavailable_since)
        self.assertEqual(app.hass.turn_off_calls, 0)

    async def test_mix_pair_stale_battery_and_missing_voltage_readback_keeps_one_native_grace(self):
        # Regression for the two independent V2 warnings seen after MAIN -> MIX.
        # One proven Native outage must retain its original epoch while partial
        # callbacks recover, without inventing either missing readback.
        live = self._with_freshness(self._live(), ages={"battery_voltage": 23.7})
        live["set_voltage_readback_v2"] = None
        live["_native_link_outage_since"] = 100.0
        app = self._app(live)
        guard = self._guard(app)
        with patch("runtime.safety.managed_guard.time.monotonic", side_effect=[110.0, 220.0, 250.0]):
            await guard.get_all_live()
            self.assertEqual(guard._telemetry_unavailable_since, 100.0)
            self.assertEqual(app.hass.turn_off_calls, 0)
            app.hass.live["set_voltage_readback_v2"] = 14.8
            await guard.get_all_live()
            self.assertEqual(guard._telemetry_unavailable_since, 100.0)
            self.assertEqual(app.hass.turn_off_calls, 0)
            app.hass.live = self._with_freshness(self._live())
            await guard.get_all_live()
        self.assertIsNone(guard._telemetry_unavailable_since)
        self.assertEqual(app.hass.turn_off_calls, 0)

    async def test_mix_pair_without_native_outage_marker_remains_fail_closed(self):
        live = self._with_freshness(self._live(), ages={"battery_voltage": 23.7})
        live["set_voltage_readback_v2"] = None
        app = self._app(live)
        guard = self._guard(app)
        await self._assert_managed_wait_then_fail(guard, app, "authoritative set_voltage readback V2")
        self.assertEqual(app.hass.turn_off_calls, 1)

    async def test_isolated_stale_readback_without_native_outage_still_fails(self):
        live = self._with_freshness(self._live())
        live["set_voltage_readback_v2"] = None
        app = self._app(live)
        guard = self._guard(app)
        await self._assert_managed_wait_then_fail(guard, app, "authoritative set_voltage")
        self.assertEqual(app.hass.turn_off_calls, 1)

    async def test_normal_poll_and_mix_transition_share_300s_wait_and_recover(self):
        # Screenshot pattern: 23.7s-old battery callback and missing Vset,
        # while Native TCP, physical Output and protection remain healthy.
        live = self._with_freshness(self._live(), ages={"battery_voltage": 23.7})
        live["set_voltage_readback_v2"] = None
        app = self._app(live)
        guard = self._guard(app)
        with patch("runtime.safety.managed_guard.time.monotonic", return_value=100.0):
            waiting = await guard.get_all_live()
        self.assertIs(waiting.get("_managed_telemetry_recovery_pending"), True)
        self.assertEqual(guard._telemetry_unavailable_since, 100.0)
        self.assertEqual(app.hass.turn_off_calls, 0)

        # Stage-change Vset report returns first, but the old battery sample
        # cannot reset the single recovery clock.
        app.hass.live["set_voltage_readback_v2"] = 14.8
        with patch("runtime.safety.managed_guard.time.monotonic", return_value=399.0):
            await guard.get_all_live()
        self.assertEqual(guard._telemetry_unavailable_since, 100.0)
        self.assertEqual(app.hass.turn_off_calls, 0)

        app.hass.live = self._with_freshness(self._live())
        with patch("runtime.safety.managed_guard.time.monotonic", return_value=399.5):
            recovered = await guard.get_all_live()
        self.assertNotIn("_managed_telemetry_recovery_pending", recovered)
        self.assertIsNone(guard._telemetry_unavailable_since)
        self.assertEqual(app.hass.turn_off_calls, 0)

    async def test_300s_wait_does_not_authorize_stale_programmed_readback(self):
        from rd6018_telemetry import canonical_programmed_readback

        live = self._with_freshness(self._live(), ages={
            "set_voltage_readback_v2": 23.7,
        })
        app = self._app(live)
        guard = self._guard(app)
        self.assertIsNone(canonical_programmed_readback(live, "set_voltage"))
        with patch("runtime.safety.managed_guard.time.monotonic", return_value=100.0):
            await guard.get_all_live()
        self.assertEqual(app.hass.turn_off_calls, 0)
        self.assertIsNone(canonical_programmed_readback(live, "set_voltage"))

    async def test_legacy_ovp_ocp_binary_sensors_are_diagnostic_only(self):
        for key in ("ovp_triggered", "ocp_triggered"):
            with self.subTest(key=key):
                live = self._live()
                live["protection_code"] = "unavailable"
                live[key] = "on"
                app = self._app(self._with_freshness(live))
                guard = self._guard(app)
                await guard.get_all_live()
                self.assertEqual(app.hass.turn_off_calls, 0)

    async def test_raw_codes_one_and_two_do_not_trigger_managed_off(self):
        for code in (1, 2):
            with self.subTest(code=code):
                live = self._live()
                live["protection_code"] = code
                app = self._app(self._with_freshness(live))
                guard = self._guard(app)
                await guard.get_all_live()
                self.assertEqual(app.hass.turn_off_calls, 0)

    async def test_known_overvoltage_preempts_missing_vset_wait(self):
        live = self._with_freshness(self._live())
        live["voltage"] = 30.0
        live["set_voltage_readback_v2"] = None
        app = self._app(live)
        guard = self._guard(app)
        with self.assertRaises(RuntimeSafetyError):
            await guard.get_all_live()
        self.assertEqual(app.hass.turn_off_calls, 1)

    async def test_valid_sample_resets_readback_outage_grace(self):
        broken = self._with_freshness(self._live())
        for key in ("battery_voltage", "voltage", "current", "temp_ext", "temp_int", "switch"):
            broken[key] = None
        app = self._app(broken)
        guard = self._guard(app)
        with patch("runtime.safety.managed_guard.time.monotonic", side_effect=[100.0, 200.0, 300.0]):
            await guard.get_all_live()
            app.hass.live = self._with_freshness(self._live())
            await guard.get_all_live()
            app.hass.live = dict(broken)
            await guard.get_all_live()
        self.assertEqual(app.hass.turn_off_calls, 0)

    async def test_disabled_ovp_ocp_do_not_trip_normal_live_envelope(self):
        live = self._with_freshness(self._live())
        live.update(voltage=14.72, current=0.21, ovp=0.0, ocp=0.0,
                    ovp_readback_v2=0.0, ocp_readback_v2=0.0)
        app = self._app(live)
        guard = self._guard(app)
        self.assertIsNone(guard._runtime_envelope_error(live))
        await guard.get_all_live()
        self.assertEqual(app.hass.turn_off_calls, 0)

    async def test_legacy_protection_setpoints_do_not_replace_vi_envelope(self):
        live = self._with_freshness(self._live())
        app = self._app(live)
        guard = self._guard(app)
        live.update(ovp=13.0, ovp_readback_v2=13.0,
                    ocp=0.10, ocp_readback_v2=0.10)
        self.assertIsNone(guard._runtime_envelope_error(live))
        live["voltage"] = 17.0
        self.assertIn("measured output voltage", guard._runtime_envelope_error(live))
        live["voltage"] = 14.72
        live["current"] = 12.1
        self.assertIn("working-current", guard._runtime_envelope_error(live))

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
        await self._assert_managed_wait_then_fail(guard, app, "temp_ext stale")
        self.assertEqual(app.hass.live["switch"], "off")
        self.assertEqual(app.hass.turn_off_calls, 1)

    async def test_stale_measured_output_voltage_fails_closed(self):
        live = self._with_freshness(self._live(), ages={"voltage": 30.0})
        app = self._app(live)
        guard = self._guard(app)
        await self._assert_managed_wait_then_fail(guard, app, "voltage stale")
        self.assertEqual(app.hass.live["switch"], "off")

    async def test_stale_output_switch_state_fails_closed(self):
        live = self._with_freshness(self._live(), ages={"switch": 30.0})
        app = self._app(live)
        guard = self._guard(app)
        with self.assertRaisesRegex(RuntimeSafetyError, "switch stale"):
            await guard.get_all_live()
        self.assertEqual(app.hass.live["switch"], "off")

    async def test_stale_retired_protection_state_is_not_a_gate(self):
        live = self._with_freshness(self._live(), ages={"ovp_triggered": 30.0, "ocp_triggered": 30.0})
        app = self._app(live)
        guard = self._guard(app)
        await guard.get_all_live()
        self.assertEqual(app.hass.live["switch"], "on")
        self.assertEqual(app.hass.turn_off_calls, 0)

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
        await self._assert_managed_wait_then_fail(guard, app, "is_cv stale")
        self.assertEqual(app.hass.live["switch"], "off")

    async def test_stale_raw_regulation_code_fails_closed(self):
        live = self._live()
        live["regulation_code"] = 0
        live = self._with_freshness(live, ages={"regulation_code": 30.0})
        app = self._app(live)
        guard = self._guard(app)
        await self._assert_managed_wait_then_fail(guard, app, "regulation_code stale")
        self.assertEqual(app.hass.live["switch"], "off")

    async def test_stale_canonical_programmed_readback_fails_closed_while_output_is_on(self):
        live = self._with_freshness(self._live(), old_static=True)
        app = self._app(live)
        guard = self._guard(app)
        await self._assert_managed_wait_then_fail(guard, app, "authoritative set_voltage readback V2")
        self.assertEqual(app.hass.turn_off_calls, 1)

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
        await self._assert_managed_wait_then_fail(guard, app, "authoritative current readback V2")
        self.assertEqual(app.hass.live["switch"], "off")

    async def test_missing_v2_current_readback_fails_closed(self):
        live = self._with_freshness(self._live())
        live.pop("set_current_readback_v2")
        live["_meta"].pop("set_current_readback_v2")
        app = self._app(live)
        guard = self._guard(app)
        await self._assert_managed_wait_then_fail(guard, app, "authoritative current readback V2")
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
        guard._off_unconfirmed_notice_active = True
        guard.OFF_UNCONFIRMED_RETRY_S = 3600.0

        with self.assertRaisesRegex(OutputOffNotConfirmed, "ON"):
            await guard.get_all_live()

        self.assertTrue(guard._off_unconfirmed)
        self.assertEqual(app.hass.live["switch"], "on")
        self.assertEqual(app.hass.turn_off_calls, 1)
        self.assertIsNone(guard._orphan_output_seen_at)

        # A second background poll inside the retry interval is containment-only.
        app.hass.off_confirms = True
        with self.assertRaisesRegex(OutputOffNotConfirmed, "ON"):
            await guard.get_all_live()
        self.assertEqual(app.hass.turn_off_calls, 1)

        # Once the bounded retry becomes due, the same recovery path may prove OFF.
        # ``time.monotonic()`` is process/system uptime on Windows; zero is not
        # necessarily outside the retry interval after a recent reboot.
        guard._off_unconfirmed_last_retry_at = (
            time.monotonic() - guard.OFF_UNCONFIRMED_RETRY_S
        )
        observed = await guard.get_all_live()
        self.assertEqual(observed["switch"], "off")
        self.assertFalse(guard._off_unconfirmed)
        self.assertEqual(app.hass.turn_off_calls, 2)
        self.assertIsNone(guard._orphan_output_seen_at)

    async def test_off_unconfirmed_with_unknown_switch_is_passive_containment(self):
        controller = DummyController()
        controller.is_active = False
        live = self._with_freshness(self._live())
        live["switch"] = "unknown"
        app = self._app(live, controller=controller)
        app.hass.off_confirms = False
        guard = self._guard(app)
        guard._off_unconfirmed = True
        guard._off_unconfirmed_notice_active = True

        with self.assertRaisesRegex(OutputOffNotConfirmed, "unknown/stale"):
            await guard.get_all_live()

        self.assertEqual(app.hass.turn_off_calls, 0)
        self.assertTrue(guard._off_unconfirmed)

    def test_transport_metadata_preserves_home_assistant_last_reported(self):
        from hass_api import HassClient
        now = datetime.now(timezone.utc).isoformat()
        old = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        metadata = HassClient._entity_metadata(
            "sensor.example",
            {"last_updated": old, "last_reported": now},
            "ok",
        )
        self.assertEqual(metadata["last_updated"], old)
        self.assertEqual(metadata["last_reported"], now)


class SafetyAdapterInstallationDefaultsTests(unittest.TestCase):
    def _app(self):
        live = V2RuntimeSafetyTests._with_freshness(V2RuntimeSafetyTests._live())
        return V2RuntimeSafetyTests._app(live)

    def test_runtime_guard_install_does_not_patch_transport_by_default(self):
        app = self._app()
        original_instance_fields = set(vars(app.hass))

        guard = RuntimeSafetyGuard(app)
        guard.install()

        self.assertIs(guard.adapter, app.hass)
        self.assertEqual(set(vars(app.hass)), original_instance_fields)
        self.assertNotIn("_runtime_safety_guard", vars(app.hass))

    def test_managed_guard_installer_does_not_patch_transport_by_default(self):
        app = self._app()
        original_instance_fields = set(vars(app.hass))

        guard = install_managed_runtime_safety(app)

        self.assertIs(app.runtime_safety_guard, guard)
        self.assertIs(guard.adapter, app.hass)
        self.assertEqual(set(vars(app.hass)), original_instance_fields)
        self.assertNotIn("_runtime_safety_guard", vars(app.hass))


if __name__ == "__main__":
    unittest.main()
