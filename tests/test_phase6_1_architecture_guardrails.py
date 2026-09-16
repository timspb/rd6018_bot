"""Phase 6.1 static architecture guardrails; no runtime integration."""

from __future__ import annotations

import ast
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "RD6018_ARCHITECTURE_GUARDRAILS.md"


def _imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.append(node.module or "")
    return names


class ArchitectureGuardrailTests(unittest.TestCase):
    def test_domain_import_graph_isolated(self) -> None:
        forbidden = ("telegram", "aiogram", "hass_api", "homeassistant", "esphome", "persistence", "database", "runtime.physical", "controller", "safe_output")
        violations = [
            f"{path.relative_to(ROOT)}: {name}"
            for path in (ROOT / "runtime" / "charge").rglob("*.py")
            for name in _imports(path)
            if any(token in name.lower() for token in forbidden)
        ]
        self.assertEqual([], violations)

    def test_ui_import_graph_has_no_fsm_or_physical_owner(self) -> None:
        forbidden = ("charge_logic", "charge_controller", "runtime.charge", "runtime.physical", "hass_api", "homeassistant", "esphome", "safe_output", "controller")
        violations = [
            f"{path.relative_to(ROOT)}: {name}"
            for path in (ROOT / "application").glob("operator_*.py")
            for name in _imports(path)
            if any(token in name.lower() for token in forbidden)
        ]
        self.assertEqual([], violations)

    def test_infrastructure_transports_do_not_import_domain_or_ui(self) -> None:
        forbidden = ("runtime.charge", "charge_logic", "charge_controller", "runtime.ui", "telegram", "aiogram", "operator_")
        transport_root = ROOT / "runtime" / "physical" / "transports"
        violations = [
            f"{path.relative_to(ROOT)}: {name}"
            for path in transport_root.rglob("*.py")
            for name in _imports(path)
            if any(token in name.lower() for token in forbidden)
        ]
        self.assertEqual([], violations)

    def test_composition_and_transitional_bootstrap_are_algorithm_free(self) -> None:
        forbidden_attrs = {"turn_on", "turn_off", "set_voltage", "set_current", "safe_enable_output"}
        for path in (ROOT / "application" / "composition_contract.py", ROOT / "v2_bootstrap.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            calls = [f"{path.name}:{node.lineno}:{node.attr}" for node in ast.walk(tree) if isinstance(node, ast.Attribute) and node.attr in forbidden_attrs]
            self.assertEqual([], calls)
        bootstrap = (ROOT / "v2_bootstrap.py").read_text(encoding="utf-8")
        for token in ("STAGE_", "MIX_DONE_TIMER", "MAIN_STAGE_MAX_HOURS", "def tick(", "current_stage ="):
            self.assertNotIn(token, bootstrap, token)

    def test_single_production_root_and_no_secondary_new_root(self) -> None:
        bot = (ROOT / "bot.py").read_text(encoding="utf-8")
        self.assertEqual(1, bot.count("if __name__ == \"__main__\":"))
        self.assertEqual(1, bot.count("asyncio.run(main())"))
        self.assertNotIn("import bot_legacy", bot)
        for path in ((ROOT / "application").rglob("*.py"), (ROOT / "runtime" / "charge").rglob("*.py")):
            for candidate in path:
                source = candidate.read_text(encoding="utf-8")
                self.assertNotIn("asyncio.run(main())", source, str(candidate))

    def test_guardrail_document_tracks_all_boundary_classes(self) -> None:
        text = DOC.read_text(encoding="utf-8")
        for term in ("Domain isolation", "UI isolation", "Infrastructure isolation", "Composition-root purity", "Bootstrap inventory", "Hidden-global", "duplicate-root"):
            self.assertIn(term, text)


if __name__ == "__main__":
    unittest.main()
