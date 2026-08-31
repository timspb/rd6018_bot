import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from external_temp_integrity import ExternalTempIntegrityMonitor, ExternalTempIntegrityPolicy
from runtime_safety import RuntimeSafetyError
from runtime_safety_v2 import V2RuntimeSafetyGuard


def _live(temp=25.0, *, when=None, switch="on"):
    when = when or datetime.now(timezone.utc)
    stamp = when.isoformat()
    live = {
        "battery_voltage": 14.2,
        "voltage": 14.2,
        "current": 2.0,
        "temp_ext": float(temp),
        "temp_int": 30.0,
        "switch": switch,
        "is_cv": "on",
        "is_cc": "off",
        "ovp_triggered": "off",
        "ocp_triggered": "off",
        "set_voltage": 14.8,
        "set_current": 5.0,
        "ovp": 14.9,
        "ocp": 5.1,
    }
    keys = (
        "battery_voltage", "voltage", "current", "temp_ext", "temp_int", "switch",
        "is_cv", "is_cc", "ovp_triggered", "ocp_triggered",
    )
    live["_meta"] = {
        key: {"status": "ok", "last_reported": stamp, "last_updated": stamp}
        for key in keys
    }
    return live


class ExternalTempIntegrityMonitorTests(unittest.TestCase):
    def test_repeated_poll_of_same_source_report_counts_once(self):
        policy = ExternalTempIntegrityPolicy(consecutive_samples=3, max_step_c=2.0)
        monitor = ExternalTempIntegrityMonitor(policy, fault_file="")
        t0 = datetime.now(timezone.utc)
        monitor.observe(_live(25.0, when=t0))
        first = monitor.observe(_live(30.0, when=t0 + timedelta(seconds=5)))
        self.assertTrue(first.suspicious)
        self.assertEqual(first.anomaly_count, 1)
        cached = monitor.observe(_live(30.0, when=t0 + timedelta(seconds=5)))
        self.assertFalse(cached.new_source_sample)
        self.assertEqual(cached.anomaly_count, 1)

    def test_clean_new_report_resets_consecutive_counter(self):
        policy = ExternalTempIntegrityPolicy(consecutive_samples=3, max_step_c=2.0)
        monitor = ExternalTempIntegrityMonitor(policy, fault_file="")
        t0 = datetime.now(timezone.utc)
        monitor.observe(_live(25.0, when=t0))
        monitor.observe(_live(30.0, when=t0 + timedelta(seconds=5)))
        clean = monitor.observe(_live(30.5, when=t0 + timedelta(seconds=10)))
        self.assertFalse(clean.suspicious)
        self.assertEqual(monitor.anomaly_count, 0)

    def test_n_distinct_suspicious_reports_trip_and_latch(self):
        policy = ExternalTempIntegrityPolicy(consecutive_samples=2, max_step_c=2.0)
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "fault.json")
            monitor = ExternalTempIntegrityMonitor(policy, fault_file=path)
            t0 = datetime.now(timezone.utc)
            monitor.observe(_live(25.0, when=t0))
            self.assertFalse(monitor.observe(_live(30.0, when=t0 + timedelta(seconds=5))).trip)
            decision = monitor.observe(_live(35.0, when=t0 + timedelta(seconds=10)))
            self.assertTrue(decision.trip)
            self.assertTrue(monitor.latched)
            self.assertTrue(os.path.exists(path))
            restored = ExternalTempIntegrityMonitor(policy, fault_file=path)
            self.assertTrue(restored.latched)

    def test_hv_policy_cannot_be_looser_than_baseline(self):
        with self.assertRaises(ValueError):
            ExternalTempIntegrityPolicy(
                consecutive_samples=2,
                hv_consecutive_samples=3,
                max_step_c=2.0,
            )

    def test_no_numeric_defaults_means_detector_is_calibration_gated(self):
        self.assertFalse(ExternalTempIntegrityPolicy().enabled)
        monitor = ExternalTempIntegrityMonitor(ExternalTempIntegrityPolicy(), fault_file="")
        decision = monitor.observe(_live(999.0))
        self.assertFalse(decision.trip)

    def test_rearm_requires_two_distinct_clean_reports(self):
        policy = ExternalTempIntegrityPolicy(consecutive_samples=2, max_step_c=2.0)
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "fault.json")
            monitor = ExternalTempIntegrityMonitor(policy, fault_file=path)
            t0 = datetime.now(timezone.utc)
            monitor.observe(_live(25.0, when=t0))
            monitor.observe(_live(30.0, when=t0 + timedelta(seconds=5)))
            monitor.observe(_live(35.0, when=t0 + timedelta(seconds=10)))
            allowed, _ = monitor.can_rearm(_live(25.0, when=t0 + timedelta(seconds=15)))
            self.assertFalse(allowed)
            allowed, _ = monitor.can_rearm(_live(25.5, when=t0 + timedelta(seconds=20)))
            self.assertTrue(allowed)
            monitor.clear_latch()
            self.assertFalse(monitor.latched)
            self.assertFalse(os.path.exists(path))


