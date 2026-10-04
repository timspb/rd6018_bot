from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import unittest

from application.operator_snapshot_provider import OperatorSnapshotProvider
from runtime.ui.actions import UIAction
from runtime.ui.components.entities import render_entities_body
from runtime.ui.models import EntityStatusItem, EntityStatusView
from runtime.ui.screen import ScreenId
from runtime.ui.screens.entities import build_entities_screen
from runtime.ui.telegram.entities import (
    ENTITIES_CALLBACK_DATA,
    HOME_CALLBACK_DATA,
    install_entities_screen,
)
from runtime.ui.telegram.renderer import render_screen_text
from telegram_panel import _is_workspace_callback


ROOT = Path(__file__).resolve().parents[1]


def _view() -> EntityStatusView:
    return EntityStatusView(
        (
            EntityStatusItem("battery_voltage", 14.5123, "ok", "V", "Battery voltage"),
            EntityStatusItem("current", "unavailable", "unavailable", "A", "Current"),
            EntityStatusItem("switch", None, "error", "", "Output"),
        )
    )


class _Hass:
    async def get_entities_status(self):
        return [
            {
                "key": "battery_voltage",
                "state": 14.5123,
                "status": "ok",
                "unit": "V",
                "friendly_name": "Battery voltage",
            },
            {
                "key": "current",
                "state": "unavailable",
                "status": "unavailable",
                "unit": "A",
                "friendly_name": "Current",
            },
        ]


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
    async def get_entity_statuses(self):
        return _view()


class _App:
    def __init__(self) -> None:
        self.router = _Router()
        self.ParseMode = SimpleNamespace(HTML="HTML")

    async def _check_chat_and_respond(self, _call):
        return True


class V3EntitiesUICutoverTests(unittest.IsolatedAsyncioTestCase):
    async def test_application_provider_maps_hass_rows_to_data_only_view(self):
        app = SimpleNamespace(hass=_Hass())
        provider = OperatorSnapshotProvider(app)
        view = await provider.get_entity_statuses()
        self.assertEqual(len(view.items), 2)
        self.assertEqual(view.items[0].key, "battery_voltage")
        self.assertEqual(view.items[0].status, "ok")
        self.assertEqual(view.items[1].status, "unavailable")

    async def test_canonical_handler_renders_application_view(self):
        app = _App()
        home_calls = []

        async def home(call):
            home_calls.append(call)

        install_entities_screen(app, interface=_Interface(), home_handler=home)
        call = _Call()
        await app._v3_entities_handler(call)

        self.assertEqual(len(call.message.answers), 1)
        text, kwargs = call.message.answers[0]
        self.assertEqual(text, render_screen_text(build_entities_screen(_view())))
        back = kwargs["reply_markup"].inline_keyboard[0][0]
        self.assertEqual(back.callback_data, HOME_CALLBACK_DATA)
        await app._v3_home_handler(call)
        self.assertEqual(home_calls, [call])


class V3EntitiesUIContractTests(unittest.TestCase):
    def test_formatter_preserves_entity_status_semantics(self):
        text = render_entities_body(_view())
        self.assertIn("✅ Доступно: 1/3", text)
        self.assertIn("🟢 <b>battery_voltage</b>: 14.512 V", text)
        self.assertIn("🟡 <b>current</b>: unavailable (unavailable)", text)
        self.assertIn("🔴 <b>switch</b>: error ()", text)

    def test_screen_and_callback_are_canonical(self):
        screen = build_entities_screen(_view())
        self.assertEqual(screen.screen_id, ScreenId.ENTITIES)
        self.assertEqual(screen.buttons[0][0].action, UIAction.OPEN_HOME)
        self.assertEqual(ENTITIES_CALLBACK_DATA, "ui:nav.entities")
        self.assertTrue(_is_workspace_callback(ENTITIES_CALLBACK_DATA))
        self.assertFalse(_is_workspace_callback("entities_status"))

    def test_historical_entities_callback_is_removed(self):
        source = (ROOT / "runtime" / "v2_runtime.py").read_text(encoding="utf-8")
        self.assertNotIn('F.data == "entities_status"', source)
        self.assertNotIn("async def entities_status_handler(", source)

    def test_canonical_entities_tree_has_no_hass_or_historical_import(self):
        for rel in (
            "runtime/ui/components/entities.py",
            "runtime/ui/screens/entities.py",
            "runtime/ui/telegram/entities.py",
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

    def test_composition_installs_entities_after_operator_interface(self):
        source = (ROOT / "bot.py").read_text(encoding="utf-8")
        provider = source.index("_legacy.operator_interface = OperatorSnapshotProvider(_legacy)")
        install = source.index("install_entities_screen(")
        self.assertLess(provider, install)


if __name__ == "__main__":
    unittest.main()
