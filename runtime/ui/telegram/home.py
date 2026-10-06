"""Canonical Telegram home command route."""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from aiogram.filters import Command


logger = logging.getLogger("rd6018.ui")


def install_home_command(
    app: Any,
    *,
    render_home: Callable[..., Awaitable[int]],
) -> None:
    """Install /start without historical controller or physical dependencies."""

    if bool(getattr(app, "_v3_home_command_installed", False)):
        return

    @app.router.message(Command("start"))
    async def _home_command(message: Any) -> None:
        if not await app._check_chat_and_respond(message):
            return

        user_id = message.from_user.id if message.from_user else 0
        chat_id = int(message.chat.id)
        app.last_chat_id = chat_id
        app.last_user_id = user_id
        logger.info("Command /start from %s", user_id)

        old_id = app.user_dashboard.get(user_id) if user_id else app.chat_dashboard.get(chat_id)
        if old_id:
            try:
                await app.bot.delete_message(chat_id, old_id)
            except Exception:
                pass

        msg_id = await render_home(
            chat_id=chat_id,
            user_id=user_id,
            old_msg_id=None,
            anchor_msg_id=None,
        )
        if user_id:
            app.user_dashboard[user_id] = int(msg_id)
        app.chat_dashboard[chat_id] = int(msg_id)

    app._v3_home_command_handler = _home_command
    app._v3_home_command_installed = True


__all__ = ["install_home_command"]
