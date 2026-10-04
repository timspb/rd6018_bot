"""Telegram routes for canonical charge-program selection."""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiogram import F
from aiogram.filters import Command

from application.intents import OperatorIntentKind
from runtime.ui.actions import UIAction
from runtime.ui.routing.registry import route_for
from runtime.ui.screens.charge import build_charge_program_screen
from runtime.ui.telegram.renderer import (
    callback_data_for,
    decode_callback_data,
    render_screen_markup,
    render_screen_text,
)


CHARGE_CALLBACK_DATA = callback_data_for(UIAction.OPEN_CHARGE)
PROFILE_CALLBACK_PREFIX = callback_data_for(UIAction.SELECT_PROFILE)
BATTERIES_CALLBACK_DATA = callback_data_for(UIAction.OPEN_BATTERIES)
BATTERY_ADD_CALLBACK_DATA = callback_data_for(UIAction.OPEN_BATTERY_ADD)
MANUAL_CALLBACK_DATA = callback_data_for(UIAction.OPEN_MANUAL)
INTERRUPTED_MANUAL_CALLBACK_DATA = callback_data_for(UIAction.OPEN_INTERRUPTED_MANUAL)


def install_charge_program_screen(
    app: Any,
    *,
    profile_selector: Callable[[Any, str], Awaitable[None]],
    batteries_handler: Callable[[Any], Awaitable[None]],
    battery_add_handler: Callable[[Any], Awaitable[None]],
    manual_handler: Callable[[Any], Awaitable[None]],
    interrupted_manual_handler: Callable[[Any], Awaitable[None]] | None = None,
    interrupted_manual_provider: Callable[[], bool] | None = None,
    schedule_refresh: Callable[[int, int], None] | None = None,
) -> None:
    """Install canonical charge menu while preserving existing workflow owners."""

    if bool(getattr(app, "_v3_charge_program_installed", False)):
        return
    if not route_for(UIAction.OPEN_CHARGE).navigation_only:
        raise RuntimeError("charge-program screen must remain navigation-only")
    profile_route = route_for(UIAction.SELECT_PROFILE)
    if profile_route.intent_kind is not OperatorIntentKind.SELECT_CHARGE_PROFILE:
        raise RuntimeError("profile selection must route through SELECT_CHARGE_PROFILE")

    def manual_interrupted() -> bool:
        if interrupted_manual_provider is None:
            return False
        try:
            return bool(interrupted_manual_provider())
        except Exception:
            return False

    async def render(event: Any, *, schedule: bool = False) -> None:
        message = event.message if getattr(event, "message", None) is not None else event
        user = getattr(event, "from_user", None)
        user_id = int(getattr(user, "id", 0) or 0)
        chat_id = int(message.chat.id)
        app.last_chat_id = chat_id
        app.last_user_id = user_id
        screen = build_charge_program_screen(
            manual_interrupted=manual_interrupted(),
        )
        await message.answer(
            render_screen_text(screen),
            parse_mode=app.ParseMode.HTML,
            reply_markup=render_screen_markup(screen),
        )
        if schedule and schedule_refresh is not None:
            schedule_refresh(chat_id, user_id)

    @app.router.message(Command("modes"))
    async def _modes_command(message: Any) -> None:
        if not await app._check_chat_and_respond(message):
            return
        await render(message, schedule=True)

    @app.router.callback_query(F.data == CHARGE_CALLBACK_DATA)
    async def _charge_open(call: Any) -> None:
        if not await app._check_chat_and_respond(call):
            return
        await call.answer()
        await render(call)

    @app.router.callback_query(F.data.startswith(PROFILE_CALLBACK_PREFIX + "?"))
    async def _profile(call: Any) -> None:
        try:
            action, payload = decode_callback_data(str(call.data or ""))
        except ValueError:
            await call.answer("Некорректный профиль", show_alert=True)
            return
        if action is not UIAction.SELECT_PROFILE:
            await call.answer("Некорректный профиль", show_alert=True)
            return
        profile = str(payload.get("profile") or "")
        await profile_selector(call, profile)

    @app.router.callback_query(F.data == BATTERIES_CALLBACK_DATA)
    async def _batteries(call: Any) -> None:
        await batteries_handler(call)

    @app.router.callback_query(F.data == BATTERY_ADD_CALLBACK_DATA)
    async def _battery_add(call: Any) -> None:
        await battery_add_handler(call)

    @app.router.callback_query(F.data == MANUAL_CALLBACK_DATA)
    async def _manual(call: Any) -> None:
        await manual_handler(call)

    @app.router.callback_query(F.data == INTERRUPTED_MANUAL_CALLBACK_DATA)
    async def _manual_interrupted(call: Any) -> None:
        if interrupted_manual_handler is None or not manual_interrupted():
            await call.answer("Прерванной Manual-сессии больше нет", show_alert=True)
            return
        await interrupted_manual_handler(call)

    app._v3_modes_command_handler = _modes_command
    app._v3_charge_program_handler = _charge_open
    app._v3_charge_profile_handler = _profile
    app._v3_charge_program_installed = True


__all__ = [
    "BATTERIES_CALLBACK_DATA",
    "BATTERY_ADD_CALLBACK_DATA",
    "CHARGE_CALLBACK_DATA",
    "INTERRUPTED_MANUAL_CALLBACK_DATA",
    "MANUAL_CALLBACK_DATA",
    "PROFILE_CALLBACK_PREFIX",
    "install_charge_program_screen",
]
