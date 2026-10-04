"""Telegram route for the canonical journal screen."""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiogram import F

from runtime.ui.actions import UIAction
from runtime.ui.routing.registry import route_for
from runtime.ui.screens.journal import build_journal_screen
from runtime.ui.telegram.renderer import (
    callback_data_for,
    render_screen_markup,
    render_screen_text,
)


JOURNAL_CALLBACK_DATA = callback_data_for(UIAction.OPEN_JOURNAL)
HOME_CALLBACK_DATA = callback_data_for(UIAction.OPEN_HOME)


def install_journal_screen(
    app: Any,
    *,
    interface: Any,
    home_handler: Callable[[Any], Awaitable[None]],
    retire_graph_tracking: Callable[[int, int, int], None] | None = None,
) -> None:
    """Install the migrated journal route without importing historical owners."""

    if bool(getattr(app, "_v3_journal_screen_installed", False)):
        return
    route = route_for(UIAction.OPEN_JOURNAL)
    if not route.navigation_only:
        raise RuntimeError("journal UI action must remain navigation-only")

    @app.router.callback_query(F.data == JOURNAL_CALLBACK_DATA)
    async def _journal(call: Any) -> None:
        if not await app._check_chat_and_respond(call):
            return
        await call.answer()
        view = await interface.get_event_journal(50)
        screen = build_journal_screen(view)
        text = render_screen_text(screen)
        markup = render_screen_markup(screen)

        user_id = call.from_user.id if call.from_user else 0
        chat_id = int(call.message.chat.id)
        message_id = int(call.message.message_id)
        if retire_graph_tracking is not None:
            retire_graph_tracking(chat_id, user_id, message_id)

        try:
            await call.message.edit_text(
                text,
                parse_mode=app.ParseMode.HTML,
                reply_markup=markup,
            )
            rendered_id = message_id
        except Exception:
            sent = await call.message.answer(
                text,
                parse_mode=app.ParseMode.HTML,
                reply_markup=markup,
            )
            rendered_id = int(sent.message_id)
            try:
                await app.bot.delete_message(chat_id, message_id)
            except Exception:
                pass

        if user_id:
            app.user_dashboard[user_id] = rendered_id
        app.chat_dashboard[chat_id] = rendered_id

    if not bool(getattr(app, "_v3_home_navigation_installed", False)):
        @app.router.callback_query(F.data == HOME_CALLBACK_DATA)
        async def _home(call: Any) -> None:
            await home_handler(call)

        app._v3_home_handler = _home
        app._v3_home_navigation_installed = True

    app._v3_journal_handler = _journal
    app._v3_journal_screen_installed = True


__all__ = [
    "HOME_CALLBACK_DATA",
    "JOURNAL_CALLBACK_DATA",
    "install_journal_screen",
]
