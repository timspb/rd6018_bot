from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
import unittest

from application.operator_actions import OperatorAction, OperatorActionSpec, OperatorActionsView
from application.operator_views import OperatorDetailsView
from operator_hmi import _keyboard_from_actions, render_operator_details_view
from runtime.ui.actions import UIAction
from runtime.ui.screen import ScreenId
from runtime.ui.screens.details import (
    build_operator_details_screen,
    operator_details_button_spec,
)
from runtime.ui.telegram.details import (
    DETAILS_CALLBACK_DATA,
    HOME_CALLBACK_DATA,
    install_operator_details_screen,
)
from runtime.ui.telegram.renderer import render_screen_text


ROOT = Path(__file__).resolve().parents[1]


def _view() -> OperatorDetailsView:
    return OperatorDetailsView(
        process_state="running",
        authority="auto",
        output_on=True,
        regulator="CV",
        battery_label="EFB 70Ah",
        battery_voltage_v=14.51,
        current_a=1.23,
        battery_temp_c=25.5,
        psu_temp_c=41.0,
        target_voltage_v=14.8,
        current_limit_a=2.1,
        safety="OK",
        stage="Main Charge",
        battery_type="EFB",
        capacity_ah=70.0,
        stage_time="01:23",
        total_time="02:34",
        remaining_time="03:45",
        delivered_ah=4.56,
        input_voltage_v=60.1,
        uptime="1d 02:03",
    )


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
        self.callback_query = _RouterGroup()


class _Message:
    def __init__(self) -> None:
        self.answers = []

    async def answer(self, text, **kwargs):
        self.answers.append((text, kwargs))


class _Call:
    def __init__(self) -> None:
        self.from_user = SimpleNamespace(id=7)
        self.message = _Message()
        self.answers = []

    async def answer(self, *args, **kwargs):
        self.answers.append((args, kwargs))


class _Interface:
    async def get_operator_details(self):
        return _view()


class _App:
    def __init__(self) -> None:
        self.router = _Router()
        self.ParseMode = SimpleNamespace(HTML="HTML")

    async def _check_chat_and_respond(self, _call):
        return True


class V3OperatorDetailsUICutoverTests(unittest.TestCase):
    def test_canonical_screen_preserves_existing_details_text(self):
        screen = build_operator_details_screen(_view())
        self.assertEqual(screen.screen_id, ScreenId.DIAGNOSTICS)
        self.assertEqual(screen.title, "📋 Информация для оператора")
        self.assertEqual(render_screen_text(screen), render_operator_details_view(_view()))
        self.assertEqual(screen.buttons[0][0].action, UIAction.OPEN_HOME)
        self.assertEqual(HOME_CALLBACK_DATA, "ui:nav.home")

    def test_details_button_is_declarative(self):
        spec = operator_details_button_spec()
        self.assertEqual(spec.action, UIAction.OPEN_DIAGNOSTICS)
        self.assertEqual(spec.target_screen, ScreenId.DIAGNOSTICS.value)
        self.assertEqual(DETAILS_CALLBACK_DATA, "ui:nav.diagnostics")

    def test_operator_hmi_maps_details_capability_to_canonical_callback(self):
        import inspect

        source = inspect.getsource(_keyboard_from_actions)
        self.assertIn(
            'OperatorAction.SHOW_DIAGNOSTICS: ("ℹ Подробнее", DETAILS_CALLBACK_DATA)',
            source,
        )
        self.assertNotIn('"operator_details"', source)

    def test_historical_operator_details_callback_is_removed(self):
        source = (ROOT / "operator_hmi.py").read_text(encoding="utf-8")
        self.assertNotIn('F.data == "operator_details"', source)
        self.assertNotIn("async def _operator_details(", source)

    def test_composition_installs_details_after_operator_interface(self):
        source = (ROOT / "bot.py").read_text(encoding="utf-8")
        provider = source.index("_legacy.operator_interface = OperatorSnapshotProvider(_legacy)")
        install = source.index("install_operator_details_screen(")
        self.assertLess(provider, install)
        self.assertIn("interface=_legacy.operator_interface", source)

    def test_canonical_details_tree_has_no_historical_import(self):
        for rel in (
            "runtime/ui/components/details.py",
            "runtime/ui/screens/details.py",
            "runtime/ui/telegram/details.py",
        ):
            source = (ROOT / rel).read_text(encoding="utf-8")
            for forbidden in (
                "runtime.v2_runtime",
                "charge_logic",
                "hass_api",
                "operator_hmi",
                "runtime_safety",
                "safe_output",
            ):
                self.assertNotIn(forbidden, source, f"{rel}: {forbidden}")


class V3OperatorDetailsTelegramRouteTests(unittest.IsolatedAsyncioTestCase):
    async def test_details_handler_uses_application_view_and_canonical_markup(self):
        app = _App()
        home_calls = []

        async def home(call):
            home_calls.append(call)

        install_operator_details_screen(
            app,
            interface=_Interface(),
            home_handler=home,
        )
        call = _Call()
        await app._v3_operator_details_handler(call)

        self.assertEqual(len(call.message.answers), 1)
        text, kwargs = call.message.answers[0]
        self.assertEqual(text, render_operator_details_view(_view()))
        back = kwargs["reply_markup"].inline_keyboard[0][0]
        self.assertEqual(back.callback_data, HOME_CALLBACK_DATA)

        await app._v3_home_handler(call)
        self.assertEqual(home_calls, [call])


if __name__ == "__main__":
    unittest.main()
