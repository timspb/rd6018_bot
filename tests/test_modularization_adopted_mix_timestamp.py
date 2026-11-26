from __future__ import annotations

import ast
import math
import unittest
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from runtime.charge.evidence.adopted_mix_source_timestamp import adopted_mix_source_timestamp


class AdoptedMixSourceTimestampTests(unittest.TestCase):
    @staticmethod
    def _compatibility_wrapper():
        source = Path("rd_managed_mix.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        cls = next(node for node in tree.body
                   if isinstance(node, ast.ClassDef) and node.name == "ManagedMixAdoptionCoordinator")
        method = next(node for node in cls.body
                      if isinstance(node, ast.FunctionDef) and node.name == "_source_timestamp")
        module = ast.fix_missing_locations(ast.Module(body=[method], type_ignores=[]))
        namespace = {"adopted_mix_source_timestamp": adopted_mix_source_timestamp,
                     "Any": Any, "Optional": Optional}
        exec(compile(module, "rd_managed_mix.py", "exec"), namespace)
        return namespace["_source_timestamp"]

    def test_missing_or_nonmapping_metadata_returns_none(self):
        self.assertIsNone(adopted_mix_source_timestamp({}))
        self.assertIsNone(adopted_mix_source_timestamp({"_meta": None}))
        self.assertIsNone(adopted_mix_source_timestamp({"_meta": []}))
        self.assertIsNone(adopted_mix_source_timestamp({"_meta": {"current": []}}))

    def test_uses_earliest_valid_timestamp_from_known_fields(self):
        live = {"_meta": {
            "current": {"last_updated": "2026-01-03T00:00:00+00:00"},
            "battery_voltage": {"last_reported": "2026-01-01T00:00:00+00:00"},
            "temp_ext": {"last_reported": "2026-01-02T00:00:00+00:00"},
            "unrelated": {"last_reported": "2000-01-01T00:00:00+00:00"},
        }}
        expected = datetime.fromisoformat("2026-01-01T00:00:00+00:00").timestamp()
        self.assertEqual(adopted_mix_source_timestamp(live), expected)

    def test_last_reported_has_precedence_even_when_invalid(self):
        live = {"_meta": {
            "current": {
                "last_reported": "not-a-date",
                "last_updated": "2026-01-01T00:00:00+00:00",
            },
            "is_cv": {"last_updated": "2026-01-02T00:00:00+00:00"},
        }}
        expected = datetime.fromisoformat("2026-01-02T00:00:00+00:00").timestamp()
        self.assertEqual(adopted_mix_source_timestamp(live), expected)

    def test_z_timezone_is_utc(self):
        live = {"_meta": {"is_cc": {"last_reported": "2026-01-01T00:00:00Z"}}}
        expected = datetime.fromisoformat("2026-01-01T00:00:00+00:00").timestamp()
        self.assertEqual(adopted_mix_source_timestamp(live), expected)

    def test_nonpositive_nonfinite_and_malformed_timestamps_are_excluded(self):
        live = {"_meta": {
            "current": {"last_reported": "1960-01-01T00:00:00+00:00"},
            "battery_voltage": {"last_reported": "1970-01-01T00:00:00+00:00"},
            "temp_ext_v2": {"last_reported": "not-a-date"},
            "temp_ext": {"last_reported": "999999-01-01T00:00:00+00:00"},
            "regulation_code": {"last_reported": "2026-01-01T00:00:00+00:00"},
        }}
        expected = datetime.fromisoformat("2026-01-01T00:00:00+00:00").timestamp()
        result = adopted_mix_source_timestamp(live)
        self.assertEqual(result, expected)
        self.assertTrue(math.isfinite(result))

    def test_input_controller_like_state_is_untouched_and_wrapper_matches(self):
        live = {"_meta": {"current": {"last_updated": "2026-01-01T00:00:00Z"}},
                "output": True, "voltage": 14.2}
        before = {key: (dict(value) if isinstance(value, dict) else value)
                  for key, value in live.items()}
        pure_value = adopted_mix_source_timestamp(live)
        self.assertEqual(self._compatibility_wrapper()(live), pure_value)
        self.assertEqual(live, before)

    def test_compatibility_wrapper_is_static_thin_delegate(self):
        source = Path("rd_managed_mix.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        cls = next(node for node in tree.body
                   if isinstance(node, ast.ClassDef) and node.name == "ManagedMixAdoptionCoordinator")
        method = next(node for node in cls.body
                      if isinstance(node, ast.FunctionDef) and node.name == "_source_timestamp")
        self.assertTrue(any(isinstance(decorator, ast.Name) and decorator.id == "staticmethod"
                            for decorator in method.decorator_list))
        self.assertEqual(len(method.body), 1)
        returned = method.body[0]
        self.assertIsInstance(returned, ast.Return)
        self.assertIsInstance(returned.value, ast.Call)
        self.assertIsInstance(returned.value.func, ast.Name)
        self.assertEqual(returned.value.func.id, "adopted_mix_source_timestamp")
        self.assertEqual(len(returned.value.args), 1)
        self.assertIsInstance(returned.value.args[0], ast.Name)
        self.assertEqual(returned.value.args[0].id, "live")

    def test_module_has_no_physical_or_filesystem_imports(self):
        source = Path("runtime/charge/evidence/adopted_mix_source_timestamp.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        forbidden = {"os", "pathlib", "io", "socket", "subprocess", "asyncio", "hass_api",
                     "application.execution_port", "runtime.production_runtime", "rd_managed_mix"}
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.add(node.module or "")
        self.assertFalse(any(name in forbidden or any(name.startswith(item + ".") for item in forbidden)
                             for name in imported), imported)


if __name__ == "__main__":
    unittest.main()
