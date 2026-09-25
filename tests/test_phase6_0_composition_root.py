"""Phase 6.0 composition-root contracts; no runtime wiring."""

from __future__ import annotations

import ast
from pathlib import Path
import unittest

from application.composition_contract import ApplicationComposition


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "RD6018_COMPOSITION_ROOT_MODEL.md"


class CompositionRootContractTests(unittest.TestCase):
    def test_application_composition_has_single_layer_shape(self) -> None:
        fields = tuple(ApplicationComposition.__dataclass_fields__)
        self.assertEqual(("domain", "application", "infrastructure", "ui", "persistence"), fields)
        instance = ApplicationComposition(*(object() for _ in fields))
        self.assertIsNotNone(instance)

    def test_composition_contract_has_no_infrastructure_imports_or_actuators(self) -> None:
        path = ROOT / "application" / "composition_contract.py"
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        forbidden = ("hass", "esphome", "telegram", "physical", "turn_on", "turn_off", "set_voltage", "set_current")
        violations = [
            f"{path.name}:{node.lineno}:{node.attr}"
            for node in ast.walk(tree)
            if isinstance(node, ast.Attribute) and node.attr in forbidden
        ]
        self.assertEqual([], violations)

    def test_transitional_bootstrap_has_no_physical_calls_or_domain_algorithms(self) -> None:
        path = ROOT / "v2_bootstrap.py"
        source = path.read_text(encoding="utf-8")
        for token in ("turn_on(", "turn_off(", "set_voltage(", "set_current(", "STAGE_", "MIX_DONE_TIMER", "def tick("):
            self.assertNotIn(token, source, token)

    def test_documented_single_root_and_no_duplicate_bootstrap(self) -> None:
        text = DOC.read_text(encoding="utf-8")
        for phrase in ("one authoritative `ApplicationComposition`", "one startup handoff", "not a second production root", "second bootstrap"):
            self.assertIn(phrase, text)
        self.assertIn("bot_legacy.py", text)

    def test_bootstrap_does_not_define_domain_transition_logic(self) -> None:
        source = (ROOT / "v2_bootstrap.py").read_text(encoding="utf-8")
        for marker in ("AGM_STAGES", "EFB_MIX_MAX_HOURS", "CA_MIX_MAX_HOURS", "MAIN_STAGE_MAX_HOURS", "current_stage ="):
            self.assertNotIn(marker, source)


if __name__ == "__main__":
    unittest.main()
