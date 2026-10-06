"""Telegram command route for canonical operator help."""

from __future__ import annotations

from typing import Any, Callable

from aiogram.filters import Command

from runtime.ui.screens.help import build_help_screen
from runtime.ui.telegram.renderer import render_screen_text


def install_help_screen(
    app: Any,
    *,
    schedule_refresh: Callable[[int, int], None] | None = None,
) -> None:
    if bool(getattr(app, "_v3_help_screen_installed", False)):
        return

    @app.router.message(Command("help"))
    async def _help(message: Any) -> None:
        if not await app._check_chat_and_respond(message):
            return
        await message.answer(
            render_screen_text(build_help_screen()),
            parse_mode=app.ParseMode.HTML,
        )
        if schedule_refresh is not None:
            schedule_refresh(
                int(message.chat.id),
                int(message.from_user.id if message.from_user else 0),
            )

    app._v3_help_handler = _help
    app._v3_help_screen_installed = True


__all__ = ["install_help_screen"]
