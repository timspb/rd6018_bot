"""Pure trace projection parity tests using only JSON-safe documents."""

import ast
from pathlib import Path
import unittest
import uuid
from enum import Enum
from unittest.mock import patch

from runtime.charge.session import project_trace_identity, restore_trace_identity


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
    def __init__(self):
        self.total_start_time = 1234.5
        self.battery_type = "Ca/Ca"
        self.ah_capacity = 60
        self.host_configuration = _Configuration()
        self._v2_battery_id = "existing-battery"
        self._v2_intent = _Intent.NORMAL
        self._v2_condition_before = _Condition.UNKNOWN


def _project_from_host(host, document, *, now_s=None):
    configuration = host.host_configuration
    return project_trace_identity(
        document,
        total_start_time=host.total_start_time,
        battery_type=host.battery_type,
        ah_capacity=host.ah_capacity,
        battery_id=host._v2_battery_id,
        intent_default=configuration.restore_trace_default_intent,
        condition_default=configuration.restore_trace_default_condition,
        now_s=now_s,
    )


class PureTraceProjectionTests(unittest.TestCase):
    def assert_parity(self, document, *, now_s=None):
        host = _Host()
        before = dict(host.__dict__)
        if now_s is None:
            pure = _project_from_host(host, document)
            legacy = restore_trace_identity(host, document)
        else:
            pure = _project_from_host(host, document, now_s=now_s)
            with patch("runtime.charge.session.time.time", side_effect=AssertionError("clock read")):
                legacy = restore_trace_identity(host, document)
        self.assertEqual(pure, legacy)
        self.assertEqual(host.__dict__, before)
        return pure

    def test_preexisting_trace_id_and_timestamp_are_preserved(self):
        snapshot = self.assert_parity({
            "v2_trace_session_id": "  saved-id  ",
            "v2_trace_started_at": "42.5",
            "v2_battery_id": "pack-7",
            "v2_intent": "normal",
            "v2_condition_before": "unknown",
        })
        self.assertEqual((snapshot.session_id, snapshot.started_at), ("saved-id", 42.5))
        self.assertEqual(snapshot.battery_id, "pack-7")

    def test_legacy_timestamp_fallback_order_and_invalid_host_time(self):
        for document, expected in (
            ({"total_start_time": 20, "saved_at": 30}, 20),
            ({"total_start_time": None, "saved_at": 30}, 30),
            ({"v2_trace_started_at": "invalid", "saved_at": 30}, 1234.5),
        ):
            with self.subTest(document=document):
                self.assertEqual(self.assert_parity(document).started_at, expected)

    def test_falsey_profile_and_capacity_retain_uuid5_seed_fallbacks(self):
        document = {
            "profile": "", "ah_limit": 0, "v2_trace_started_at": 1234.5000004,
            "saved_at": 7,
        }
        snapshot = self.assert_parity(document)
        seed = f"Ca/Ca|60|{1234.5000004:.6f}|7"
        self.assertEqual(
            snapshot.session_id,
            uuid.uuid5(uuid.NAMESPACE_URL, f"rd6018-recovery:{seed}").hex,
        )

    def test_nested_json_battery_id_keeps_legacy_string_conversion(self):
        snapshot = self.assert_parity({"v2_battery_id": {"nested": [1, True, None]}})
        self.assertEqual(snapshot.battery_id, "{'nested': [1, True, None]}")

    def test_enum_and_string_defaults_and_invalid_document_values(self):
        enum_defaults = self.assert_parity({
            "v2_intent": "invalid", "v2_condition_before": "invalid",
        })
        self.assertEqual((enum_defaults.intent, enum_defaults.condition_before),
                         ("diagnostic", "healthy"))

        host = _Host()
        host.host_configuration = None
        host._v2_intent = "custom-intent"
        host._v2_condition_before = "custom-condition"
        before = dict(host.__dict__)
        pure = project_trace_identity(
            {"v2_intent": "invalid", "v2_condition_before": "invalid"},
            total_start_time=host.total_start_time,
            battery_type=host.battery_type,
            ah_capacity=host.ah_capacity,
            battery_id=host._v2_battery_id,
            intent_default=host._v2_intent,
            condition_default=host._v2_condition_before,
        )
        legacy = restore_trace_identity(host, {
            "v2_intent": "invalid", "v2_condition_before": "invalid",
        })
        self.assertEqual(pure, legacy)
        # Plain string defaults preserve arbitrary document values, including invalid labels.
        self.assertEqual((pure.intent, pure.condition_before), ("invalid", "invalid"))
        self.assertEqual(host.__dict__, before)

    def test_supplied_now_is_used_without_reading_clock(self):
        host = _Host()
        host.total_start_time = 0
        args = dict(
            total_start_time=0, battery_type=host.battery_type,
            ah_capacity=host.ah_capacity, battery_id=host._v2_battery_id,
            intent_default=_Intent.DIAGNOSTIC,
            condition_default=_Condition.HEALTHY, now_s=7654.25,
        )
        with patch("runtime.charge.session.time.time", side_effect=AssertionError("clock read")):
            snapshot = project_trace_identity({"v2_trace_started_at": "bad"}, **args)
        self.assertEqual(snapshot.started_at, 7654.25)

    def test_module_has_no_production_or_manual_mode_imports(self):
        source = Path(__file__).parents[1] / "runtime" / "charge" / "session.py"
        tree = ast.parse(source.read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
        forbidden = ("manual_mode", "runtime.charge.persistence", "runtime.production_runtime")
        self.assertFalse([name for name in imported if name in forbidden])


if __name__ == "__main__":
    unittest.main()
