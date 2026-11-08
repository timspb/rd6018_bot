"""Regression guards for the ERADICATION-09 charge_logic dependency contraction."""

from __future__ import annotations

import ast
from pathlib import Path
import unittest

from runtime.charge.persistence import SESSION_FILE, SESSION_START_MAX_AGE_S
from runtime.charge.strategy.exit_variables import (
    MIX_CC_DELTA_V_EXIT_V,
    MIX_CV_DELTA_I_EXIT_A,
)
from runtime.safety.variables import (
    HIGH_V_FAST_TIMEOUT_S,
    HIGH_V_THRESHOLD_V,
    MAX_STAGE_CURRENT_A,
    PROTECTION_OCP_MARGIN_A,
    PROTECTION_OVP_MARGIN_V,
    WATCHDOG_TIMEOUT_S,
)


ROOT = Path(__file__).resolve().parents[1]


class ChargeLogicDependencyContractionTests(unittest.TestCase):
    def test_canonical_values_preserve_accepted_production_baseline(self) -> None:
        self.assertEqual("charge_session.json", SESSION_FILE)
        self.assertEqual(24 * 60 * 60, SESSION_START_MAX_AGE_S)
        self.assertEqual(0.03, MIX_CC_DELTA_V_EXIT_V.default)
        self.assertEqual(0.03, MIX_CV_DELTA_I_EXIT_A.default)
        self.assertEqual(12.0, MAX_STAGE_CURRENT_A.default)
        self.assertEqual(0.1, PROTECTION_OVP_MARGIN_V.default)
        self.assertEqual(0.1, PROTECTION_OCP_MARGIN_A.default)
        self.assertEqual(300.0, WATCHDOG_TIMEOUT_S.default)
        self.assertEqual(300.0, HIGH_V_FAST_TIMEOUT_S.default)
        self.assertEqual(HIGH_V_FAST_TIMEOUT_S.default, WATCHDOG_TIMEOUT_S.default)
        self.assertEqual(15.0, HIGH_V_THRESHOLD_V.default)

    def test_high_voltage_communication_watchdog_has_no_early_off_path(self) -> None:
        """A stale heartbeat above 15 V waits 300s, not a separate 60s."""
        tree = ast.parse((ROOT / "runtime/safety/communication_watchdog.py").read_text(encoding="utf-8"))
        watchdog = next(
            node for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "communication_shutdown_due"
        )
        names = {
            node.id for node in ast.walk(watchdog) if isinstance(node, ast.Name)
        }
        self.assertIn("timeout_s", names)
        self.assertNotIn("HIGH_V_FAST_TIMEOUT", names)
        self.assertNotIn("HIGH_V_THRESHOLD", names)
        observer = (ROOT / "runtime/safety/watchdog_runtime.py").read_text(encoding="utf-8")
        self.assertEqual(observer.count("await app._hard_stop_charge()"), 1)
        self.assertIn("communication_shutdown_due(", observer)

    @staticmethod
    def _charge_logic_imports(relative_path: str) -> set[str]:
        path = ROOT / relative_path
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imports: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "charge_logic":
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "charge_logic":
                        imports.add("<module>")
        return imports

    def test_contracted_consumers_do_not_reimport_historical_charge_logic_values(self) -> None:
        consumers = (
            "manual_mode.py",
            "manual_runtime.py",
            "manual_text.py",
            "mix_active_authority.py",
            "production_controller.py",
            "runtime/charge/profiles/manual.py",
            "runtime/production_runtime.py",
            "runtime_safety.py",
            "managed_runtime_safety.py",
        )
        violations = {
            path: sorted(self._charge_logic_imports(path))
            for path in consumers
            if self._charge_logic_imports(path)
        }
        self.assertEqual({}, violations)

    def test_charge_controller_has_no_historical_charge_logic_edge(self) -> None:
        self.assertEqual(
            set(),
            self._charge_logic_imports("charge_controller.py"),
        )

        path = ROOT / "charge_controller.py"
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        controller = next(
            node
            for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "ManagedChargeController"
        )
        self.assertEqual(controller.bases, [])


if __name__ == "__main__":
    unittest.main()
