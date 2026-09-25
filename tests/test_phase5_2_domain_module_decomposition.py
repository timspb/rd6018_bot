"""Phase 5.2 module decomposition contracts; no runtime integration."""

from __future__ import annotations

import ast
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
CHARGE_ROOT = ROOT / "runtime" / "charge"
DOC = ROOT / "docs" / "RD6018_DOMAIN_MODULE_MODEL.md"


class DomainModuleDecompositionTests(unittest.TestCase):
    def test_module_ownership_contract_is_complete(self) -> None:
        text = DOC.read_text(encoding="utf-8")
        for module in ("Charge Domain", "Profile Domain", "Strategy Domain", "Session Domain", "Safety Domain"):
            self.assertIn(module, text)
        for column in ("Owns", "Consumes", "Exports", "Forbidden dependencies"):
            self.assertIn(column, text)

    def test_extracted_concepts_have_one_declared_target_boundary(self) -> None:
        text = DOC.read_text(encoding="utf-8")
        for concept in ("legacy phase strings/FSM", "AGM/EFB/Ca/Ca/Custom", "Main, Recovery, Mix", "Imin/Delta-I", "start/stop/restore/pause", "battery envelope"):
            self.assertIn(concept, text)
        self.assertIn("no second FSM/session owner", text)

    def test_unresolved_parity_blockers_are_tracked(self) -> None:
        text = DOC.read_text(encoding="utf-8")
        for blocker in ("EFB Mix authority", "Canonical CC Delta evidence", "Explicit Custom recipe schema", "pause/resume semantics"):
            self.assertIn(blocker, text)

    def test_charge_package_has_no_infrastructure_imports(self) -> None:
        forbidden = (
            "telegram", "aiogram", "hass_api", "homeassistant", "esphome",
            "physical", "safe_output", "controller", "serial", "modbus",
        )
        violations: list[str] = []
        for path in CHARGE_ROOT.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    names = [node.module or ""]
                else:
                    continue
                for name in names:
                    if any(token in name.lower() for token in forbidden):
                        violations.append(f"{path.relative_to(ROOT)}: {name}")
        self.assertEqual([], violations)

    def test_domain_modules_do_not_call_actuators(self) -> None:
        forbidden = {"turn_on", "turn_off", "set_voltage", "set_current", "safe_enable_output", "controller"}
        violations: list[str] = []
        for path in CHARGE_ROOT.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Attribute) and node.attr in forbidden:
                    violations.append(f"{path.relative_to(ROOT)}:{node.lineno}:{node.attr}")
        self.assertEqual([], violations)


if __name__ == "__main__":
    unittest.main()
