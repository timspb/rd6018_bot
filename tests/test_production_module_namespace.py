from pathlib import Path
import ast
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ProductionModuleNamespaceTests(unittest.TestCase):
    def test_no_production_python_filename_uses_v2_namespace(self):
        offenders = []
        for path in ROOT.rglob("*.py"):
            if any(part in {".git", "__pycache__", "tests"} for part in path.parts):
                continue
            if "v2" in path.name.lower():
                offenders.append(str(path.relative_to(ROOT)))
        self.assertEqual([], offenders)

    def test_retired_module_imports_are_absent_from_production_sources(self):
        retired = {
            "auto_strategy_v2", "charge_controller_v2", "manual_context_v2",
            "manual_runtime_v2", "manual_text_v2", "runtime_safety_v2",
            "sg_policy_v2", "v2_authority", "v2_battery_catalog",
            "v2_battery_input", "v2_bootstrap", "v2_bot_ui", "v2_mix_mode",
            "v2_sg_ui", "v2_ui", "v2_ui_polish", "runtime.v2_startup_recovery",
            "application.v2_v3_comparison",
        }
        violations = []
        for path in ROOT.rglob("*.py"):
            if any(part in {".git", "__pycache__", "tests"} for part in path.parts):
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                names = []
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    names = [node.module or ""]
                for name in names:
                    if name in retired:
                        violations.append(f"{path.relative_to(ROOT)}:{name}")
        self.assertEqual([], violations)

    def test_retired_production_type_names_are_absent(self):
        retired = (
            "ChargeControllerV2", "ProductionChargeControllerV2",
            "AutoStrategyProductionChargeControllerV2",
            "DiagnosticProductionChargeControllerV2", "V2RuntimeSafetyGuard",
            "V2RuntimeLifecycle", "V2StartTransactionAdapter",
            "V2StartTransactionInput", "V2TransactionOutcome",
            "V2StartEventContext", "V2TransactionRunner", "install_v2",
            "init_v2_storage",
        )
        violations = []
        for path in ROOT.rglob("*.py"):
            if any(part in {".git", "__pycache__", "tests"} for part in path.parts):
                continue
            source = path.read_text(encoding="utf-8")
            for name in retired:
                if name in source:
                    violations.append(f"{path.relative_to(ROOT)}:{name}")
        self.assertEqual([], violations)

    def test_retired_shadow_migration_modules_are_absent(self):
        retired = (
            "application/charge_orchestration.py",
            "application/configuration_ownership.py",
            "application/decision_authority.py",
            "application/decision_authority_shadow_run.py",
            "application/decision_comparison.py",
            "application/divergence_explanation.py",
            "application/dual_runtime.py",
            "application/execution_shadow_validation.py",
            "application/legacy_domain_adapter.py",
            "application/long_running_shadow_acceptance.py",
            "application/ownership_transition.py",
            "application/production_shadow_observer.py",
            "application/runtime_composition.py",
            "application/shadow_acceptance.py",
            "application/shadow_composition.py",
            "application/shadow_evidence.py",
            "application/staged_ownership.py",
            "application/telemetry_ownership.py",
            "application/transport_adapters_shadow.py",
            "runtime/charge/shadow",
            "runtime/output/shadow_bridge.py",
            "runtime/safety/parity.py",
        )
        self.assertEqual([], [rel for rel in retired if (ROOT / rel).exists()])

    def test_retired_application_contract_island_is_absent(self):
        retired = (
            "application/actuator_intent.py",
            "application/actuator_intent_adapter.py",
            "application/actuator_intent_mapping.py",
            "application/charge_event.py",
            "application/composition_contract.py",
            "application/composition_lifecycle.py",
            "application/configuration_authority.py",
            "application/configuration_decision_registry.py",
            "application/configuration_model.py",
            "application/containment_mapping.py",
            "application/containment_observation.py",
            "application/containment_result.py",
            "application/diagnostics_domain.py",
            "application/execution_boundary.py",
            "application/infrastructure_contracts.py",
            "application/operator_interface.py",
            "application/persistence_boundary.py",
            "application/rd_transport.py",
            "application/safety_boundary.py",
            "application/safety_state.py",
            "application/start_dry_run.py",
            "application/start_execution_adapter.py",
            "application/telemetry_authority.py",
            "application/ui_adapter.py",
            "telegram/adapter.py",
            "telegram/panel_store.py",
            "presentation/panel_actions.py",
            "presentation/panel_layout.py",
            "presentation/panel_renderer.py",
        )
        self.assertEqual([], [rel for rel in retired if (ROOT / rel).exists()])

    def test_historical_charge_fsm_sources_are_absent(self):
        self.assertFalse((ROOT / "charge_logic.py").exists())
        self.assertFalse((ROOT / "legacy_safety.py").exists())

    def test_retired_root_compatibility_modules_are_absent(self):
        retired = (
            "first_stage_evidence.py",
            "live_recovery_bridge.py",
            "mix_current_containment.py",
            "rd_operation_mode.py",
            "recipe_output.py",
            "recovery_orchestrator.py",
            "recovery_runtime.py",
        )
        self.assertEqual([], [rel for rel in retired if (ROOT / rel).exists()])

    def test_canonical_module_names_exist(self):
        for rel in (
            "auto_strategy.py", "charge_controller.py", "manual_context.py",
            "manual_runtime.py", "manual_text.py", "managed_runtime_safety.py",
            "sg_policy.py", "charge_authority.py", "battery_catalog.py",
            "battery_input.py", "production_bootstrap.py", "production_bot_ui.py",
            "mix_mode.py", "sg_ui.py", "ui_support.py", "ui_polish.py",
            "runtime/startup_recovery.py",
        ):
            self.assertTrue((ROOT / rel).is_file(), rel)


if __name__ == "__main__":
    unittest.main()
