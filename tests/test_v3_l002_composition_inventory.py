from __future__ import annotations

import ast
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
BOT = ROOT / "bot.py"

RETIRED_COMPATIBILITY_MODULES = {
    "auto_manual_off_v2",
    "done_storage_restore",
    "live_output_readback_v2",
    "production_guardrails_v2",
    "soft_watchdog_containment",
    "telegram_startup_resilience",
}

CORE_DOMAIN_COMPONENTS = {
    "install_diagnostic_persistence",
    "install_manual_context_preprocessor",
    "install_manual_context_ui",
    "install_mix_only_mode",
    "install_v2",
}

OWNERSHIP_AND_RUNTIME_COMPONENTS = {
    "install_hands_off_background_isolation",
    "install_managed_live_adoption",
    "install_managed_mix_adoption",
    "install_rd_autonomous_final_hmi",
    "install_rd_autonomous_mode",
    "install_rd_control_mode",
    "install_rd_hands_off_release",
    "install_rd_live_adoption",
    "install_rd_ownership_recovery",
    "install_rd_startup_authority_gate",
}

PHYSICAL_VALIDATION_COMPONENTS = {
    "install_physical_test_control",
    "install_physical_test_control_d062",
    "install_physical_test_control_d062_delta",
    "install_physical_test_control_diagnostic",
    "install_physical_test_control_pb_mode",
    "install_physical_test_control_programmed_readback",
    "install_physical_test_control_source_faults",
}

OPERATOR_UI_COMPONENTS = {
    "install_analysis_screen",
    "install_charge_program_screen",
    "install_custom_cancel_route",
    "install_entities_screen",
    "install_help_screen",
    "install_home_command",
    "install_journal_screen",
    "install_mix_action_eligibility",
    "install_off_conditions_screen",
    "install_operator_destructive_guard",
    "install_operator_details_screen",
    "install_operator_graph_dashboard",
    "install_operator_hmi",
    "install_operator_managed_stop",
    "install_operator_navigation_recovery",
    "install_operator_output_truth",
    "install_service_details_screen",
    "install_stats_screen",
}

EXPECTED_CANONICAL_INSTALLERS = (
    CORE_DOMAIN_COMPONENTS
    | OWNERSHIP_AND_RUNTIME_COMPONENTS
    | PHYSICAL_VALIDATION_COMPONENTS
    | OPERATOR_UI_COMPONENTS
)


def _compose_install_calls() -> set[str]:
    tree = ast.parse(BOT.read_text(encoding="utf-8"))
    composition = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "ProductionComposition"
    )
    compose = next(
        node
        for node in composition.body
        if isinstance(node, ast.FunctionDef) and node.name == "compose"
    )
    return {
        node.func.id
        for node in ast.walk(compose)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id.startswith("install_")
    }


class L002CompositionInventoryTests(unittest.TestCase):
    def test_remaining_installers_are_explicitly_classified_canonical_components(self) -> None:
        self.assertEqual(_compose_install_calls(), EXPECTED_CANONICAL_INSTALLERS)

    def test_retired_patch_modules_have_zero_production_import_reachability(self) -> None:
        offenders: list[str] = []
        for path in ROOT.rglob("*.py"):
            if "tests" in path.parts or "__pycache__" in path.parts:
                continue
            if path.stem in RETIRED_COMPATIBILITY_MODULES:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name in RETIRED_COMPATIBILITY_MODULES:
                            offenders.append(f"{path.relative_to(ROOT)}:{alias.name}")
                elif (
                    isinstance(node, ast.ImportFrom)
                    and node.module in RETIRED_COMPATIBILITY_MODULES
                ):
                    offenders.append(f"{path.relative_to(ROOT)}:{node.module}")
        self.assertEqual(offenders, [])

    def test_retired_patch_symbols_are_absent_from_production_composition(self) -> None:
        source = BOT.read_text(encoding="utf-8")
        for module in sorted(RETIRED_COMPATIBILITY_MODULES):
            with self.subTest(module=module):
                self.assertNotIn(module, source)
        retired_installers = {
            "install_auto_manual_off_contract",
            "install_done_storage_restore",
            "install_output_state_readback",
            "install_production_guardrails",
            "install_soft_watchdog_containment",
            "install_telegram_startup_resilience",
        }
        self.assertTrue(retired_installers.isdisjoint(_compose_install_calls()))


if __name__ == "__main__":
    unittest.main()
