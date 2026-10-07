from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import unittest

from application.intents import OperatorIntent, OperatorIntentKind
from application.off_condition_command import OffConditionCommandHandler
from runtime.ui.actions import UIAction
from runtime.ui.commands.models import CommandResult, CommandStatus
from runtime.ui.screen import ScreenId
from runtime.ui.screens.off_conditions import (
    build_off_conditions_screen,
    off_conditions_button_spec,
)
from runtime.ui.telegram.off_conditions import (
    HOME_CALLBACK_DATA,
    OFF_CALLBACK_DATA,
    OFF_PRESET_PREFIX,
    install_off_conditions_screen,
)
from runtime.ui.telegram.renderer import callback_data_for, render_screen_text
from telegram_panel import _is_workspace_callback


ROOT = Path(__file__).resolve().parents[1]


class _RouterGroup:
    def __init__(self) -> None:
        self.handlers = []

    def __call__(self, _filter):
        def decorate(func):
            self.handlers.append(func)
            return func
        return decorate


class _Router:
    def __init__(self) -> None:
        self.message = _RouterGroup()
        self.callback_query = _RouterGroup()


class _Message:
    def __init__(self) -> None:
        self.chat = SimpleNamespace(id=10)
        self.from_user = SimpleNamespace(id=7)
        self.answers = []

    async def answer(self, text, **kwargs):
        self.answers.append((text, kwargs))
        return SimpleNamespace(message_id=99)


class _Call:
    def __init__(self, data: str) -> None:
        self.data = data
        self.from_user = SimpleNamespace(id=7)
        self.message = _Message()
        self.answers = []

    async def answer(self, *args, **kwargs):
        self.answers.append((args, kwargs))


class _Interface:
    def __init__(self) -> None:
        self.intents = []

    async def submit_intent(self, intent):
        self.intents.append(intent)
        return CommandResult(CommandStatus.ACCEPTED, "preset applied")


class _App:
    def __init__(self) -> None:
        self.router = _Router()
        self.ParseMode = SimpleNamespace(HTML="HTML")

    async def _check_chat_and_respond(self, _event):
        return True


