"""PR00 characterization: RuntimeApp namespace contract.

This test freezes WHICH production modules write WHICH attributes onto the
application namespace object (the current "module-as-app" surface: ``app.X = ...``).

It exists so that any hidden ownership change (a new attribute written from a new
location, or an attribute silently moving owner) fails loudly during the runtime
ownership extraction migration. Updating the golden inventory is an explicit,
reviewed architecture decision.

READ-ONLY characterization: no production module is imported or modified; the
inventory is derived by parsing source with ``ast``.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# Directories that are not part of the production runtime module graph.
SKIP_DIRS = {
    ".git",
    ".venv",
    "tests",
    "esphome",
    "docs",
    "assets",
    "tools",
    "__pycache__",
    ".pytest_cache",
}

# Frozen inventory: every app.<attr> written anywhere in production modules.
APP_ATTRS_WRITTEN = frozenset(
    {
        "MIN_INPUT_VOLTAGE",
        "_build_and_send_dashboard",
        "_build_charge_modes_keyboard",
        "_build_dashboard_keyboard",
        "_charge_modes_text",
        "_charge_notify",
        "_compact_dashboard_caption",
        "_done_storage_restore_installed",
        "_format_stage_progress_line",
        "_hands_off_background_isolation_installed",
        "_hard_stop_charge",
        "_has_manual_off_condition",
        "_mix_action_eligibility_installed",
        "_operator_destructive_guard",
        "_operator_graph_dashboard_installed",
        "_operator_hmi_installed",
        "_operator_home_handler",
        "_operator_managed_stop_confirmations",
        "_operator_managed_stop_installed",
        "_operator_navigation_recovery_installed",
        "_operator_output_truth_installed",
        "_operator_pause_active",
        "_operator_pause_toggle",
        "_rd_autonomous_final_hmi_installed",
        "_rd_ownership_recovery_installed",
        "_refresh_operator_panel",
        "_restore_allows_auto_enable",
        "_send_notify_safe",
        "_soft_watchdog_containment_installed",
        "_soft_watchdog_incident",
        "_v2_bound_manual_middleware",
        "_v2_managed_charge_monitor_guard_installed",
        "_v2_manual_context_ui_installed",
        "_v2_manual_text_middleware",
        "_v2_production_guardrails_installed",
        "_v2_vin_psu_health_only",
        "charge_controller",
        "charge_monitor",
        "controlled_diagnostic_probe",
        "diagnostic_action_journal",
        "edge_safety_lease",
        "handle_ah_input",
        "handle_dialog_mode",
        "last_charge_alert_at",
        "last_chat_id",
        "last_checkpoint_time",
        "last_idle_alert_at",
        "last_user_id",
        "log_event",
        "manual_session_manager",
        "physical_test_control",
        "physical_test_control_d062",
        "physical_test_control_d062_delta",
        "physical_test_control_diagnostic",
        "physical_test_control_pb_mode",
        "physical_test_control_programmed_readback_v2",
        "physical_test_control_source_faults",
        "rd_autonomous_mode",
        "rd_control_mode_manager",
        "rd_live_mix_observer",
        "rd_managed_live_adoption",
        "rd_managed_mix_adoption",
        "rd_startup_authority_gate",
        "runtime_safety_guard",
        "schedule_dashboard_after_60",
        "soft_watchdog_loop",
        "start_custom_charge",
        "terminal_panel_manager",
        "zero_current_since",
    }
)

# Frozen inventory: attributes written from inside an install*() function.
INSTALL_ATTRS_WRITTEN = frozenset(
    {
        "MIN_INPUT_VOLTAGE",
        "_build_and_send_dashboard",
        "_build_charge_modes_keyboard",
        "_build_dashboard_keyboard",
        "_charge_modes_text",
        "_charge_notify",
        "_compact_dashboard_caption",
        "_done_storage_restore_installed",
        "_format_stage_progress_line",
        "_hands_off_background_isolation_installed",
        "_hard_stop_charge",
        "_has_manual_off_condition",
        "_mix_action_eligibility_installed",
        "_operator_destructive_guard",
        "_operator_graph_dashboard_installed",
        "_operator_hmi_installed",
        "_operator_home_handler",
        "_operator_managed_stop_confirmations",
        "_operator_managed_stop_installed",
        "_operator_navigation_recovery_installed",
        "_operator_output_truth_installed",
        "_operator_pause_active",
        "_operator_pause_toggle",
        "_rd_autonomous_final_hmi_installed",
        "_rd_ownership_recovery_installed",
        "_refresh_operator_panel",
        "_restore_allows_auto_enable",
        "_send_notify_safe",
        "_soft_watchdog_containment_installed",
        "_soft_watchdog_incident",
        "_v2_bound_manual_middleware",
        "_v2_manual_context_ui_installed",
        "_v2_manual_text_middleware",
        "_v2_production_guardrails_installed",
        "_v2_vin_psu_health_only",
        "charge_controller",
        "controlled_diagnostic_probe",
        "diagnostic_action_journal",
        "handle_ah_input",
        "handle_dialog_mode",
        "log_event",
        "manual_session_manager",
        "physical_test_control",
        "physical_test_control_d062",
        "physical_test_control_d062_delta",
        "physical_test_control_diagnostic",
        "physical_test_control_pb_mode",
        "physical_test_control_programmed_readback_v2",
        "physical_test_control_source_faults",
        "rd_autonomous_mode",
        "rd_control_mode_manager",
        "rd_live_mix_observer",
        "rd_managed_live_adoption",
        "rd_managed_mix_adoption",
        "rd_startup_authority_gate",
        "runtime_safety_guard",
        "schedule_dashboard_after_60",
        "soft_watchdog_loop",
        "start_custom_charge",
        "terminal_panel_manager",
    }
)

# Frozen ownership of critical runtime components: attribute -> writing modules.
CRITICAL_OWNERSHIP = {
    "charge_controller": {"v2_bootstrap.py"},
    "manual_session_manager": {"v2_bootstrap.py"},
    "charge_monitor": {"v2_bootstrap.py"},
    "runtime_safety_guard": {
        "runtime_safety.py",
        "runtime_safety_strict.py",
        "runtime_safety_v2.py",
    },
    "edge_safety_lease": {"runtime_safety_strict.py"},
    "rd_control_mode_manager": {"rd_control_mode.py"},
    "rd_startup_authority_gate": {"rd_startup_authority.py"},
    "rd_autonomous_mode": {"rd_autonomous_mode.py"},
    "rd_managed_live_adoption": {"rd_managed_adoption.py"},
    "rd_managed_mix_adoption": {"rd_managed_mix_adoption.py"},
    "rd_live_mix_observer": {"rd_live_adoption.py"},
    "diagnostic_action_journal": {"diagnostic_persistence.py"},
    "controlled_diagnostic_probe": {"diagnostic_persistence.py"},
    "terminal_panel_manager": {"telegram_panel.py"},
    "physical_test_control": {"physical_test_control.py"},
    "_restore_allows_auto_enable": {"done_storage_restore.py"},
    "_send_notify_safe": {"telegram_panel.py"},
    "_build_dashboard_keyboard": {
        "operator_hmi.py",
        "rd_control_mode.py",
        "rd_hands_off_release.py",
        "rd_live_adoption.py",
        "v2_bootstrap.py",
        "v2_bot_ui.py",
    },
}


def _iter_production_files():
    for path in sorted(REPO_ROOT.rglob("*.py")):
        rel = path.relative_to(REPO_ROOT)
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        yield rel.as_posix(), path


class _NamespaceWriterVisitor(ast.NodeVisitor):
    """Collect ``app.<attr> = ...`` writes and their enclosing function/module."""

    def __init__(self, module: str):
        self.module = module
        self.func_name = "<module>"
        self.writes = []  # (attr, module, func_name)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node)

    def _visit_function(self, node) -> None:
        previous = self.func_name
        self.func_name = node.name
        self.generic_visit(node)
        self.func_name = previous

    def visit_Assign(self, node: ast.Assign) -> None:
        for target in node.targets:
            if (
                isinstance(target, ast.Attribute)
                and isinstance(target.value, ast.Name)
                and target.value.id == "app"
            ):
                self.writes.append((target.attr, self.module, self.func_name))
        self.generic_visit(node)


def scan_namespace_writes():
    """Return (all_app_attrs, install_written_attrs, ownership_map)."""
    app_attrs = set()
    install_attrs = set()
    ownership: dict[str, set[str]] = {}

    for module, path in _iter_production_files():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        visitor = _NamespaceWriterVisitor(module)
        visitor.visit(tree)
        for attr, owner_module, func_name in visitor.writes:
            app_attrs.add(attr)
            ownership.setdefault(attr, set()).add(owner_module)
            if func_name.startswith("install"):
                install_attrs.add(attr)

    return app_attrs, install_attrs, ownership


class RuntimeAppNamespaceContractTests(unittest.TestCase):
    def test_app_namespace_attribute_set_is_frozen(self):
        actual, _, _ = scan_namespace_writes()
        self.assertEqual(
            sorted(actual),
            sorted(APP_ATTRS_WRITTEN),
            "The set of app.<attr> namespace writes changed. This is an explicit "
            "runtime-ownership change: update APP_ATTRS_WRITTEN deliberately.",
        )

    def test_installer_written_attribute_set_is_frozen(self):
        _, actual_install, _ = scan_namespace_writes()
        self.assertEqual(
            sorted(actual_install),
            sorted(INSTALL_ATTRS_WRITTEN),
            "The set of attributes written from inside install*() changed. "
            "Update INSTALL_ATTRS_WRITTEN deliberately.",
        )

    def test_critical_component_ownership_is_frozen(self):
        _, _, ownership = scan_namespace_writes()
        for attr, expected_owners in CRITICAL_OWNERSHIP.items():
            with self.subTest(attr=attr):
                self.assertIn(
                    attr, ownership, f"app.{attr} is no longer written anywhere"
                )
                self.assertEqual(
                    ownership[attr],
                    set(expected_owners),
                    f"Ownership of app.{attr} changed: expected "
                    f"{sorted(expected_owners)}, got "
                    f"{sorted(ownership.get(attr, set()))}",
                )


if __name__ == "__main__":
    unittest.main()