class DummyHass:
    def __init__(self, live):
        self.live = dict(live)
        self.base_url = ""
        self.turn_off_calls = 0

    @staticmethod
    def _entity_metadata(entity_id, data, status):
        return {"entity_id": entity_id, "status": status, "last_updated": data.get("last_updated")}

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
    STAGE_DESULFATION = "Desulfation"
    STAGE_MIX = "Mix"

    def __init__(self):
        self.is_active = True
        self.current_stage = "Main"
        self._session_start_reason = "User Command"
        self.stop_calls = []

    def _recipe_envelope(self):
        return None

    def _get_target_v_i(self, temp_ext=None):
        return 14.8, 5.0

    def stop(self, clear_session=True):
        self.stop_calls.append(bool(clear_session))
        self.is_active = False


class ExternalTempRuntimeIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_trip_forces_verified_off_and_retires_auto_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            t0 = datetime.now(timezone.utc)
            controller = DummyController()
            hass = DummyHass(_live(25.0, when=t0))
            app = SimpleNamespace(
                hass=hass,
                charge_controller=controller,
                manual_session_manager=None,
                external_temp_integrity_policy=ExternalTempIntegrityPolicy(
                    consecutive_samples=2,
                    max_step_c=5.0,
                ),
                external_temp_integrity_fault_file=os.path.join(tmp, "fault.json"),
                _charge_notify=lambda *args, **kwargs: None,
            )
            guard = V2RuntimeSafetyGuard(app)
            guard.edge_lease_enforced = False
            guard.VERIFY_ATTEMPTS = 1
            guard.VERIFY_DELAY_S = 0.0

            await guard.get_all_live()
            hass.live = _live(31.0, when=t0 + timedelta(seconds=5))
            await guard.get_all_live()
            hass.live = _live(37.0, when=t0 + timedelta(seconds=10))
            with self.assertRaisesRegex(RuntimeSafetyError, "external temperature sensor integrity"):
                await guard.get_all_live()

            self.assertEqual(hass.live["switch"], "off")
            self.assertEqual(hass.turn_off_calls, 1)
            self.assertEqual(controller.stop_calls, [True])
            self.assertFalse(controller.is_active)
            self.assertTrue(guard.external_temp_integrity.latched)

    async def test_persisted_latch_forbids_auto_restore(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "fault.json")
            policy = ExternalTempIntegrityPolicy(consecutive_samples=2, max_step_c=5.0)
            monitor = ExternalTempIntegrityMonitor(policy, fault_file=path)
            t0 = datetime.now(timezone.utc)
            monitor.observe(_live(25.0, when=t0))
            monitor.observe(_live(31.0, when=t0 + timedelta(seconds=5)))
            monitor.observe(_live(37.0, when=t0 + timedelta(seconds=10)))

            controller = DummyController()
            controller._session_start_reason = "Auto-restore"
            hass = DummyHass(_live(25.0, when=t0 + timedelta(seconds=15), switch="off"))
            app = SimpleNamespace(
                hass=hass,
                charge_controller=controller,
                manual_session_manager=None,
                external_temp_integrity_policy=policy,
                external_temp_integrity_fault_file=path,
                _charge_notify=lambda *args, **kwargs: None,
            )
            guard = V2RuntimeSafetyGuard(app)
            guard.edge_lease_enforced = False
            with self.assertRaisesRegex(RuntimeSafetyError, "auto-restore is forbidden"):
                await guard.turn_on()
            self.assertEqual(controller.stop_calls, [True])
            self.assertFalse(controller.is_active)


if __name__ == "__main__":
    unittest.main()
