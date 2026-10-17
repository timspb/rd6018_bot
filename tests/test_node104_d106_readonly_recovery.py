"""D106 strict read-only dual-source projection and independent recovery gates."""
import copy
import time
import unittest
from unittest.mock import patch

from tools import node104_d106_readonly_projection as O
from tests.test_node104_d105_trial_lifecycle import TrialLifecycleTests, TX


class ObserverProjectionTests(unittest.TestCase):
    def snapshot(self):
        now = time.time()
        fields = {
            "output_r18": 0, "voltage_v": 0.0, "current_a": 0.0,
            "protection_r16": 0, "autonomous": False, "lease_armed": False,
            "lease_remaining_s": 0.0, "lease_ttl_s": 900.0,
            "modbus_age_s": 1.0, "set_voltage_v": 13.57,
            "set_current_a": 0.10, "ovp_v": 14.07, "ocp_a": 0.20,
        }
        result = {"captured_at_epoch": now,
                  "source_nonces": ["a"*32, "b"*32]}
        for key, source in (("ha102", "ha102_rest"), ("esp128", "esp_native_api")):
            result[key] = {}
            for field, value in fields.items():
                if key == "ha102" and field not in O.HA_FIELDS:
                    continue
                meta = {"source": source, "object_id": field, "status": "ok",
                        "reported_at_epoch": now}
                if key == "esp128":
                    meta["native_type"] = ("BinarySensorState"
                                          if field in O.BOOLEAN_FIELDS else "SensorState")
                result[key][field] = {"value": value, "meta": meta}
        return result

    def test_strict_independent_valid_off(self):
        snap = self.snapshot()
        a = O.project_off(snap)
        b = O.project_off(snap)
        self.assertFalse(a.autonomous)
        self.assertEqual(0, a.lease_remaining_s)
        self.assertEqual(900, a.lease_ttl_s)
        self.assertNotEqual(a.challenge, b.challenge)

    def test_missing_unknown_stale_and_masquerading_evidence_denied(self):
        changes = [
            ("ha102", "autonomous", "value", None),
            ("ha102", "autonomous", "value", "unknown"),
            ("ha102", "autonomous", "value", True),
            ("esp128", "lease_armed", "value", True),
            ("esp128", "lease_remaining_s", "value", 200),
            ("esp128", "lease_ttl_s", "value", 30),
            ("esp128", "protection_r16", "value", 2),
            ("esp128", "modbus_age_s", "value", 45),
            ("esp128", "set_voltage_v", "value", 17.3),
            ("ha102", "output_r18", "value", 1),
            ("ha102", "voltage_v", "value", 0.5),
            ("esp128", "current_a", "value", 0.5),
            ("esp128", "set_current_a", "value", 0.8),
            ("esp128", "autonomous", "value", True),
        ]
        for source, name, component, bad in changes:
            with self.subTest(source=source, name=name, bad=bad):
                snap = self.snapshot()
                snap[source][name][component] = bad
                with self.assertRaises(O.TransactionError):
                    O.project_off(snap)
        for source, field in (("ha102", "autonomous"), ("esp128", "protection_r16")):
            with self.subTest(source=source, field=field):
                snap = self.snapshot()
                del snap[source][field]
                with self.assertRaises(O.TransactionError):
                    O.project_off(snap)
        for source, field, meta_key, bad in (
            ("esp128", "autonomous", "native_type", "ButtonInfo"),
            ("esp128", "protection_r16", "native_type", "ButtonInfo"),
            ("ha102", "autonomous", "source", "esp_native_api"),
            ("esp128", "voltage_v", "reported_at_epoch", time.time()-60),
            ("ha102", "autonomous", "reported_at_epoch", time.time()-60),
        ):
            with self.subTest(source=source, field=field, meta=meta_key):
                snap = self.snapshot()
                snap[source][field]["meta"][meta_key] = bad
                with self.assertRaises(O.TransactionError):
                    O.project_off(snap)

    def test_snapshot_nonces_invalid_and_ha_native_disagreement(self):
        for nonces in (["a"*32, "a"*32], [], ["a", "b"]):
            snap = self.snapshot()
            snap["source_nonces"] = nonces
            with self.assertRaises(O.TransactionError):
                O.project_off(snap)
        snap = self.snapshot()
        snap["captured_at_epoch"] -= 60
        with self.assertRaises(O.TransactionError):
            O.project_off(snap)
        snap = self.snapshot()
        snap["esp128"]["ovp_v"]["value"] = 14.4
        with self.assertRaisesRegex(O.TransactionError, "disagreement"):
            O.project_off(snap)


class SeparateRecoveryAdmissionTests(TrialLifecycleTests):
    """Reuse exact D105 fixture with a separately admitted recovery path."""

    def test_recovery_with_activation_socket_gone(self):
        self.trial()
        self.tx.trial_socket_ready = None
        with patch.object(TX, "TRIAL_PIN", self.fixture_pin):
            restored = self.tx.recover()
        self.assertEqual("TRIAL_RESTORED", restored["phase"])
        self.assert_old()

    def test_finish_without_activation_permission(self):
        self.trial()
        self.tx._trial_gate = lambda: (_ for _ in ()).throw(TX.TransactionError('activation disabled'))
        self.tx.trial_socket_ready = None
        with patch.object(TX, "TRIAL_PIN", self.fixture_pin):
            restored = self.tx.finish_trial()
        self.assertEqual("TRIAL_RESTORED", restored["phase"])
        self.assert_old()

    def test_recovery_fails_closed_without_independent_edge_observer(self):
        self.trial()
        self.tx.trial_edge_proof = None
        stops = self.service.stops
        with patch.object(TX, "TRIAL_PIN", self.fixture_pin):
            with self.assertRaisesRegex(TX.TransactionError, "independent edge proof"):
                self.tx.recover()
        self.assertEqual(stops, self.service.stops)

    def test_recovery_at_every_restore_copy_crash(self):
        for failpoint in (
            "trial-restore-app", "trial-restore-state", "trial-restore-venv",
            "trial-restore-after-three-components-before-config",
            "trial-restore-after-marker-before-verify",
            "trial-restore-before-old-start",
        ):
            with self.subTest(failpoint=failpoint):
                self.tearDown()
                self.setUp()
                self.trial()
                self.tx.failpoint = lambda point: (_ for _ in ()).throw(
                    RuntimeError(point)) if point == failpoint else None
                with patch.object(TX, "TRIAL_PIN", self.fixture_pin):
                    with self.assertRaisesRegex(RuntimeError, failpoint):
                        self.tx.finish_trial()
                self.assertFalse(self.service.running)
                self.tx.failpoint = lambda _: None
                self.tx.trial_socket_ready = None
                with patch.object(TX, "TRIAL_PIN", self.fixture_pin):
                    self.assertEqual("TRIAL_RESTORED", self.tx.recover()["phase"])
                self.assert_old()
