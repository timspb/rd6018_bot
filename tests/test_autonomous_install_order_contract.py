from pathlib import Path
import unittest


class AutonomousInstallOrderContractTests(unittest.TestCase):
    def test_production_installs_v2_safety_before_ownership_and_autonomous_boundaries(self):
        text = Path("bot.py").read_text(encoding="utf-8")
        safety = text.index("install_production_guardrails(_legacy)")
        ownership = text.index("install_rd_control_mode(_legacy")
        autonomous = text.index("install_rd_autonomous_mode(")
        physical = text.index("install_physical_test_control(_legacy)")
        self.assertLess(safety, ownership)
        self.assertLess(ownership, autonomous)
        self.assertLess(autonomous, physical)

    def test_autonomous_hmi_is_after_output_truth_normalization(self):
        text = Path("bot.py").read_text(encoding="utf-8")
        truth = text.index("install_operator_output_truth(_legacy)")
        autonomous_hmi = text.index("install_rd_autonomous_final_hmi(_legacy")
        self.assertLess(truth, autonomous_hmi)

    def test_production_entrypoint_remains_bot_py(self):
        text = Path("AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("Production: `python bot.py`", text)
        self.assertNotIn("production entrypoint with `bot_legacy.py`", text.split(
            "Production: `python bot.py`", 1
        )[1].split("\n", 1)[0])


if __name__ == "__main__":
    unittest.main()
