"""Telegram command route for canonical statistics help."""

from __future__ import annotations

from typing import Any, Callable

from aiogram.filters import Command

from runtime.ui.screens.stats import build_stats_screen
from runtime.ui.telegram.renderer import render_screen_text


def install_stats_screen(
    app: Any,
    *,
    schedule_refresh: Callable[[int, int], None] | None = None,
) -> None:
    if bool(getattr(app, "_v3_stats_screen_installed", False)):
        return

    @app.router.message(Command("stats"))
    async def _stats(message: Any) -> None:
        if not await app._check_chat_and_respond(message):
            return
        await message.answer(
            render_screen_text(build_stats_screen()),
            parse_mode=app.ParseMode.HTML,
        )

    app._v3_stats_handler = _stats
    app._v3_stats_screen_installed = True


__all__ = ["install_stats_screen"]
