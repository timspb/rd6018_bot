"""Telegram route for the canonical journal screen."""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiogram import F
from aiogram.filters import Command

from runtime.ui.actions import UIAction
from runtime.ui.routing.registry import route_for
from runtime.ui.screens.journal import build_journal_screen
from runtime.ui.telegram.renderer import (
    callback_data_for,
    decode_callback_data,
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
    restore_dashboard: Callable[[int, int], Awaitable[Any]] | None = None,
) -> None:
    """Install the migrated journal route without importing historical owners."""

    if bool(getattr(app, "_v3_journal_screen_installed", False)):
        return
    route = route_for(UIAction.OPEN_JOURNAL)
    if not route.navigation_only:
        raise RuntimeError("journal UI action must remain navigation-only")

    async def send_journal(chat_id: int, *, offset: int = 0):
        view = await interface.get_event_journal(None)
        screen = build_journal_screen(view, offset=offset)
        return view, render_screen_text(screen), render_screen_markup(screen)

    async def answer_journal_error(message: Any) -> None:
        try:
            await message.answer("❌ Не удалось загрузить журнал. Повторите попытку позже.")
        except Exception:
            # A transport failure cannot be repaired from inside this callback.
            return

    @app.router.callback_query(F.data.startswith(JOURNAL_CALLBACK_DATA))
    async def _journal(call: Any) -> None:
        if not await app._check_chat_and_respond(call):
            return
        await call.answer()
        user_id = call.from_user.id if call.from_user else 0
        chat_id = int(call.message.chat.id)
        offset = 0
        is_page = False
        try:
            _action, payload = decode_callback_data(str(getattr(call, "data", JOURNAL_CALLBACK_DATA)))
            is_page = "offset" in payload
            offset = max(0, min(100_000, int(payload.get("offset", "0"))))
        except (ValueError, TypeError):
            offset = 0

        try:
            _view, text, markup = await send_journal(chat_id, offset=offset)
        except Exception:
            await answer_journal_error(call.message)
            return
        if is_page:
            # Pagination edits only the journal message; it never touches dashboard IDs.
            try:
                await call.message.edit_text(
                    text, parse_mode=app.ParseMode.HTML, reply_markup=markup,
                )
                return
            except Exception:
                # Stale photo/non-text messages cannot be edited as text. Send
                # the requested page as a fresh message instead of dropping it.
                try:
                    await call.message.answer(
                        text, parse_mode=app.ParseMode.HTML, reply_markup=markup,
                    )
                    return
                except Exception:
                    await answer_journal_error(call.message)
                    return
        if offset == 0:
            try:
                # The journal remains the active workspace until the operator
                # explicitly returns. Never append L2 below the journal.
                await call.message.answer(
                    text, parse_mode=app.ParseMode.HTML, reply_markup=markup,
                )
            except Exception:
                await answer_journal_error(call.message)

    @app.router.message(Command("logs"))
    async def _journal_command(message: Any) -> None:
        if not await app._check_chat_and_respond(message):
            return
        chat_id = int(message.chat.id)
        user_id = message.from_user.id if message.from_user else 0
        try:
            _view, text, markup = await send_journal(chat_id)
            await message.answer(
                text,
                parse_mode=app.ParseMode.HTML,
                reply_markup=markup,
            )
        except Exception:
            await answer_journal_error(message)

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
