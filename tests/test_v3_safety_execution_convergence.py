from __future__ import annotations

import ast
from pathlib import Path
import unittest

from runtime.charge.strategy.mix_variables import mix_max_active_hours
from runtime.safety.voltage_variables import (
    PB_AUTOMATIC_TARGET_CEILING_V,
    clamp_pb_automatic_target_voltage,
)


ROOT = Path(__file__).resolve().parents[1]
SKIP_PARTS = {
    ".git",
    ".venv",
    "tests",
    "esphome",
    "docs",
    "assets",
    "tools",
    "__pycache__",
    ".pytest_cache",
}
PHYSICAL_METHODS = {
    "set_voltage",
    "set_current",
    "set_ovp",
    "set_ocp",
    "turn_on",
    "turn_off",
    "safe_enable_output",
}
APPROVED_PHYSICAL_IMPLEMENTATION = {
    "application/execution_port.py",
    "hass_api.py",
    "runtime_safety_strict.py",
    "managed_runtime_safety.py",
    "safe_output.py",
}
RETIRED_EXECUTION_COMPATIBILITY = {
    "recipe_output.py",
    "recovery_orchestrator.py",
}


def _production_python_files():
    for path in sorted(ROOT.rglob("*.py")):
        rel = path.relative_to(ROOT)
        if any(part in SKIP_PARTS for part in rel.parts):
            continue
        yield rel.as_posix(), path


def _direct_physical_call_modules() -> set[str]:
    result: set[str] = set()
    for module, path in _production_python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in PHYSICAL_METHODS
            ):
                result.add(module)
                break
    return result


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            modules.add(node.module or "")
    return modules


class V3SafetyExecutionConvergenceTests(unittest.TestCase):
    def test_live_direct_physical_calls_are_confined_to_approved_implementation(self):
        direct = _direct_physical_call_modules()
        unexpected = direct - APPROVED_PHYSICAL_IMPLEMENTATION - RETIRED_EXECUTION_COMPATIBILITY
        self.assertEqual(set(), unexpected)

    def test_retired_recovery_execution_compatibility_is_absent(self):
        for rel in RETIRED_EXECUTION_COMPATIBILITY:
            self.assertFalse((ROOT / rel).exists(), rel)

    def test_pb_voltage_ceiling_has_one_canonical_value_owner(self):
        self.assertEqual(16.6, float(PB_AUTOMATIC_TARGET_CEILING_V.default))
        self.assertEqual(16.6, clamp_pb_automatic_target_voltage(17.2))
        config_source = (ROOT / "config.py").read_text(encoding="utf-8")
        self.assertIn("PB_AUTOMATIC_TARGET_CEILING_V.default", config_source)
        self.assertNotIn("MAX_VOLTAGE = 16.6", config_source)

    def test_historical_charge_logic_and_safety_sources_are_removed(self):
        self.assertFalse((ROOT / "charge_logic.py").exists())
        self.assertFalse((ROOT / "legacy_safety.py").exists())

    def test_trace_reporting_uses_canonical_mix_authority_windows(self):
        source = (ROOT / "recovery_trace_report.py").read_text(encoding="utf-8")
        self.assertNotIn("legacy_safety", source)
        self.assertEqual(20.0, mix_max_active_hours("Ca/Ca"))
        self.assertEqual(24.0, mix_max_active_hours("EFB"))
        self.assertEqual(10.0, mix_max_active_hours("AGM"))
        self.assertIsNone(mix_max_active_hours("Custom"))



if __name__ == "__main__":
    unittest.main()
