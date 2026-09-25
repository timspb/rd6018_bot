"""EPIC C infrastructure migration contract and boundary tests."""

from datetime import datetime, timezone
from pathlib import Path
import ast
import unittest

from application.infrastructure_contracts import ReadbackObservation


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "RD6018_INFRASTRUCTURE_MIGRATION_MODEL.md"
CANONICAL = ROOT / "docs" / "RD6018_V3_CANONICAL_STATE.md"


class EpicCInfrastructureMigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = DOC.read_text(encoding="utf-8")
        cls.canonical = CANONICAL.read_text(encoding="utf-8")

    def test_infrastructure_sections_and_failure_taxonomy_exist(self) -> None:
        for term in (
            "Telemetry infrastructure",
            "Canonical readback contract",
            "Control model — intent only",
            "Lease model",
            "Transport failure taxonomy",
            "HA unavailable",
            "ESP unavailable",
            "RD unavailable",
            "stale telemetry",
            "command unconfirmed",
        ):
            self.assertIn(term, self.text)

    def test_readback_contract_is_immutable_and_validated(self) -> None:
        observation = ReadbackObservation(
            requested_value=14.8,
            observed_value=14.79,
            timestamp=datetime.now(timezone.utc),
            source="ESP_DIRECT",
            confidence=1.0,
        )
        self.assertEqual(14.8, observation.requested_value)
        with self.assertRaises((AttributeError, TypeError)):
            observation.confidence = 0.5  # type: ignore[misc]
        with self.assertRaises(ValueError):
            ReadbackObservation(1, 1, observation.timestamp, "", 1.0)
        with self.assertRaises(ValueError):
            ReadbackObservation(1, 1, observation.timestamp, "HA", 1.1)

    def test_forbidden_infrastructure_side_effects_are_explicitly_blocked(self) -> None:
        for term in (
            "no HA/ESP writes",
            "physical calls",
            "never renew",
            "issue OFF",
            "does not connect HA or ESP clients",
            "V2 control ownership",
        ):
            self.assertIn(term, self.text)

    def test_contract_module_has_no_transport_or_physical_imports(self) -> None:
        module = ROOT / "application" / "infrastructure_contracts.py"
        tree = ast.parse(module.read_text(encoding="utf-8"), filename=str(module))
        forbidden = ("ha", "esp", "telegram", "transport", "physical", "controller", "lease")
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name.lower() for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.append((node.module or "").lower())
        self.assertEqual([], [item for item in imports if any(term in item for term in forbidden)])

    def test_canonical_state_records_epic_c_status(self) -> None:
        self.assertIn("### EPIC C — Infrastructure migration", self.canonical)
        self.assertIn("Current status: shadow infrastructure normalization", self.canonical)
        self.assertIn("V2 remains the control, lease and physical owner", self.canonical)


if __name__ == "__main__":
    unittest.main()
