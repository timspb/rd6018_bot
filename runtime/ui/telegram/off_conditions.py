"""Telegram routes for canonical operator OFF-condition UI."""

from __future__ import annotations

from typing import Any, Callable

from aiogram import F
from aiogram.filters import Command

from application.intents import OperatorIntent, OperatorIntentKind
from runtime.ui.actions import UIAction
from runtime.ui.routing.registry import route_for
from runtime.ui.screens.off_conditions import build_off_conditions_screen
from runtime.ui.telegram.renderer import (
    callback_data_for,
    decode_callback_data,
    render_screen_markup,
    render_screen_text,
)


OFF_CALLBACK_DATA = callback_data_for(UIAction.OPEN_OFF_CONDITIONS)
OFF_PRESET_PREFIX = callback_data_for(UIAction.SET_OFF_PRESET)
HOME_CALLBACK_DATA = callback_data_for(UIAction.OPEN_HOME)


def install_off_conditions_screen(
    app: Any,
    *,
    interface: Any,
    status_provider: Callable[[], str],
) -> None:
    """Install OFF-condition presentation without importing historical owners."""

    if bool(getattr(app, "_v3_off_conditions_installed", False)):
        return
    if not route_for(UIAction.OPEN_OFF_CONDITIONS).navigation_only:
        raise RuntimeError("OFF-condition screen must remain navigation-only")
    preset_route = route_for(UIAction.SET_OFF_PRESET)
    if preset_route.intent_kind is not OperatorIntentKind.SET_OFF_CONDITION:
        raise RuntimeError("OFF preset must route through SET_OFF_CONDITION intent")

    async def render(event: Any) -> None:
        screen = build_off_conditions_screen(status_provider())
        message = event.message if getattr(event, "message", None) is not None else event
        await message.answer(
            render_screen_text(screen),
            parse_mode=app.ParseMode.HTML,
            reply_markup=render_screen_markup(screen),
        )

    @app.router.message(Command("off"))
    async def _off_command(message: Any) -> None:
        if not await app._check_chat_and_respond(message):
            return
        await render(message)

    @app.router.callback_query(F.data == OFF_CALLBACK_DATA)
    async def _off_open(call: Any) -> None:
        if not await app._check_chat_and_respond(call):
            return
        await call.answer()
        await render(call)

    @app.router.callback_query(F.data.startswith(OFF_PRESET_PREFIX + "?"))
    async def _off_preset(call: Any) -> None:
        if not await app._check_chat_and_respond(call):
            return
        try:
            action, payload = decode_callback_data(str(call.data or ""))
        except ValueError:
            await call.answer("Некорректный preset", show_alert=True)
            return
        if action is not UIAction.SET_OFF_PRESET:
            await call.answer("Некорректный preset", show_alert=True)
            return
        preset = str(payload.get("preset") or "")
        user = str(getattr(getattr(call, "from_user", None), "id", "0"))
        result = await interface.submit_intent(
            OperatorIntent(
                OperatorIntentKind.SET_OFF_CONDITION,
                "telegram",
                user,
                {"preset": preset},
            )
        )
        status = getattr(result, "status", "")
        status_value = str(getattr(status, "value", status))
        if status_value == "rejected":
            await call.answer("Preset недоступен", show_alert=True)
            return
        await call.answer()
        detail = str(getattr(result, "reason", "") or "")
        if detail:
            await call.message.answer(detail, parse_mode=app.ParseMode.HTML)
        await render(call)

    app._v3_off_command_handler = _off_command
    app._v3_off_conditions_handler = _off_open
    app._v3_off_preset_handler = _off_preset
    app._v3_off_conditions_installed = True


__all__ = [
    "HOME_CALLBACK_DATA",
    "OFF_CALLBACK_DATA",
    "OFF_PRESET_PREFIX",
    "install_off_conditions_screen",
]
