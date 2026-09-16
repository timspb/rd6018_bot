"""Phase 5.1 static contracts: domain extraction without runtime wiring."""

from __future__ import annotations

import ast
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
CHARGE_ROOT = ROOT / "runtime" / "charge"
DOCS = (
    ROOT / "docs" / "RD6018_DOMAIN_LOGIC_EXTRACTION.md",
    ROOT / "docs" / "RD6018_CHARGE_STATE_MODEL.md",
    ROOT / "docs" / "RD6018_CHARGE_PROGRAM_MODEL.md",
)


class DomainExtractionContractTests(unittest.TestCase):
    def test_required_domain_documents_exist_and_name_all_profiles(self) -> None:
        text = "\n".join(path.read_text(encoding="utf-8") for path in DOCS)
        for profile in ("AGM", "EFB", "Ca/Ca", "Custom"):
            self.assertIn(profile, text)
        for term in ("phase", "transition", "termination", "hold", "timer", "limits"):
            self.assertIn(term, text.lower())

    def test_legacy_states_are_represented_in_state_contract(self) -> None:
        source = (ROOT / "charge_logic.py").read_text(encoding="utf-8")
        expected = (
            "Подготовка", "Main Charge", "Десульфатация", "Mix Mode",
            "Безопасное ожидание", "Остывание", "Done", "Idle",
        )
        doc = (ROOT / "docs" / "RD6018_CHARGE_STATE_MODEL.md").read_text(encoding="utf-8")
        for state in expected:
            self.assertIn(state, source)
        for state in ("PREP", "MAIN", "DESULFATION", "MIX", "SAFE_WAIT", "COOLING", "DONE", "IDLE"):
            self.assertIn(f"`{state}`", doc)

    def test_native_domain_has_no_transport_or_physical_imports(self) -> None:
        forbidden = {
            "telegram", "aiogram", "hass_api", "homeassistant", "esphome",
            "physical", "safe_output", "controller", "serial", "modbus",
        }
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
                    lowered = name.lower()
                    if any(token in lowered for token in forbidden):
                        violations.append(f"{path.relative_to(ROOT)}: {name}")
        self.assertEqual([], violations)

    def test_domain_source_has_no_physical_method_calls(self) -> None:
        forbidden_attrs = {"turn_on", "turn_off", "set_voltage", "set_current", "safe_enable_output"}
        violations: list[str] = []
        for path in CHARGE_ROOT.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Attribute) and node.attr in forbidden_attrs:
                    violations.append(f"{path.relative_to(ROOT)}:{node.lineno}:{node.attr}")
        self.assertEqual([], violations)

    def test_program_contracts_are_explicit_and_pure(self) -> None:
        source = (ROOT / "docs" / "RD6018_CHARGE_PROGRAM_MODEL.md").read_text(encoding="utf-8")
        for marker in ("Common contract", "Required domain measurements", "Completion and containment"):
            self.assertIn(marker, source)
        from runtime.charge.programs import DeltaConfig, ManualTargets, MinimumConfig

        self.assertEqual("CV", DeltaConfig(14.4, 2.0, "CV", 0.3, 0.06).mode)
        self.assertEqual("minimum", MinimumConfig(14.4, 2.0, 0.3).active_stage)
        self.assertEqual(14.4, ManualTargets(14.4, 2.0).voltage)


if __name__ == "__main__":
    unittest.main()
