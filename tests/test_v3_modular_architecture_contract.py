"""Architecture contracts for modular V3 and the first legacy-eradication boundary."""

from __future__ import annotations

import ast
from pathlib import Path
import unittest

from runtime.config.variable_spec import ChangeEffect, OverridePolicy, VariableSpec
from runtime.ui.actions import UIAction
from runtime.ui.buttons import ButtonSpec
from runtime.ui.routing.registry import route_for


ROOT = Path(__file__).resolve().parents[1]


class ModularV3ArchitectureContractTests(unittest.TestCase):
    def test_variable_spec_requires_complete_metadata(self) -> None:
        spec = VariableSpec(
            key="ui.example_interval_s",
            default=30.0,
            value_type=float,
            unit="s",
            description="Example interval owned by the UI test module.",
            owner="runtime.ui",
            provenance="architecture contract test",
            override_policy=OverridePolicy.CONFIG_FILE,
            change_effect=ChangeEffect.RESTART_REQUIRED,
            minimum=1.0,
            maximum=300.0,
        )
        self.assertEqual(30.0, spec.default)

        with self.assertRaises(ValueError):
            VariableSpec(
                key="",
                default=1,
                value_type=int,
                unit="s",
                description="missing key",
                owner="runtime.ui",
                provenance="test",
                override_policy=OverridePolicy.CODE_DEFAULT_ONLY,
                change_effect=ChangeEffect.DEPLOY_REQUIRED,
            )

    def test_modular_ui_button_is_declarative(self) -> None:
        button = ButtonSpec(
            button_id="charge.start",
            label="▶ Запустить",
            action=UIAction.START_CHARGE,
            requires_confirmation=True,
        )
        route = route_for(button.action)
        self.assertFalse(route.navigation_only)
        self.assertIsNotNone(route.intent_kind)

    def test_canonical_runtime_ui_has_no_framework_or_hardware_imports(self) -> None:
        forbidden = (
            "aiogram",
            "hass_api",
            "runtime.v2_runtime",
            "charge_logic",
            "charge_controller",
            "safe_output",
            "runtime.physical",
            "esphome",
        )
        violations: list[str] = []
        for path in (ROOT / "runtime" / "ui").rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                module = ""
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    names = [module]
                else:
                    continue
                for name in names:
                    for token in forbidden:
                        if not (name == token or name.startswith(token + ".")):
                            continue
                        if token == "aiogram" and "telegram" in path.parts:
                            continue
                        violations.append(f"{path.relative_to(ROOT)}:{name}")
        self.assertEqual([], violations)

    def test_only_telegram_renderer_layer_constructs_framework_buttons(self) -> None:
        violations: list[str] = []
        renderer_hits: list[str] = []
        for path in (ROOT / "runtime" / "ui").rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            for token in ("InlineKeyboardButton(", "callback_data="):
                if token not in text:
                    continue
                if "telegram" in path.parts:
                    renderer_hits.append(f"{path.relative_to(ROOT)}:{token}")
                else:
                    violations.append(f"{path.relative_to(ROOT)}:{token}")
        self.assertEqual([], violations)
        self.assertTrue(
            any("renderer.py:InlineKeyboardButton(" in item for item in renderer_hits),
            "canonical Telegram renderer must be the explicit framework button boundary",
        )

    def test_capacity_start_has_no_direct_legacy_physical_fallback(self) -> None:
        source = (ROOT / "runtime" / "production_runtime.py").read_text(encoding="utf-8")
        start = source.index("async def handle_ah_input")
        end = source.index("async def handle_dialog_mode", start)
        callback = source[start:end]
        self.assertIn("direct legacy START is retired", callback)
        self.assertIn("await route.submit(intent)", callback)
        for forbidden in (
            "charge_controller.start(",
            "hass.set_ovp(",
            "hass.set_ocp(",
            "hass.set_voltage(",
            "hass.set_current(",
            "hass.turn_on(",
        ):
            self.assertNotIn(forbidden, callback)

    def test_ui_support_default_start_helper_has_no_physical_fallback(self) -> None:
        source = (ROOT / "production_bot_ui.py").read_text(encoding="utf-8")
        start = source.index("async def _start_profile")
        end = source.index("def install_ui_support", start)
        helper = source[start:end]
        self.assertIn("Старый прямой UI→RD запуск отключён", helper)
        for forbidden in (
            "charge_controller.start(",
            "app.hass.set_voltage(",
            "app.hass.set_current(",
            "app.hass.turn_on(",
            "app._apply_phase_protection(",
        ):
            self.assertNotIn(forbidden, helper)

    def test_environment_cannot_reenable_legacy_transition_authority(self) -> None:
        source = (ROOT / "charge_controller.py").read_text(encoding="utf-8")
        self.assertNotIn('os.getenv("V2_AUTHORITATIVE"', source)
        self.assertNotIn('_env_bool("V2_AUTHORITATIVE"', source)
        self.assertNotIn("authoritative:", source)
        self.assertNotIn("_v2_authoritative", source)
        self.assertNotIn("set_v2_authoritative", source)

    def test_retired_runtime_facades_are_removed(self) -> None:
        self.assertFalse((ROOT / "bot_legacy.py").exists())
        self.assertFalse((ROOT / "runtime" / "v2_runtime.py").exists())
        self.assertFalse((ROOT / "v2_startup.py").exists())
        self.assertFalse((ROOT / "application" / "v2_start_runner_adapter.py").exists())
        self.assertFalse((ROOT / "application" / "legacy_actuator_boundary.py").exists())
        self.assertFalse((ROOT / "v1_ui_compat.py").exists())
        self.assertFalse((ROOT / "application" / "v2_identity_bridge.py").exists())
        self.assertFalse((ROOT / "application" / "operator_snapshot_shadow.py").exists())
        self.assertFalse((ROOT / "runtime" / "ui" / "legacy_shadow").exists())
        self.assertFalse((ROOT / "application" / "active_start_bridge.py").exists())
        self.assertFalse((ROOT / "application" / "operator_feedback.py").exists())
        self.assertFalse((ROOT / "application" / "telegram_operator_feedback.py").exists())

    def test_modular_contract_and_debt_ledger_are_present(self) -> None:
        for name in (
            "V3_MODULAR_ARCHITECTURE.md",
            "V3_UI_MODULAR_ARCHITECTURE.md",
            "V3_LEGACY_ERADICATION_LEDGER.md",
        ):
            self.assertTrue((ROOT / "docs" / name).is_file(), name)


if __name__ == "__main__":
    unittest.main()
