"""Fake-only parity baseline for the current trace identity projection/apply helpers."""

import unittest
import uuid
from enum import Enum
from unittest.mock import patch

from runtime.charge.session import apply_trace_identity, restore_trace_identity


class _Intent(str, Enum):
    NORMAL = "normal"
    DIAGNOSTIC = "diagnostic"


class _Condition(str, Enum):
    UNKNOWN = "unknown"
    HEALTHY = "healthy"


class _Configuration:
    restore_trace_default_intent = _Intent.DIAGNOSTIC
    restore_trace_default_condition = _Condition.HEALTHY


class _Host:
    """Small state holder: no controller, runtime, persistence, or device imports."""

    def __init__(self):
        self.total_start_time = 1234.5
        self.battery_type = "Ca/Ca"
        self.ah_capacity = 60
        self.host_configuration = _Configuration()
        self._v2_battery_id = "existing-battery"
        self._v2_intent = _Intent.NORMAL
        self._v2_condition_before = _Condition.UNKNOWN


def _expected_id(profile, capacity, started, saved_at):
    seed = f"{profile}|{capacity}|{started:.6f}|{saved_at or ''}"
    return uuid.uuid5(uuid.NAMESPACE_URL, f"rd6018-recovery:{seed}").hex


class TraceProjectionParityTests(unittest.TestCase):
    def test_trace_timestamp_precedence_trace_started_at_then_total_then_saved(self):
        for document, expected in (
            ({"v2_trace_started_at": 10, "total_start_time": 20, "saved_at": 30}, 10),
            ({"v2_trace_started_at": None, "total_start_time": 20, "saved_at": 30}, 20),
            ({"total_start_time": None, "saved_at": 30}, 30),
        ):
            with self.subTest(document=document):
                self.assertEqual(restore_trace_identity(_Host(), document).started_at, expected)

    def test_nonfinite_and_malformed_times_fall_back_to_host_then_controlled_clock(self):
        for bad in ("not-a-time", float("nan"), float("inf"), float("-inf"), 0, -1):
            with self.subTest(bad=bad):
                host = _Host()
                snapshot = restore_trace_identity(host, {"v2_trace_started_at": bad})
                self.assertEqual(snapshot.started_at, host.total_start_time)
        host = _Host()
        host.total_start_time = 0
        with patch("runtime.charge.session.time.time", return_value=7654.25):
            snapshot = restore_trace_identity(host, {"v2_trace_started_at": "bad"})
        self.assertEqual(snapshot.started_at, 7654.25)

    def test_missing_id_uses_legacy_uuid5_seed_and_six_decimal_timestamp(self):
        snapshot = restore_trace_identity(_Host(), {
            "profile": "Ca/Ca", "ah_limit": 60, "v2_trace_started_at": 1234.5000004,
            "saved_at": 7,
        })
        self.assertEqual(snapshot.session_id, _expected_id("Ca/Ca", 60, 1234.5000004, 7))

    def test_uuid_seed_uses_host_profile_and_capacity_for_falsey_document_values(self):
        snapshot = restore_trace_identity(_Host(), {
            "profile": "", "ah_limit": 0, "v2_trace_started_at": 1234.5, "saved_at": 7,
        })
        self.assertEqual(snapshot.session_id, _expected_id("Ca/Ca", 60, 1234.5, 7))

    def test_explicit_trace_id_is_preserved_after_stripping(self):
        snapshot = restore_trace_identity(_Host(), {
            "v2_trace_session_id": "  legacy-id  ", "v2_trace_started_at": 2,
        })
        self.assertEqual(snapshot.session_id, "legacy-id")

    def test_battery_id_truthy_is_stringified_and_falsey_uses_existing_value(self):
        truthy = restore_trace_identity(_Host(), {"v2_battery_id": 42})
        falsey = restore_trace_identity(_Host(), {"v2_battery_id": ""})
        self.assertEqual(truthy.battery_id, "42")
        self.assertEqual(falsey.battery_id, "existing-battery")

    def test_configuration_defaults_precede_host_fields_and_string_defaults(self):
        configured = restore_trace_identity(_Host(), {})
        self.assertEqual(configured.intent, "diagnostic")
        self.assertEqual(configured.condition_before, "healthy")

        host = _Host()
        host.host_configuration = None
        from_host = restore_trace_identity(host, {})
        self.assertEqual(from_host.intent, "normal")
        self.assertEqual(from_host.condition_before, "unknown")

        host._v2_intent = "host-intent"
        host._v2_condition_before = "host-condition"
        from_strings = restore_trace_identity(host, {})
        self.assertEqual(from_strings.intent, "host-intent")
        self.assertEqual(from_strings.condition_before, "host-condition")

    def test_document_enum_values_convert_and_invalid_values_fall_back_to_default(self):
        valid = restore_trace_identity(_Host(), {
            "v2_intent": "diagnostic", "v2_condition_before": "healthy",
        })
        invalid = restore_trace_identity(_Host(), {
            "v2_intent": "bogus", "v2_condition_before": "bogus",
        })
        self.assertEqual((valid.intent, valid.condition_before), ("diagnostic", "healthy"))
        self.assertEqual((invalid.intent, invalid.condition_before), ("diagnostic", "healthy"))

    def test_apply_reconstitutes_enum_types_when_host_fields_are_enums(self):
        host = _Host()
        snapshot = restore_trace_identity(host, {
            "v2_trace_session_id": "sid", "v2_trace_started_at": 12,
            "v2_intent": "diagnostic", "v2_condition_before": "healthy",
        })
        apply_trace_identity(host, snapshot)
        self.assertIs(host._v2_intent, _Intent.DIAGNOSTIC)
        self.assertIs(host._v2_condition_before, _Condition.HEALTHY)

    def test_apply_uses_strings_when_host_fields_are_absent(self):
        host = _Host()
        host.host_configuration = None
        del host._v2_intent
        del host._v2_condition_before
        snapshot = restore_trace_identity(host, {
            "v2_trace_session_id": "sid", "v2_trace_started_at": 12,
            "v2_intent": "custom", "v2_condition_before": "custom-condition",
        })
        apply_trace_identity(host, snapshot)
        self.assertEqual(host._v2_intent, "custom")
        self.assertEqual(host._v2_condition_before, "custom-condition")
        self.assertIs(type(host._v2_intent), str)
        self.assertIs(type(host._v2_condition_before), str)

    def test_snapshot_creation_does_not_mutate_host(self):
        host = _Host()
        before = dict(host.__dict__)
        restore_trace_identity(host, {"v2_intent": "diagnostic", "v2_battery_id": "new"})
        self.assertEqual(host.__dict__, before)

    def test_json_nested_battery_id_is_stringified_but_exotic_python_object_is_documented(self):
        snapshot = restore_trace_identity(_Host(), {"v2_battery_id": {"json": "object"}})
        self.assertEqual(snapshot.battery_id, "{'json': 'object'}")

        class _ExplodingString:
            def __str__(self):
                raise RuntimeError("injected __str__ failure")

        # This is a decoder-injected Python object edge, not a value representable by JSON.
        with self.assertRaisesRegex(RuntimeError, "injected __str__ failure"):
            restore_trace_identity(_Host(), {"v2_battery_id": _ExplodingString()})


if __name__ == "__main__":
    unittest.main()
