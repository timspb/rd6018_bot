from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import unittest

from runtime.ui.actions import UIAction
from runtime.ui.screen import ScreenId
from runtime.ui.screens.charge import build_charge_program_screen, charge_button_spec
from runtime.ui.telegram.charge import (
    BATTERIES_CALLBACK_DATA,
    BATTERY_ADD_CALLBACK_DATA,
    CHARGE_CALLBACK_DATA,
    INTERRUPTED_MANUAL_CALLBACK_DATA,
    MANUAL_CALLBACK_DATA,
    PROFILE_CALLBACK_PREFIX,
    install_charge_program_screen,
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


class _App:
    def __init__(self) -> None:
        self.router = _Router()
        self.ParseMode = SimpleNamespace(HTML="HTML")
        self.last_chat_id = 0
        self.last_user_id = 0

    async def _check_chat_and_respond(self, _event):
        return True


class V3ChargeProgramCutoverTests(unittest.TestCase):
    def test_charge_screen_is_declarative_and_preserves_program_choices(self):
        screen = build_charge_program_screen(manual_interrupted=True)
        self.assertEqual(screen.screen_id, ScreenId.CHARGE)
        self.assertEqual(screen.title, "🧭 V2 · программа заряда")
        text = render_screen_text(screen)
        self.assertIn("Normal", text)
        self.assertIn("Recovery", text)
        self.assertIn("Imin→ΔI", text)
        self.assertIn("Vmax→ΔV", text)

        actions = [button.action for row in screen.buttons for button in row]
        self.assertIn(UIAction.SELECT_PROFILE, actions)
        self.assertIn(UIAction.OPEN_BATTERIES, actions)
        self.assertIn(UIAction.OPEN_BATTERY_ADD, actions)
        self.assertIn(UIAction.OPEN_MANUAL, actions)
        self.assertIn(UIAction.OPEN_INTERRUPTED_MANUAL, actions)
        self.assertIn(UIAction.OPEN_OFF_CONDITIONS, actions)
        self.assertIn(UIAction.OPEN_HOME, actions)

        profiles = {
            button.payload[0][1]
            for button in screen.buttons[0]
        }
        self.assertEqual(profiles, {"Ca/Ca", "EFB", "AGM"})

        entry = charge_button_spec()
        self.assertEqual(entry.action, UIAction.OPEN_CHARGE)
        self.assertEqual(entry.target_screen, ScreenId.CHARGE.value)

    def test_charge_screen_hides_interrupted_manual_when_not_available(self):
        screen = build_charge_program_screen(manual_interrupted=False)
        actions = [button.action for row in screen.buttons for button in row]
        self.assertNotIn(UIAction.OPEN_INTERRUPTED_MANUAL, actions)

    def test_canonical_callbacks_are_workspace_and_raw_charge_modes_is_retired(self):
        self.assertTrue(_is_workspace_callback(CHARGE_CALLBACK_DATA))
        self.assertTrue(_is_workspace_callback(BATTERIES_CALLBACK_DATA))
        self.assertTrue(_is_workspace_callback(BATTERY_ADD_CALLBACK_DATA))
        self.assertTrue(_is_workspace_callback(MANUAL_CALLBACK_DATA))
        self.assertTrue(_is_workspace_callback(INTERRUPTED_MANUAL_CALLBACK_DATA))
        profile_data = callback_data_for(
            UIAction.SELECT_PROFILE,
            (("profile", "AGM"),),
        )
        self.assertTrue(profile_data.startswith(PROFILE_CALLBACK_PREFIX + "?"))
        self.assertTrue(_is_workspace_callback(profile_data))
        self.assertFalse(_is_workspace_callback("charge_modes"))

    def test_historical_modes_routes_and_raw_payloads_are_removed(self):
        runtime = (ROOT / "runtime" / "production_runtime.py").read_text(encoding="utf-8")
        self.assertNotIn('Command("modes")', runtime)
        self.assertNotIn('F.data == "charge_modes"', runtime)
        self.assertNotIn("async def cmd_modes(", runtime)
        self.assertNotIn("async def charge_modes_handler(", runtime)

        for rel in (
            "runtime/production_runtime.py",
            "manual_context.py",
            "manual_text.py",
            "production_bootstrap.py",
            "production_bot_ui.py",
            "mix_mode.py",
            "sg_ui.py",
            "ui_polish.py",
        ):
            source = (ROOT / rel).read_text(encoding="utf-8")
            self.assertNotIn('callback_data="charge_modes"', source, rel)

    def test_operator_hmi_uses_canonical_charge_and_battery_callbacks(self):
        source = (ROOT / "operator_hmi.py").read_text(encoding="utf-8")
        self.assertIn(
            'OperatorAction.START_CHARGE: ("⚡ Режимы заряда", CHARGE_CALLBACK_DATA)',
            source,
        )
        self.assertIn(
            'OperatorAction.SELECT_PROFILE: ("🔋 АКБ", BATTERIES_CALLBACK_DATA)',
            source,
        )

    def test_canonical_charge_ui_has_no_historical_or_physical_imports(self):
        for rel in (
            "runtime/ui/screens/charge.py",
            "runtime/ui/telegram/charge.py",
        ):
            source = (ROOT / rel).read_text(encoding="utf-8")
            for forbidden in (
                "runtime.v2_runtime",
                "charge_logic",
                "charge_controller",
                "hass_api",
                "runtime_safety",
                "safe_output",
                "production_bot_ui",
                "manual_context",
                "esphome",
            ):
                self.assertNotIn(forbidden, source, f"{rel}: {forbidden}")

    def test_production_composition_injects_existing_workflow_owners(self):
        source = (ROOT / "bot.py").read_text(encoding="utf-8")
        self.assertIn("install_charge_program_screen(", source)
        for fragment in (
            "profile_selector=app._v2_select_quick_profile",
            "batteries_handler=app._v2_batteries_handler",
            "battery_add_handler=app._v2_battery_add_handler",
            "manual_handler=app._v2_manual_choose_handler",
            "interrupted_manual_handler=app._v2_manual_interrupted_handler",
        ):
            self.assertIn(fragment, source)


class V3ChargeProgramTelegramTests(unittest.IsolatedAsyncioTestCase):
    async def test_command_and_open_callback_render_canonical_screen(self):
        app = _App()
        calls = []
        scheduled = []

        async def profile(call, profile):
            calls.append(("profile", call, profile))

        async def batteries(call):
            calls.append(("batteries", call))

        async def battery_add(call):
            calls.append(("battery_add", call))

        async def manual(call):
            calls.append(("manual", call))

        async def interrupted(call):
            calls.append(("interrupted", call))

        install_charge_program_screen(
            app,
            profile_selector=profile,
            batteries_handler=batteries,
            battery_add_handler=battery_add,
            manual_handler=manual,
            interrupted_manual_handler=interrupted,
            interrupted_manual_provider=lambda: True,
            schedule_refresh=lambda chat, user: scheduled.append((chat, user)),
        )

        message = _Message()
        await app._v3_modes_command_handler(message)
        self.assertIn("программа заряда", message.answers[0][0])
        self.assertEqual(scheduled, [(10, 7)])

        call = _Call(CHARGE_CALLBACK_DATA)
        await app._v3_charge_program_handler(call)
        self.assertIn("программа заряда", call.message.answers[0][0])
        self.assertEqual(app.last_chat_id, 10)
        self.assertEqual(app.last_user_id, 7)

    async def test_profile_and_nested_navigation_delegate_to_injected_workflows(self):
        app = _App()
        calls = []

        async def profile(call, profile):
            calls.append(("profile", profile))

        async def batteries(call):
            calls.append(("batteries", call.data))

        async def battery_add(call):
            calls.append(("battery_add", call.data))

        async def manual(call):
            calls.append(("manual", call.data))

        async def interrupted(call):
            calls.append(("interrupted", call.data))

        install_charge_program_screen(
            app,
            profile_selector=profile,
            batteries_handler=batteries,
            battery_add_handler=battery_add,
            manual_handler=manual,
            interrupted_manual_handler=interrupted,
            interrupted_manual_provider=lambda: True,
        )

        profile_call = _Call(
            callback_data_for(
                UIAction.SELECT_PROFILE,
                (("profile", "EFB"),),
            )
        )
        await app._v3_charge_profile_handler(profile_call)
        self.assertEqual(calls[0], ("profile", "EFB"))

        await app.router.callback_query.handlers[2](_Call(BATTERIES_CALLBACK_DATA))
        await app.router.callback_query.handlers[3](_Call(BATTERY_ADD_CALLBACK_DATA))
        await app.router.callback_query.handlers[4](_Call(MANUAL_CALLBACK_DATA))
        await app.router.callback_query.handlers[5](_Call(INTERRUPTED_MANUAL_CALLBACK_DATA))
        self.assertEqual([row[0] for row in calls[1:]], [
            "batteries",
            "battery_add",
            "manual",
            "interrupted",
        ])


if __name__ == "__main__":
    unittest.main()
