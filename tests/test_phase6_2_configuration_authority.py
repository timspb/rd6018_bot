"""Phase 6.2 configuration authority contracts; no runtime wiring."""

from __future__ import annotations

import ast
from pathlib import Path
import unittest

from application.configuration_authority import ConfigurationAuthority, ConfigurationParameter, ConfigurationSection


ROOT = Path(__file__).resolve().parents[1]
AUTHORITY = ROOT / "application" / "configuration_authority.py"


class ConfigurationAuthorityTests(unittest.TestCase):
    def test_parameter_has_owner_type_default_validator_description(self) -> None:
        parameter = ConfigurationParameter("safety.example", ConfigurationSection.SAFETY, "Safety Domain", float, 1.0, lambda value: value > 0, "test safety value")
        authority = ConfigurationAuthority({parameter.key: parameter})
        self.assertEqual(("safety.example",), authority.keys())
        self.assertEqual((ConfigurationSection.SAFETY,), authority.sections())

    def test_duplicate_keys_are_rejected(self) -> None:
        parameter = ConfigurationParameter("charge.example", ConfigurationSection.CHARGE, "Charge Domain", int, 1, lambda value: value > 0, "test charge value")
        authority = ConfigurationAuthority({parameter.key: parameter})
        with self.assertRaises(ValueError):
            authority.register(parameter)

    def test_all_configuration_sections_are_documented(self) -> None:
        text = (ROOT / "docs" / "RD6018_CONFIGURATION_AUTHORITY_MODEL.md").read_text(encoding="utf-8")
        for section in ("Charge", "Strategy", "Safety", "Containment", "Lease", "Execution", "Transport", "UI", "Persistence"):
            self.assertIn(f"| {section} |", text)

    def test_safety_configuration_consumption_catalogue_exists(self) -> None:
        text = (ROOT / "docs" / "RD6018_CONFIGURATION_AUTHORITY_MODEL.md").read_text(encoding="utf-8")
        for key in ("safety.ovp_max_v", "safety.ocp_max_a", "safety.temperature_critical_c", "safety.telemetry_freshness_s", "safety.watchdog_timeout_s", "safety.grace_period_s"):
            self.assertIn(f"`{key}`", text)
        self.assertIn("Safety consumers must declare", text)

    def test_authority_contract_has_no_hardcoded_runtime_values_or_io(self) -> None:
        tree = ast.parse(AUTHORITY.read_text(encoding="utf-8"), filename=str(AUTHORITY))
        forbidden_imports = ("yaml", "dotenv", "sqlite", "hass", "esphome", "telegram", "physical")
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.append(node.module or "")
        self.assertEqual([], [name for name in imports if any(token in name.lower() for token in forbidden_imports)])
        numeric_literals = [node for node in ast.walk(tree) if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool)]
        self.assertEqual([], numeric_literals)

    def test_configuration_document_forbids_duplicate_defaults_and_magic_numbers(self) -> None:
        text = (ROOT / "docs" / "RD6018_CONFIGURATION_AUTHORITY_MODEL.md").read_text(encoding="utf-8")
        self.assertIn("No new magic number", text)
        self.assertIn("duplicated default", text)
        self.assertIn("legacy drift", text)


if __name__ == "__main__":
    unittest.main()