class V3OffConditionsCutoverTests(unittest.TestCase):
    def test_screen_is_declarative_and_preserves_operator_copy(self):
        screen = build_off_conditions_screen("⏹ OFF: I≤0.30A")
        self.assertEqual(screen.screen_id, ScreenId.OFF_CONDITIONS)
        text = render_screen_text(screen)
        self.assertIn("Off по условию", text)
        self.assertIn("OFF: I≤0.30A", text)
        self.assertIn("off I&lt;=1.23", text)
        self.assertEqual(screen.buttons[-1][0].action, UIAction.OPEN_HOME)
        self.assertEqual(HOME_CALLBACK_DATA, "ui:nav.home")

        entry = off_conditions_button_spec()
        self.assertEqual(entry.action, UIAction.OPEN_OFF_CONDITIONS)
        self.assertEqual(entry.target_screen, ScreenId.OFF_CONDITIONS.value)

    def test_preset_buttons_encode_canonical_payload(self):
        screen = build_off_conditions_screen()
        presets = {
            button.payload[0][1]
            for row in screen.buttons[:-1]
            for button in row
        }
        self.assertEqual(presets, {"time_2h", "i_le_030", "v_ge_162", "clear"})
        data = callback_data_for(
            UIAction.SET_OFF_PRESET,
            (("preset", "time_2h"),),
        )
        self.assertTrue(data.startswith(OFF_PRESET_PREFIX + "?"))
        self.assertTrue(_is_workspace_callback(data))
        self.assertTrue(_is_workspace_callback(OFF_CALLBACK_DATA))
        self.assertFalse(_is_workspace_callback("menu_off"))

    def test_historical_off_routes_and_raw_callbacks_are_removed(self):
        runtime = (ROOT / "runtime" / "production_runtime.py").read_text(encoding="utf-8")
        bootstrap = (ROOT / "production_bootstrap.py").read_text(encoding="utf-8")

        self.assertNotIn('Command("off")', runtime)
        self.assertNotIn('F.data == "menu_off"', runtime)
        self.assertNotIn('F.data.startswith("off_preset_")', runtime)
        self.assertNotIn("async def cmd_off(", runtime)
        self.assertNotIn("async def menu_off_handler(", runtime)
        self.assertNotIn("async def off_preset_handler(", runtime)
        self.assertNotIn("def _build_off_menu_keyboard(", runtime)
        self.assertIn("def _apply_manual_off_preset(", runtime)

        for source in (runtime, bootstrap):
            self.assertNotIn('callback_data="menu_off"', source)
            self.assertIn("OFF_CALLBACK_DATA", source)

    def test_canonical_off_ui_has_no_historical_or_physical_imports(self):
        for rel in (
            "runtime/ui/screens/off_conditions.py",
            "runtime/ui/telegram/off_conditions.py",
        ):
            source = (ROOT / rel).read_text(encoding="utf-8")
            for forbidden in (
                "runtime.v2_runtime",
                "charge_logic",
                "charge_controller",
                "hass_api",
                "runtime_safety",
                "safe_output",
                "esphome",
            ):
                self.assertNotIn(forbidden, source, f"{rel}: {forbidden}")

    def test_production_composition_installs_off_screen_after_operator_interface(self):
        source = (ROOT / "bot.py").read_text(encoding="utf-8")
        provider = source.index("operator_interface = OperatorSnapshotProvider(")
        install = source.index("install_off_conditions_screen(")
        self.assertLess(provider, install)
        self.assertIn("operator_read_source = OperatorReadSource(_legacy)", source)
        self.assertIn("interface=operator_interface", source)
        self.assertNotIn("OperatorSnapshotProvider(_legacy)", source)
        self.assertIn("status_provider=_legacy._format_manual_off_for_dashboard", source)

    def test_application_handler_validates_and_routes_preset(self):
        calls = []
        app = SimpleNamespace(
            _apply_manual_off_preset=lambda preset: calls.append(preset) or f"ok:{preset}"
        )
        handler = OffConditionCommandHandler(app)
        accepted = handler.route(
            OperatorIntent(
                OperatorIntentKind.SET_OFF_CONDITION,
                "test",
                "7",
                {"preset": "clear"},
            )
        )
        self.assertEqual(accepted.status, CommandStatus.ACCEPTED)
        self.assertEqual(calls, ["clear"])

        rejected = handler.route(
            OperatorIntent(
                OperatorIntentKind.SET_OFF_CONDITION,
                "test",
                "7",
                {"preset": "unknown"},
            )
        )
        self.assertEqual(rejected.status, CommandStatus.REJECTED)
        self.assertEqual(calls, ["clear"])


class V3OffConditionsTelegramTests(unittest.IsolatedAsyncioTestCase):
    async def test_command_and_open_callback_render_same_screen(self):
        app = _App()
        interface = _Interface()
        install_off_conditions_screen(
            app,
            interface=interface,
            status_provider=lambda: "⏹ OFF: I≤0.30A",
        )

        command_message = _Message()
        await app._v3_off_command_handler(command_message)
        self.assertIn("OFF: I≤0.30A", command_message.answers[0][0])

        call = _Call(OFF_CALLBACK_DATA)
        await app._v3_off_conditions_handler(call)
        self.assertIn("OFF: I≤0.30A", call.message.answers[0][0])

    async def test_preset_callback_routes_through_application_intent_and_rerenders(self):
        app = _App()
        interface = _Interface()
        install_off_conditions_screen(
            app,
            interface=interface,
            status_provider=lambda: "",
        )
        data = callback_data_for(
            UIAction.SET_OFF_PRESET,
            (("preset", "time_2h"),),
        )
        call = _Call(data)
        await app._v3_off_preset_handler(call)

        self.assertEqual(len(interface.intents), 1)
        intent = interface.intents[0]
        self.assertEqual(intent.kind, OperatorIntentKind.SET_OFF_CONDITION)
        self.assertEqual(intent.parameters["preset"], "time_2h")
        self.assertEqual(call.message.answers[0][0], "preset applied")
        self.assertIn("Off по условию", call.message.answers[1][0])


if __name__ == "__main__":
    unittest.main()
