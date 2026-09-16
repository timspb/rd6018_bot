"""Phase 5.4 state ownership/persistence contracts; no runtime changes."""

from __future__ import annotations

import ast
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "RD6018_STATE_PERSISTENCE_MODEL.md"


class StatePersistenceBoundaryTests(unittest.TestCase):
    def test_all_requested_state_categories_have_contract_rows(self) -> None:
        text = DOC.read_text(encoding="utf-8")
        for state in (
            "FSM/phase state", "charge session identity/lifecycle", "active profile/chemistry",
            "active targets", "telemetry history", "domain safety state", "containment state",
            "actuator state/setpoints", "UI/dashboard state",
        ):
            self.assertIn(state, text)
        for field in ("Owner", "Lifetime", "Persistence", "Recovery after restart"):
            self.assertIn(field, text)

    def test_ownership_invariants_are_explicit(self) -> None:
        text = DOC.read_text(encoding="utf-8")
        self.assertIn("ровно один authoritative owner", text)
        self.assertIn("UI does not own FSM", text)
        self.assertIn("transport does not own domain state", text)
        self.assertIn("Persistence files do not own runtime state", text)

    def test_ui_modules_do_not_import_runtime_or_transport_owners(self) -> None:
        forbidden = (
            "charge_logic", "runtime.charge", "runtime_safety", "rd_control_mode",
            "hass_api", "homeassistant", "esphome", "runtime.physical", "rd_transport",
        )
        violations: list[str] = []
        for path in (ROOT / "application").glob("operator_*.py"):
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

    def test_transport_contract_is_not_imported_by_domain_or_state_contracts(self) -> None:
        forbidden = ("rd_transport", "hass_api", "homeassistant", "esphome", "runtime.physical")
        violations: list[str] = []
        for path in (ROOT / "runtime" / "charge").rglob("*.py"):
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

    def test_restart_never_grants_physical_authority_from_persistence(self) -> None:
        text = DOC.read_text(encoding="utf-8")
        self.assertIn("cannot authorize START/ACTIVE", text)
        self.assertIn("never replay stale commands", text)
        self.assertIn("require fresh preflight", text)


if __name__ == "__main__":
    unittest.main()
