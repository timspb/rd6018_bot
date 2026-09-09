from pathlib import Path
import unittest


class AutonomousInstallOrderContractTests(unittest.TestCase):
    def test_production_installs_v2_safety_before_ownership_boundary(self):
        text = Path("bot.py").read_text(encoding="utf-8")
        safety = text.index("install_production_guardrails(_legacy)")
        ownership = text.index("install_rd_control_mode(_legacy")
        physical = text.index("install_physical_test_control(_legacy)")
        self.assertLess(safety, ownership)
        self.assertLess(ownership, physical)

    def test_production_entrypoint_remains_bot_py(self):
        text = Path("AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("Production: `python bot.py`", text)
        self.assertNotIn("production entrypoint with `bot_legacy.py`", text.split(
            "Production: `python bot.py`", 1
        )[1].split("\n", 1)[0])


if __name__ == "__main__":
    unittest.main()
