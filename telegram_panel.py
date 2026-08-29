from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Any, Awaitable, Callable, Dict, Optional

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

logger = logging.getLogger("rd6018.ui")

# These callbacks intentionally turn the current dashboard message into a secondary
# workspace (menu/details). Preserve that source message, then publish a fresh terminal
# dashboard below it.
_PRESERVE_SOURCE_CALLBACKS = {
    "charge_modes",
    "logs",
    "info_full",
    "ai_analysis",
}

# These callbacks already leave a dashboard as the terminal message and do not create
# a newer chat message that needs to be followed by another dashboard.
_ADOPT_CALLBACKS = {
    "refresh",
    "dash_back",
    "charge_back",
    "custom_cancel",
}


class TerminalPanelManager:
    """Keep one authoritative RD6018 dashboard as the last bot message in each chat.

    Telegram edits do not change message ordering. The legacy UI historically edited
    the old dashboard after sending notices/prompts, so the operator often ended with
    a text message below the controls. This manager deliberately republishes the
    dashboard as a *new* message after interactive output, then removes only the prior
    dashboard message it owns. Secondary menus/details are preserved above it.

    The manager never calls HA or RD6018 directly. It delegates rendering to the
    existing dashboard builder, so this module is presentation-only.
    """

    def __init__(self, app: Any) -> None:
        self.app = app
        self._panel_by_chat: Dict[int, int] = {}
        self._locks: Dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)

    def panel_id(self, chat_id: int) -> Optional[int]:
        return self._panel_by_chat.get(int(chat_id))

    def adopt(self, chat_id: int, user_id: int, message_id: Optional[int] = None) -> Optional[int]:
        """Adopt an already-rendered dashboard without creating a new message."""
        chat_id = int(chat_id)
        user_id = int(user_id or 0)
        candidate = message_id
        if candidate is None and user_id:
            candidate = self.app.user_dashboard.get(user_id)
        if candidate is None:
            candidate = self.app.chat_dashboard.get(chat_id)
        if candidate is None:
            return None
        panel_id = int(candidate)
        self._panel_by_chat[chat_id] = panel_id
        self.app.chat_dashboard[chat_id] = panel_id
        if user_id:
            self.app.user_dashboard[user_id] = panel_id
        return panel_id

    async def _delete_previous_panel(
        self,
        chat_id: int,
        previous_panel_id: Optional[int],
        new_panel_id: int,
        preserve_message_id: Optional[int],
    ) -> None:
        if previous_panel_id is None:
            return
        if previous_panel_id in {new_panel_id, preserve_message_id}:
            return
        try:
            await self.app.bot.delete_message(chat_id, previous_panel_id)
        except Exception as exc:
            logger.debug("old terminal panel cleanup failed: %s", exc)

    async def ensure_last(
        self,
        chat_id: int,
        user_id: int = 0,
        *,
        preserve_message_id: Optional[int] = None,
    ) -> int:
        """Publish a fresh dashboard at the bottom and retire the previous dashboard."""
        chat_id = int(chat_id)
        user_id = int(user_id or 0)
        async with self._locks[chat_id]:
            previous = self._panel_by_chat.get(chat_id)
            new_id = await self.app._build_and_send_dashboard(
                chat_id=chat_id,
                user_id=user_id,
                old_msg_id=None,
                anchor_msg_id=None,
            )
            new_id = int(new_id)
            self._panel_by_chat[chat_id] = new_id
            self.app.chat_dashboard[chat_id] = new_id
            if user_id:
                self.app.user_dashboard[user_id] = new_id
            await self._delete_previous_panel(
                chat_id,
                previous,
                new_id,
                preserve_message_id,
            )
            return new_id

    async def after_event(self, event: TelegramObject) -> None:
        if isinstance(event, CallbackQuery):
            if event.message is None:
                return
            chat_id = event.message.chat.id
            user_id = event.from_user.id if event.from_user else 0
            data = str(event.data or "")

            if data in _ADOPT_CALLBACKS or data.startswith("chart_"):
                self.adopt(chat_id, user_id)
                return

            preserve = (
                event.message.message_id
                if data in _PRESERVE_SOURCE_CALLBACKS
                else None
            )
            await self.ensure_last(
                chat_id,
                user_id,
                preserve_message_id=preserve,
            )
            return

        if isinstance(event, Message):
            chat_id = event.chat.id
            user_id = event.from_user.id if event.from_user else 0
            text = str(event.text or "").strip().lower()
            # /start already creates a new dashboard as its final response. Adopt it
            # instead of creating a pointless second copy.
            if text == "/start" or text.startswith("/start@"):
                self.adopt(chat_id, user_id)
                return
            await self.ensure_last(chat_id, user_id)


class PanelLastMiddleware(BaseMiddleware):
    def __init__(self, manager: TerminalPanelManager) -> None:
        self.manager = manager

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        result = await handler(event, data)
        try:
            await self.manager.after_event(event)
        except Exception as exc:
            # UI ordering must never turn a successful actuator command into a failed
            # command. Surface the problem in logs and leave the existing panel intact.
            logger.warning("terminal panel refresh failed: %s", exc)
        return result


def install_panel_last(app: Any) -> TerminalPanelManager:
    existing = getattr(app, "terminal_panel_manager", None)
    if isinstance(existing, TerminalPanelManager):
        return existing

    manager = TerminalPanelManager(app)
    app.terminal_panel_manager = manager

    app.router.message.outer_middleware(PanelLastMiddleware(manager))
    app.router.callback_query.outer_middleware(PanelLastMiddleware(manager))

    # The legacy 60-second "bring dashboard back" timer becomes counterproductive once
    # ordering is managed transactionally after every handler. Replace it with a no-op;
    # user-driven events are covered by middleware and background safety notifications
    # are covered by the wrapper below.
    def _panel_ordering_owned(_chat_id: int, _user_id: int = 0) -> None:
        return None

    app.schedule_dashboard_after_60 = _panel_ordering_owned

    original_notify_safe = app._send_notify_safe

    async def _notify_then_panel(msg: str, critical: bool = True) -> None:
        await original_notify_safe(msg, critical)
        chat_id = getattr(app, "last_chat_id", None)
        if not chat_id:
            return
        try:
            await manager.ensure_last(
                int(chat_id),
                int(getattr(app, "last_user_id", 0) or 0),
            )
        except Exception as exc:
            logger.warning("terminal panel after notification failed: %s", exc)

    app._send_notify_safe = _notify_then_panel
    return manager
