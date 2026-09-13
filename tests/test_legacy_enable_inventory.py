"""PR00 characterization: legacy Output-enable inventory.

Freezes every production call site that can change RD6018 Output state
(``turn_on`` / ``turn_off`` / ``safe_enable_output``), together with its owning
module and function. This is the mechanical "enable inventory" required before any
runtime ownership extraction: if a new direct actuator bypass appears, or an
existing one moves, this test fails and forces an explicit review.

READ-ONLY characterization: no production module is imported or modified; the
inventory is derived by parsing source with ``ast``.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

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

_ENABLE_METHODS = ("turn_on", "turn_off", "safe_enable_output")

# Frozen inventory: (module, function, "owner.method") for every production call.
ENABLE_CALLS = frozenset(
    {
        # D-STARTUP-3: after explicit MANAGED reconciliation, deferred restore may
        # converge physical Output through the final composed HassClient surface.
        # These are reviewed guarded call-sites, not raw actuator bypasses.
        ("bot.py", "_replay_deferred_startup_restore", "_legacy.hass.turn_off"),
        ("bot.py", "_replay_deferred_startup_restore", "_legacy.hass.turn_on"),
        ("bot_legacy.py", "_hard_stop_charge", "hass.turn_off"),
        ("bot_legacy.py", "_operator_pause_toggle", "hass.turn_off"),
        ("bot_legacy.py", "_operator_pause_toggle", "hass.turn_on"),
        ("bot_legacy.py", "data_logger", "hass.turn_off"),
        ("bot_legacy.py", "data_logger", "hass.turn_on"),
        ("bot_legacy.py", "handle_ah_input", "hass.turn_on"),
        ("bot_legacy.py", "main", "hass.turn_off"),
        ("bot_legacy.py", "main", "hass.turn_on"),
        ("bot_legacy.py", "power_toggle_handler", "hass.turn_off"),
        ("bot_legacy.py", "power_toggle_handler", "hass.turn_on"),
        ("bot_legacy.py", "start_custom_charge", "hass.turn_on"),
        ("diagnostic_persistence.py", "recover_diagnostic_persistence", "app.hass.turn_off"),
        ("diagnostic_probe.py", "_restore_or_off", "self.hass.turn_off"),
        ("manual_mode.py", "_enter_cooling", "self.app.hass.turn_off"),
        ("manual_mode.py", "_resume_after_cooling", "self.app.hass.safe_enable_output"),
        ("manual_mode.py", "_run", "self.app.hass.turn_off"),
        ("manual_mode.py", "start", "self.app.hass.safe_enable_output"),
        ("manual_mode.py", "stop", "self.app.hass.turn_off"),
        ("manual_runtime_v2.py", "_contain_enable_exception", "self.app.hass.turn_off"),
        ("manual_runtime_v2.py", "_run", "self.app.hass.turn_off"),
        ("manual_runtime_v2.py", "stop", "self.app.hass.turn_off"),
        ("rd_managed_adoption.py", "_verified_off", "self.app.hass.turn_off"),
        ("rd_managed_mix.py", "force_verified_off", "self.app.hass.turn_off"),
        ("recipe_output.py", "enable_authorized_recipe_target", "adapter.safe_enable_output"),
        ("recovery_orchestrator.py", "_confirm_output_off", "self.output_adapter.turn_off"),
        ("runtime_safety_strict.py", "turn_off", "super().turn_off"),
        ("runtime_safety_strict.py", "turn_on", "super().turn_on"),
        ("runtime_safety_v2.py", "turn_on", "super().turn_off"),
        ("runtime_safety_v2.py", "turn_on", "super().turn_on"),
        ("safe_output.py", "_force_off", "self.adapter.turn_off"),
        ("safe_output.py", "enable", "self.adapter.turn_on"),
        ("v2_bot_ui.py", "_start_profile", "app.hass.turn_on"),
        ("v2_mix_mode.py", "_confirm_failed_start_is_off", "app.hass.turn_off"),
        ("v2_mix_mode.py", "start_mix_transactional", "app.hass.safe_enable_output"),
        ("v2_startup.py", "_confirm_failed_start_is_off", "app.hass.turn_off"),
        ("v2_startup.py", "start_profile_transactional", "app.hass.safe_enable_output"),
    }
)


def _iter_production_files():
    for path in sorted(REPO_ROOT.rglob("*.py")):
        rel = path.relative_to(REPO_ROOT)
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        yield rel.as_posix(), path


def scan_enable_calls():
    """Return the set of (module, function, "owner.method") output-enable call sites."""
    calls = set()
    for module, path in _iter_production_files():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for sub in ast.walk(node):
                if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute):
                    if sub.func.attr in _ENABLE_METHODS:
                        base = ast.unparse(sub.func.value)
                        calls.add((module, node.name, f"{base}.{sub.func.attr}"))
    return calls


class LegacyEnableInventoryTests(unittest.TestCase):
    def test_enable_call_inventory_is_frozen(self):
        actual = scan_enable_calls()
        missing = sorted(ENABLE_CALLS - actual)
        added = sorted(actual - ENABLE_CALLS)
        self.assertEqual(
            added,
            [],
            "New production Output-enable call sites appeared (possible actuator "
            "bypass). Review and update ENABLE_CALLS deliberately: " + repr(added),
        )
        self.assertEqual(
            missing,
            [],
            "Production Output-enable call sites disappeared/moved. Review and "
            "update ENABLE_CALLS deliberately: " + repr(missing),
        )

    def test_legacy_direct_switch_calls_are_inventoried(self):
        # bot_legacy.py is the primary source of direct (non safe_enable_output)
        # Output manipulation; its inventory must remain explicit.
        legacy = {c for c in ENABLE_CALLS if c[0] == "bot_legacy.py"}
        self.assertTrue(
            legacy,
            "bot_legacy.py direct Output calls must remain inventoried before extraction",
        )
        self.assertTrue(
            any(kind.endswith(".turn_on") for _, _, kind in legacy),
            "bot_legacy.py must still declare its direct Output ON entrypoints",
        )


if __name__ == "__main__":
    unittest.main()
