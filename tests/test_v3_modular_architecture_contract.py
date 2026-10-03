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
            if "legacy_shadow" in path.parts:
                continue
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
                    if any(name == token or name.startswith(token + ".") for token in forbidden):
                        violations.append(f"{path.relative_to(ROOT)}:{name}")
        self.assertEqual([], violations)

    def test_canonical_runtime_ui_does_not_construct_telegram_buttons(self) -> None:
        violations: list[str] = []
        for path in (ROOT / "runtime" / "ui").rglob("*.py"):
            if "legacy_shadow" in path.parts:
                continue
            text = path.read_text(encoding="utf-8")
            for token in ("InlineKeyboardButton(", "callback_data="):
                if token in text:
                    violations.append(f"{path.relative_to(ROOT)}:{token}")
        self.assertEqual([], violations)

    def test_capacity_start_has_no_direct_legacy_physical_fallback(self) -> None:
        source = (ROOT / "runtime" / "v2_runtime.py").read_text(encoding="utf-8")
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

    def test_environment_cannot_reenable_legacy_transition_authority(self) -> None:
        source = (ROOT / "charge_controller_v2.py").read_text(encoding="utf-8")
        self.assertNotIn('os.getenv("V2_AUTHORITATIVE"', source)
        self.assertNotIn('_env_bool("V2_AUTHORITATIVE"', source)
        self.assertIn(
            "self._v2_authoritative = True if authoritative is None else bool(authoritative)",
            source,
        )

    def test_bot_legacy_is_not_an_executable_runtime(self) -> None:
        source = (ROOT / "bot_legacy.py").read_text(encoding="utf-8")
        self.assertNotIn("asyncio.run(_runtime.main())", source)
        self.assertIn("direct execution is retired", source)
        self.assertLess(
            source.index('if __name__ == "__main__":'),
            source.index("from runtime import v2_runtime as _runtime"),
        )

    def test_modular_contract_and_debt_ledger_are_present(self) -> None:
        for name in (
            "V3_MODULAR_ARCHITECTURE.md",
            "V3_UI_MODULAR_ARCHITECTURE.md",
            "V3_LEGACY_ERADICATION_LEDGER.md",
        ):
            self.assertTrue((ROOT / "docs" / name).is_file(), name)


if __name__ == "__main__":
    unittest.main()
