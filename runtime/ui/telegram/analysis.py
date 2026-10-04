"""Telegram route for the canonical read-only AI analysis screen."""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiogram import F
from aiogram.filters import Command

from runtime.ui.actions import UIAction
from runtime.ui.routing.registry import route_for
from runtime.ui.screens.analysis import build_analysis_screen
from runtime.ui.telegram.renderer import (
    callback_data_for,
    render_screen_markup,
    render_screen_text,
)


ANALYSIS_CALLBACK_DATA = callback_data_for(UIAction.OPEN_ANALYSIS)
HOME_CALLBACK_DATA = callback_data_for(UIAction.OPEN_HOME)


def install_analysis_screen(
    app: Any,
    *,
    analysis_provider: Callable[[], Awaitable[str]],
    home_handler: Callable[[Any], Awaitable[None]],
) -> None:
    """Install AI presentation without importing the historical runtime or AI client."""

    if bool(getattr(app, "_v3_analysis_screen_installed", False)):
        return
    route = route_for(UIAction.OPEN_ANALYSIS)
    if not route.navigation_only:
        raise RuntimeError("analysis UI action must remain navigation-only")

    async def _render_analysis(message: Any) -> None:
        rendered = await analysis_provider()
        screen = build_analysis_screen(rendered)
        await message.answer(
            render_screen_text(screen),
            parse_mode=app.ParseMode.HTML,
            reply_markup=render_screen_markup(screen),
        )

    @app.router.callback_query(F.data == ANALYSIS_CALLBACK_DATA)
    async def _analysis(call: Any) -> None:
        if not await app._check_chat_and_respond(call):
            return
        try:
            await call.answer()
        except Exception:
            pass
        await _render_analysis(call.message)

    @app.router.message(Command("ai"))
    async def _analysis_command(message: Any) -> None:
        if not await app._check_chat_and_respond(message):
            return
        await _render_analysis(message)

    if not bool(getattr(app, "_v3_home_navigation_installed", False)):
        @app.router.callback_query(F.data == HOME_CALLBACK_DATA)
        async def _home(call: Any) -> None:
            await home_handler(call)

        app._v3_home_handler = _home
        app._v3_home_navigation_installed = True

    app._v3_analysis_handler = _analysis
    app._v3_analysis_screen_installed = True


__all__ = [
    "ANALYSIS_CALLBACK_DATA",
    "HOME_CALLBACK_DATA",
    "install_analysis_screen",
]
