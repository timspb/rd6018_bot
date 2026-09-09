from pathlib import Path
import unittest


class AutonomousStartupAuthorityContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = Path("bot.py").read_text(encoding="utf-8")

    def test_edge_authority_is_resolved_before_managed_startup_recovery(self):
        prime = self.text.index("edge_authority_known = await _prime_rd_edge_authority()")
        mix_recovery = self.text.index("await _rd_managed_mix_adoption.recover_startup()")
        live_recovery = self.text.index("await _rd_managed_live_adoption.recover_startup()")
        diagnostic_recovery = self.text.index("await recover_diagnostic_persistence(_legacy)")
        self.assertLess(prime, mix_recovery)
        self.assertLess(prime, live_recovery)
        self.assertLess(prime, diagnostic_recovery)

    def test_managed_recovery_is_gated_off_for_autonomous_or_unknown_edge_authority(self):
        self.assertIn(
            "if edge_authority_known and not _rd_control_mode.edge_autonomous:",
            self.text,
        )
        self.assertIn("_rd_control_mode._edge_autonomous = True", self.text)
        self.assertIn("if not _explicit_edge_authority(raw):", self.text)

    def test_authority_parser_accepts_only_explicit_boolean_states(self):
        block = self.text.split("def _explicit_edge_authority", 1)[1].split(
            "async def _prime_rd_edge_authority", 1
        )[0]
        self.assertIn('{"on", "off", "true", "false", "1", "0"}', block)
        self.assertNotIn("unavailable", block)
        self.assertNotIn("unknown", block)

    def test_startup_authority_preflight_is_read_only(self):
        block = self.text.split("async def _prime_rd_edge_authority", 1)[1].split(
            "async def main", 1
        )[0]
        self.assertIn("guard._raw_live()", block)
        for forbidden in (
            "turn_on(",
            "turn_off(",
            "set_voltage(",
            "set_current(",
            "set_ovp(",
            "set_ocp(",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, block)


if __name__ == "__main__":
    unittest.main()
