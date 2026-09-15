"""EPIC B domain migration model and boundary tests."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "RD6018_DOMAIN_MIGRATION_MODEL.md"
CANONICAL = ROOT / "docs" / "RD6018_V3_CANONICAL_STATE.md"


class EpicBDomainMigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = DOC.read_text(encoding="utf-8")
        cls.canonical = CANONICAL.read_text(encoding="utf-8")

    def test_all_domain_blocks_and_comparison_contract_are_present(self) -> None:
        for term in (
            "Charge FSM domain",
            "Profile domain",
            "Strategy domain",
            "Session domain",
            "Safety domain",
            "V2 behavior",
            "V3 behavior",
            "Comparison",
            "Divergence explanation",
        ):
            self.assertIn(term, self.text)

    def test_all_profiles_and_classifications_are_present(self) -> None:
        for term in ("AGM", "EFB", "Ca/Ca", "Custom", "EXPECTED", "UNRESOLVED", "BUG", "ARCHITECTURAL IMPROVEMENT"):
            self.assertIn(term, self.text)
        for term in ("EFB 20 h/24 h", "CC Vmax/Delta-V versus current-drop", "Custom profile schema"):
            self.assertIn(term, self.text)

    def test_migration_preserves_v2_and_forbids_execution(self) -> None:
        for term in (
            "V2 remains the active owner",
            "wire the domain to production",
            "change START or ACTIVE",
            "physical execution",
            "no Telegram, HA, ESPHome, transport,",
            "V2 production tests remain unchanged and pass",
        ):
            self.assertIn(term, self.text)

    def test_canonical_state_records_epic_b_status(self) -> None:
        self.assertIn("### EPIC B — Domain migration", self.canonical)
        self.assertIn("Current status: shadow domain normalization", self.canonical)
        self.assertIn("V2 remains the decision, session, safety and execution owner", self.canonical)
        self.assertIn("EFB Mix 20 h versus 24 h", self.canonical)

    def test_existing_phase_parity_contracts_are_referenced(self) -> None:
        parity = (ROOT / "docs" / "RD6018_DOMAIN_RUNTIME_PARITY.md").read_text(encoding="utf-8")
        for term in ("FSM parity", "Profile parity", "Strategy parity", "Session parity", "UNRESOLVED"):
            self.assertIn(term, parity)


if __name__ == "__main__":
    unittest.main()
