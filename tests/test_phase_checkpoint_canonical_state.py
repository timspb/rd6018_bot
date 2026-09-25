"""Canonical V3 state checkpoint consistency tests."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "RD6018_V3_CANONICAL_STATE.md"


class CanonicalStateCheckpointTests(unittest.TestCase):
    def setUp(self) -> None:
        self.text = DOC.read_text(encoding="utf-8")

    def test_current_architecture_graph_and_sections_exist(self) -> None:
        for term in ("UI", "Application", "Domain", "Execution Boundary", "Infrastructure", "HA / ESP / RD", "Configuration Authority", "Diagnostics", "Persistence", "Architecture Guardrails"):
            self.assertIn(term, self.text)
        for heading in ("## 2.", "## 3.", "## 4.", "## 5.", "## 6.", "## 7.", "## 8.", "## 9."):
            self.assertIn(heading, self.text)

    def test_ownership_matrix_is_complete(self) -> None:
        components = ("UI", "Telemetry", "Configuration", "Diagnostics", "Persistence", "Domain decisions", "Safety decisions", "Containment", "Session", "Execution", "HA control", "ESP control", "Physical output")
        for component in components:
            self.assertIn(f"| {component} |", self.text)
        for term in ("Current owner", "Target owner", "Migration mode", "Rollback possibility", "V3 staged", "V3 `ConfigurationAuthority`", "V2 execution"):
            self.assertIn(term, self.text)

    def test_migration_commits_are_present(self) -> None:
        for commit in ("b5d05f5", "ffa449d", "0e1bb69", "1e8c855", "4a46d44", "0f1baea", "87aa40d"):
            self.assertIn(commit, self.text)

    def test_invariants_and_unresolved_decisions_are_present(self) -> None:
        for term in ("does not import HA/ESP", "does not execute physical actions", "read-only", "single actuator execution boundary", "does not directly restore actuator, lease or safety state", "EFB Mix 20 h vs 24 h", "Custom profile schema", "watchdog values", "readback timeout policy"):
            self.assertIn(term, self.text)

    def test_no_contradiction_with_existing_contracts(self) -> None:
        ownership = (ROOT / "docs" / "RD6018_OWNERSHIP_MANIFEST.md").read_text(encoding="utf-8")
        guardrails = (ROOT / "docs" / "RD6018_ARCHITECTURE_GUARDRAILS.md").read_text(encoding="utf-8")
        self.assertIn("V2 remains owner", ownership)
        self.assertIn("Execution Boundary", self.text)
        self.assertIn("V2 remains the active", self.text)
        self.assertIn("execution and physical owner", self.text)
        self.assertIn("physical calls", guardrails)
        self.assertIn("V2 remains the execution owner", ownership) if "V2 remains the execution owner" in ownership else self.assertIn("Physical execution", ownership)

    def test_checkpoint_does_not_authorize_execution(self) -> None:
        for term in ("does not change V2 runtime, V3 execution", "START, ACTIVE", "physical ownership"):
            self.assertIn(term, self.text)


if __name__ == "__main__":
    unittest.main()
