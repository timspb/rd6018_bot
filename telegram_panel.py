from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Any, Awaitable, Callable, Dict, Optional

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

logger = logging.getLogger("rd6018.ui")

# Callbacks that update/adopt the already-rendered main panel without opening a
# workspace and therefore do not need a second terminal panel message.
_ADOPT_CALLBACKS = {
    "refresh",
}

# A terminal callback closes an L3/L4 workspace. After its handler is finished the
# semantic L2 panel must be republished as the newest message in the chat.
_TERMINAL_CALLBACKS = {
    "dash_back",
    "charge_back",
    "custom_cancel",
    "operator_done",
    "operator_adopted_stop_execute",
    "rd_live_mix_start_observe",
    "rd_live_mix_start_delta_off",
    "rd_live_mix_cancel",
    "rd_live_mix_stop_observer",
    "rd_hands_off_release_execute",
    "rd_hands_off_release_cancel",
    # Normal V2 program workflows end here after an explicit start action. A failed
    # start is terminal too: its handler already explains the result, then L2 returns.
    "v2_quick_start",
    "v2_battery_start",
    "v2_mix_start",
    # Interrupted Manual has an explicit terminal choice.
    "v2_manual_reauthorize",
    "v2_manual_discard",
}

# Navigation/detail/program callbacks are an operator workspace. Do NOT append a
# dashboard after every click. The panel returns only when the workflow terminates.
_WORKSPACE_CALLBACKS = {
    "charge_modes",
    "logs",
    "info_full",
    "ai_analysis",
    "entities_status",
    "menu_off",
    "rd_live_mix",
    "rd_live_mix_status",
    "rd_hands_off_release_confirm",
    "operator_details",
    "operator_graph",
    "operator_more",
    "operator_adopted_stop",
}
_WORKSPACE_CALLBACK_PREFIXES = (
    "v2_",
    "off_",
    "profile_",
    "custom_",
    "rd_live_mix_",
    "rd_hands_off_release_",
    "operator_graph_",
)


def _is_workspace_callback(data: str) -> bool:
    data = str(data or "")
    if data in _TERMINAL_CALLBACKS:
        return False
    return data in _WORKSPACE_CALLBACKS or data.startswith(_WORKSPACE_CALLBACK_PREFIXES)


class TerminalPanelManager:
    """Keep one authoritative L2 panel without stealing focus from L3/L4 work.

    Telegram edits do not change message ordering. While a menu/workflow is active,
    its messages are deliberately allowed to remain at the bottom. A fresh semantic
    panel is published exactly when that workflow is completed/cancelled or when a
    top-level action finishes.
    """

    def __init__(self, app: Any) -> None:
        self.app = app
        self._panel_by_chat: Dict[int, int] = {}
        self._locks: Dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._workspace_chats: set[int] = set()

    def panel_id(self, chat_id: int) -> Optional[int]:
        return self._panel_by_chat.get(int(chat_id))

    def in_workspace(self, chat_id: int) -> bool:
        return int(chat_id) in self._workspace_chats

    def enter_workspace(self, chat_id: int) -> None:
        self._workspace_chats.add(int(chat_id))

    def leave_workspace(self, chat_id: int) -> None:
        self._workspace_chats.discard(int(chat_id))

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
        """Publish a fresh dashboard at the bottom and retire the previous panel."""
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
            chat_id = int(event.message.chat.id)
            user_id = event.from_user.id if event.from_user else 0
            data = str(event.data or "")

            if data in _ADOPT_CALLBACKS:
                self.adopt(chat_id, user_id)
                return

            if data in _TERMINAL_CALLBACKS:
                self.leave_workspace(chat_id)
                await self.ensure_last(chat_id, user_id)
                return

            # Old stale dashboard graph callbacks are treated as a detail workspace;
            # the new L2 panel no longer exposes them directly.
            if data.startswith("chart_"):
                self.enter_workspace(chat_id)
                return

            if _is_workspace_callback(data):
                self.enter_workspace(chat_id)
                return

            # Any ordinary top-level action finishes outside a workspace and restores
            # the single authoritative L2 panel at the bottom.
            self.leave_workspace(chat_id)
            await self.ensure_last(chat_id, user_id)
            return

        if isinstance(event, Message):
            chat_id = int(event.chat.id)
            user_id = event.from_user.id if event.from_user else 0
            text = str(event.text or "").strip()
            lower = text.lower()

            # /start already creates its dashboard. Adopt that one instead of sending
            # a second copy.
            if lower == "/start" or lower.startswith("/start@"):
                self.leave_workspace(chat_id)
                self.adopt(chat_id, user_id)
                return

            # Plain text is commonly an input step in a currently active workflow.
            # Never inject the panel under the handler response. Explicit callbacks
            # close the workflow and restore L2. Text-driven terminal workflows (for
            # example Manual numeric input) keep their own semantic success response;
            # the next explicit navigation action restores L2 without stealing focus.
            if not text.startswith("/"):
                return

            self.leave_workspace(chat_id)
            await self.ensure_last(chat_id, user_id)


class PanelLastMiddleware(BaseMiddleware):
    def __init__(self, manager: TerminalPanelManager) -> None:
        self.manager = manager

    async def _restore_panel(self, event: TelegramObject) -> None:
        try:
            await self.manager.after_event(event)
        except Exception as exc:
            # Message ordering is a UI invariant, but it must never replace the real
            # handler outcome or turn a successful actuator command into a UI error.
            logger.warning("terminal panel refresh failed: %s", exc)

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        try:
            result = await handler(event, data)
        except Exception:
            await self._restore_panel(event)
            raise
        await self._restore_panel(event)
        return result


def install_panel_last(app: Any) -> TerminalPanelManager:
    existing = getattr(app, "terminal_panel_manager", None)
    if isinstance(existing, TerminalPanelManager):
        return existing

    manager = TerminalPanelManager(app)
    app.terminal_panel_manager = manager

    app.router.message.outer_middleware(PanelLastMiddleware(manager))
    app.router.callback_query.outer_middleware(PanelLastMiddleware(manager))

    # Legacy delayed dashboard timers are incompatible with an active L3/L4 workspace.
    def _panel_ordering_owned(_chat_id: int, _user_id: int = 0) -> None:
        return None

    app.schedule_dashboard_after_60 = _panel_ordering_owned

    original_notify_safe = app._send_notify_safe

    async def _notify_then_panel(msg: str, critical: bool = True) -> None:
        await original_notify_safe(msg, critical)
        chat_id = getattr(app, "last_chat_id", None)
        if not chat_id:
            return
        # A background notification must not steal focus from a menu that the operator
        # is currently using. The terminal action will restore L2 when the workflow
        # actually ends.
        if manager.in_workspace(int(chat_id)):
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
