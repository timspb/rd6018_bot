from pathlib import Path
import unittest


class AutonomousInstallOrderContractTests(unittest.TestCase):
    def test_production_telemetry_and_guardrail_wrappers_are_retired_before_ownership(self):
        text = Path("bot.py").read_text(encoding="utf-8")
        diagnostic = text.index("install_diagnostic_persistence(app)")
        ownership = text.index("install_rd_control_mode(app")
        autonomous = text.index("install_rd_autonomous_mode(")
        physical = text.index("install_physical_test_control(app)")
        self.assertNotIn("install_output_state_readback", text)
        self.assertNotIn("install_production_guardrails", text)
        self.assertLess(diagnostic, ownership)
        self.assertLess(ownership, autonomous)
        self.assertLess(autonomous, physical)

    def test_autonomous_hmi_is_after_output_truth_normalization(self):
        text = Path("bot.py").read_text(encoding="utf-8")
        truth = text.index("install_operator_output_truth(app)")
        autonomous_hmi = text.index("install_rd_autonomous_final_hmi(app")
        self.assertLess(truth, autonomous_hmi)

    def testapp_background_isolation_sees_final_startup_authority_gate(self):
        text = Path("bot.py").read_text(encoding="utf-8")
        startup = text.index("install_rd_startup_authority_gate(app")
        background = text.index("install_hands_off_background_isolation(app")
        self.assertLess(startup, background)

    def test_production_entrypoint_remains_bot_py(self):
        text = Path("AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("Production: `python bot.py`", text)
        self.assertNotIn("production entrypoint with `botapp.py`", text.split(
            "Production: `python bot.py`", 1
        )[1].split("\n", 1)[0])


if __name__ == "__main__":
    unittest.main()
