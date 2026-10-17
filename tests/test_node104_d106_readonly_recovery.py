"""D107 native-authoritative OFF projection and separate D090 recovery gates."""
import copy
import time
import unittest
from unittest.mock import patch

from tools import node104_d106_readonly_projection as O
from tools import node104_d106_live_observer as LIVE
from tests.test_node104_d105_trial_lifecycle import TrialLifecycleTests, TX


class ObserverProjectionTests(unittest.TestCase):
    """One physical ESP, two network paths: direct Native API has authority."""

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

    def test_fresh_native_off_sufficient_with_healthy_ha(self):
        snap = self.snapshot()
        a = O.project_off(snap)
        b = O.project_off(snap)
        self.assertFalse(a.autonomous)
        self.assertEqual(0, a.lease_remaining_s)
        self.assertEqual(900, a.lease_ttl_s)
        self.assertNotEqual(a.challenge, b.challenge)
        self.assertEqual("fresh", O.inspect_ha_advisory(snap["ha102"])["status"])

    def test_stale_unknown_unavailable_and_contradictory_ha_never_veto_native(self):
        for ha_mutation in (
            lambda snap: snap.__setitem__("ha102", None),
            lambda snap: snap.__setitem__("ha102", {"invalid": "not-a-state"}),
            lambda snap: snap["ha102"]["autonomous"].__setitem__("value", "unknown"),
            lambda snap: snap["ha102"]["autonomous"].__setitem__("value", True),
            lambda snap: snap["ha102"]["autonomous"]["meta"].__setitem__(
                "reported_at_epoch", time.time()-20000),
            lambda snap: snap["ha102"]["output_r18"].__setitem__("value", 1),
            lambda snap: snap["ha102"]["voltage_v"].__setitem__("value", 0.5),
            lambda snap: snap["ha102"]["ovp_v"].__setitem__("value", 14.4),
            lambda snap: snap["ha102"].pop("autonomous"),
        ):
            snap = self.snapshot()
            ha_mutation(snap)
            with self.subTest(ha=snap["ha102"]):
                self.assertFalse(O.project_off(snap).autonomous)
                self.assertIsInstance(O.inspect_ha_advisory(snap["ha102"]), dict)

    def test_native_missing_unsafe_stale_or_wrong_type_is_never_replaced_by_ha(self):
        changes = (
            ("lease_armed", "value", True),
            ("lease_remaining_s", "value", 200),
            ("lease_ttl_s", "value", 30),
            ("protection_r16", "value", 2),
            ("modbus_age_s", "value", 45),
            ("set_voltage_v", "value", 17.3),
            ("output_r18", "value", 1),
            ("voltage_v", "value", 0.5),
            ("current_a", "value", 0.5),
            ("set_current_a", "value", 0.8),
            ("autonomous", "value", True),
            ("autonomous", "native_type", "ButtonInfo"),
            ("protection_r16", "native_type", "ButtonInfo"),
            ("voltage_v", "reported_at_epoch", time.time()-60),
            ("autonomous", "source", "ha102_rest"),
        )
        for field, key, bad in changes:
            with self.subTest(field=field, key=key):
                snap = self.snapshot()
                if key == "value":
                    snap["esp128"][field]["value"] = bad
                else:
                    snap["esp128"][field]["meta"][key] = bad
                with self.assertRaises(O.TransactionError):
                    O.project_off(snap)
        for field in ("autonomous", "lease_ttl_s", "protection_r16"):
            snap = self.snapshot()
            del snap["esp128"][field]
            with self.assertRaises(O.TransactionError):
                O.project_off(snap)
        snap = self.snapshot()
        snap["esp128"] = None
        with self.assertRaises(O.TransactionError):
            O.project_off(snap)

    def test_capture_identifiers_and_snapshot_timestamp_still_required(self):
        for nonces in (["a"*32, "a"*32], [], ["a", "b"]):
            snap = self.snapshot()
            snap["source_nonces"] = nonces
            with self.assertRaises(O.TransactionError):
                O.project_off(snap)
        snap = self.snapshot()
        snap["captured_at_epoch"] -= 60
        with self.assertRaises(O.TransactionError):
            O.project_off(snap)

    def test_ha_never_justifies_unsafe_direct_esp(self):
        snap = self.snapshot()
        snap["ha102"]["autonomous"]["value"] = False
        snap["esp128"]["autonomous"]["value"] = True
        with self.assertRaises(O.TransactionError):
            O.project_off(snap)


class NativeLegacyTtlMappingTests(unittest.TestCase):
    def test_exact_installed_ttl_id_can_be_resolved_from_pinned_d091(self):
        self.assertEqual("safety_lease_ttl",
                         LIVE._edge_object_id("edge_lease_ttl", {}))
        self.assertEqual("safety_lease_ttl",
                         LIVE._edge_object_id(
                             "edge_lease_ttl",
                             {"edge_lease_ttl": "safety_lease_ttl"}))
        for mappings in (
            {"edge_lease_ttl": "wrong_ttl"},
            {"edge_lease_ttl": "safety_lease_armed"},
        ):
            with self.assertRaises(LIVE.ro.ProofError):
                LIVE._edge_object_id("edge_lease_ttl", mappings)
        with self.assertRaises(LIVE.ro.ProofError):
            LIVE._edge_object_id("edge_modbus_age", {})
        with self.assertRaises(LIVE.ro.ProofError):
            LIVE._edge_object_id("edge_lease_armed", {})


class NativeMeasuredCallbackTests(unittest.TestCase):
    """Regression: an aliasing NumberState must not replace SensorState."""

    def test_measured_callback_is_pinned_by_type_key_and_device(self):
        now = time.time()
        measurement = {"voltage": (
            0.0, {"source": "esp_native_api", "object_id": "output_voltage",
                  "status": "ok", "native_type": "SensorState",
                  "entity_type": "SensorInfo", "age_s": 0.5,
                  "key": 5, "device_id": 0})}
        # SensorState=0 V and NumberState=13.57 V can share the
        # deployed transport's object_id; never use the last-type cache.
        record = LIVE._fresh_measured_record(
            "voltage_v", "voltage", "output_voltage", measurement, now)
        self.assertEqual(0.0, record["value"])
        self.assertEqual("SensorState", record["meta"]["native_type"])
        self.assertEqual(5, record["meta"]["native_key"])
        self.assertEqual(0, record["meta"]["device_id"])
        self.assertEqual("output_voltage", record["meta"]["actual_object_id"])
        bad = copy.deepcopy(measurement)
        bad["voltage"][1]["native_type"] = "NumberState"
        with self.assertRaises(LIVE.ro.ProofError):
            LIVE._fresh_measured_record(
                "voltage_v", "voltage", "output_voltage", bad, now)
        bad = copy.deepcopy(measurement)
        bad["voltage"][1]["age_s"] = 20
        with self.assertRaises(LIVE.ro.ProofError):
            LIVE._fresh_measured_record(
                "voltage_v", "voltage", "output_voltage", bad, now)
        with self.assertRaises(LIVE.ro.ProofError):
            LIVE._fresh_measured_record(
                "voltage_v", "voltage", "other_sensor", measurement, now)


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
