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

    def test_autonomous_hmi_uses_app_aware_keyboard_and_output_truth_is_outer_filter(self):
        autonomous = Path("rd_autonomous_mode.py").read_text(encoding="utf-8")
        component = Path("runtime/ui/components/hmi_action_keyboard.py").read_text(encoding="utf-8")
        truth = Path("operator_output_truth.py").read_text(encoding="utf-8")
        hmi = Path("operator_hmi.py").read_text(encoding="utf-8")
        self.assertIn("app.rd_autonomous_mode = coordinator", autonomous)
        self.assertNotIn("hmi.build_operator_keyboard =", autonomous)
        self.assertIn("def _autonomous_keyboard(app, state, markup", component)
        self.assertNotIn("hmi.build_operator_hmi_state =", truth)
        self.assertNotIn("hmi.build_operator_keyboard =", truth)
        self.assertNotIn("hmi._more_keyboard =", truth)
        self.assertNotIn("hmi.render_operator_details =", truth)
        self.assertNotIn("hmi.render_operator_service_details =", truth)
        self.assertIn("normalize_operator_state(app, state, live", hmi)
        self.assertIn("filter_keyboard_for_output_truth(app, state, markup", hmi)
        self.assertIn("_more_keyboard(state, app)", hmi)

    def testapp_background_isolation_sees_final_startup_authority_gate(self):
        text = Path("bot.py").read_text(encoding="utf-8")
        startup = text.index("install_rd_startup_authority_gate(app")
        background = text.index("install_hands_off_background_isolation(app")
        self.assertLess(startup, background)

    def test_d061_release_marker_reconciles_during_composition_before_d065_runtime_recovery(self):
        bot = Path("bot.py").read_text(encoding="utf-8")
        background = Path("rd_hands_off_background.py").read_text(encoding="utf-8")
        self.assertIn("install_adopted_hands_off_release_retirement(app, manager)", background)
        background_install = bot.index("install_hands_off_background_isolation(app")
        recovery_construct = bot.index("_startup_recovery = StartupRecovery(")
        runtime_reconcile = bot.index("reconcile_startup_authority(")
        self.assertLess(background_install, recovery_construct)
        self.assertLess(recovery_construct, runtime_reconcile)

    def test_physical_test_release_and_adoption_delegate_to_existing_owners(self):
        text = Path("physical_test_control.py").read_text(encoding="utf-8")
        self.assertIn("manager = self.app.rd_control_mode_manager", text)
        self.assertIn("result = await manager.enter_hands_off()", text)
        self.assertIn("coordinator = self.app.rd_managed_live_adoption", text)
        self.assertIn("result = await coordinator.adopt(preview)", text)
        self.assertNotIn("EdgeSafetyLease(", text)
        self.assertNotIn("_write_mode(", text)

    def test_production_entrypoint_remains_bot_py(self):
        text = Path("AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("Production: `python bot.py`", text)
        self.assertNotIn("production entrypoint with `botapp.py`", text.split(
            "Production: `python bot.py`", 1
        )[1].split("\n", 1)[0])


if __name__ == "__main__":
    unittest.main()
