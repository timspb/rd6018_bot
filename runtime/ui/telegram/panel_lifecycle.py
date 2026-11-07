"""Single ownership of Telegram panel/workspace state and publication.

This module owns the panel ID, workspace transitions, and serialization.
Telegram callbacks and graph renderers supply data and transport only.
"""
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Any, Dict, Optional

from aiogram.types import CallbackQuery, Message, TelegramObject
from runtime.ui.telegram.analysis import ANALYSIS_CALLBACK_DATA
from runtime.ui.telegram.custom import CUSTOM_CANCEL_CALLBACK_DATA
from runtime.ui.telegram.charge import (
    BATTERIES_CALLBACK_DATA,
    BATTERY_ADD_CALLBACK_DATA,
    CHARGE_CALLBACK_DATA,
    INTERRUPTED_MANUAL_CALLBACK_DATA,
    MANUAL_CALLBACK_DATA,
    PROFILE_CALLBACK_PREFIX,
)
from runtime.ui.telegram.entities import ENTITIES_CALLBACK_DATA
from runtime.ui.telegram.journal import HOME_CALLBACK_DATA, JOURNAL_CALLBACK_DATA
from runtime.ui.telegram.off_conditions import OFF_CALLBACK_DATA, OFF_PRESET_PREFIX

logger = logging.getLogger("rd6018.ui")

# A terminal callback closes an L3/L4 workspace. After its handler is finished the
# semantic L2 panel must be republished as the newest message in the chat.
_TERMINAL_CALLBACKS = {
    CUSTOM_CANCEL_CALLBACK_DATA,
    "operator_done",
    HOME_CALLBACK_DATA,
    "operator_adopted_stop_execute",
    "operator_managed_mix_stop_execute",
    "rd_live_mix_start_observe",
    "rd_live_mix_start_delta_off",
    "rd_live_mix_cancel",
    "rd_live_mix_stop_observer",
    "rd_managed_adopt_execute",
    "rd_managed_adopt_cancel",
    "rd_managed_mix_execute",
    "rd_managed_mix_cancel",
    "rd_hands_off_release_execute",
    "rd_hands_off_release_cancel",
    # Normal V2 program workflows end here after an explicit start action. A failed
    # start is terminal too: its handler already explains the result, then L2 returns.
    "v2_quick_start",
    "v2_battery_start",
    "v2_mix_start",
    "v2_manual_unbound",
    # Interrupted Manual has an explicit terminal choice.
    "v2_manual_reauthorize",
    "v2_manual_discard",
}

# Navigation/detail/program callbacks are an operator workspace. Do NOT append a
# dashboard after every click. The panel returns only when the workflow terminates.
_WORKSPACE_CALLBACKS = {
    CHARGE_CALLBACK_DATA,
    BATTERIES_CALLBACK_DATA,
    BATTERY_ADD_CALLBACK_DATA,
    MANUAL_CALLBACK_DATA,
    INTERRUPTED_MANUAL_CALLBACK_DATA,
    JOURNAL_CALLBACK_DATA,
    ANALYSIS_CALLBACK_DATA,
    ENTITIES_CALLBACK_DATA,
    OFF_CALLBACK_DATA,
    "rd_live_mix",
    "rd_live_mix_status",
    "rd_managed_adopt",
    "rd_managed_mix",
    "rd_managed_mix_status",
    "rd_hands_off_release_confirm",
    "operator_details",
    "operator_graph",
    "operator_more",
    "operator_adopted_stop",
    "operator_managed_mix_stop",
}
_WORKSPACE_CALLBACK_PREFIXES = (
    "v2_",
    "off_",
    "rd_live_mix_",
    "rd_managed_adopt_",
    "rd_managed_mix_",
    "rd_hands_off_release_",
    OFF_PRESET_PREFIX + "?",
    PROFILE_CALLBACK_PREFIX + "?",
)


def _is_workspace_callback(data: str) -> bool:
    data = str(data or "")
    if data in _TERMINAL_CALLBACKS:
        return False
    return data in _WORKSPACE_CALLBACKS or data.startswith(_WORKSPACE_CALLBACK_PREFIXES)


def _is_start_message(event: TelegramObject) -> bool:
    if not isinstance(event, Message):
        return False
    text = str(event.text or "").strip().lower()
    return text == "/start" or text.startswith("/start@")


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
        self._graph_refresh_task: asyncio.Task | None = None
        self._graph_refresh_callback = None
        self._graph_user_by_chat: Dict[int, int] = {}

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

    def graph_id(self, chat_id: int, user_id: int = 0) -> Optional[int]:
        """The currently adopted graph is the same logical L2 panel."""
        by_chat = getattr(self.app, "chat_graph_dashboard", {})
        by_user = getattr(self.app, "user_graph_dashboard", {})
        value = by_chat.get(int(chat_id)) or (
            by_user.get(int(user_id)) if user_id else None
        )
        return int(value) if value is not None else None

    def adopt_graph(self, chat_id: int, user_id: int, message_id: int) -> int:
        """Single authoritative bookkeeping of a published graph/message ID."""
        self.app.user_graph_dashboard[int(user_id)] = int(message_id)
        self.app.chat_graph_dashboard[int(chat_id)] = int(message_id)
        self._graph_user_by_chat[int(chat_id)] = int(user_id)
        return int(self.adopt(chat_id, user_id, message_id))

    def forget_graph(self, chat_id: int, user_id: int, message_id: int) -> None:
        """Retire only the exact graph ID; never erase a newer publication."""
        graph_id = int(message_id)
        if self.app.user_graph_dashboard.get(int(user_id)) == graph_id:
            self.app.user_graph_dashboard.pop(int(user_id), None)
        if self.app.chat_graph_dashboard.get(int(chat_id)) == graph_id:
            self.app.chat_graph_dashboard.pop(int(chat_id), None)
            self._graph_user_by_chat.pop(int(chat_id), None)
        if self._panel_by_chat.get(int(chat_id)) == graph_id:
            self._panel_by_chat.pop(int(chat_id), None)
        if self.app.user_dashboard.get(int(user_id)) == graph_id:
            self.app.user_dashboard.pop(int(user_id), None)
        if self.app.chat_dashboard.get(int(chat_id)) == graph_id:
            self.app.chat_dashboard.pop(int(chat_id), None)

    async def publish_last(self, chat_id: int, user_id: int) -> int:
        """The only terminal publication path: serialize graph replacement."""
        chat_id, user_id = int(chat_id), int(user_id)
        async with self._locks[chat_id]:
            restore = getattr(self.app, "_restore_dashboard_to_bottom", None)
            if callable(restore):
                panel_id = await restore(chat_id, user_id)
                return int(self.adopt(chat_id, user_id, panel_id))
            return await self._ensure_last_unlocked(chat_id, user_id)

    async def refresh_graph(self, chat_id: int, user_id: int, refresh, *, force=False) -> None:
        """Serialize timed graph edits with terminal publish/delete operations."""
        chat_id, user_id = int(chat_id), int(user_id)
        async with self._locks[chat_id]:
            if self.in_workspace(chat_id) or self.graph_id(chat_id, user_id) is None:
                return
            await refresh(chat_id, user_id, force=force)

    def start_graph_refresh(self, refresh_callback) -> None:
        """Schedule the single graph refresh loop owned by this lifecycle."""
        self._graph_refresh_callback = refresh_callback
        task = self._graph_refresh_task
        if task is None or task.done():
            self._graph_refresh_task = asyncio.create_task(self._graph_tick_loop())

    async def _graph_tick_loop(self) -> None:
        while True:
            await asyncio.sleep(60.0)
            # Telegram IDs are scoped to a chat: identical message_id values
            # in two chats must never cross-route a refresh.
            for chat_id, user_id in list(self._graph_user_by_chat.items()):
                if self.graph_id(chat_id, user_id) is None:
                    continue
                try:
                    await self.refresh_graph(
                        chat_id, user_id, self._graph_refresh_callback,
                    )
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    logger.debug("periodic graph refresh failed: %s", exc)

    async def render_graph(self, chat_id: int, user_id: int, render) -> None:
        """Serialize operator-requested graph/range changes with background edits."""
        chat_id, user_id = int(chat_id), int(user_id)
        async with self._locks[chat_id]:
            await render()
            graph = self.graph_id(chat_id, user_id)
            if graph is not None:
                self.adopt(chat_id, user_id, graph)

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
            return await self._ensure_last_unlocked(chat_id, user_id, preserve_message_id=preserve_message_id)

    async def _ensure_last_unlocked(self, chat_id: int, user_id: int, *, preserve_message_id=None) -> int:
        # Graph dashboard is the canonical active-charge panel. A former
        # text panel ID can linger in _panel_by_chat after a route replaced
        # the graph; never refresh that stale text message into a second L2.
        graph_by_user = getattr(self.app, "user_graph_dashboard", {})
        graph_by_chat = getattr(self.app, "chat_graph_dashboard", {})
        graph_id = (
            graph_by_user.get(user_id) if user_id else None
        ) or graph_by_chat.get(chat_id)
        previous = (
            graph_id
            or (self.app.user_dashboard.get(user_id) if user_id else None)
            or self.app.chat_dashboard.get(chat_id)
            or self._panel_by_chat.get(chat_id)
        )
        refresh = getattr(self.app, "_refresh_operator_panel", None)
        if previous is not None and refresh is not None:
            refreshed_id = await refresh(chat_id, user_id, int(previous))
            if refreshed_id is not None:
                panel_id = int(refreshed_id)
                self._panel_by_chat[chat_id] = panel_id
                self.app.chat_dashboard[chat_id] = panel_id
                if user_id:
                    self.app.user_dashboard[user_id] = panel_id
                if panel_id != int(previous):
                    await self._delete_previous_panel(
                        chat_id, int(previous), panel_id, preserve_message_id,
                    )
                return panel_id
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

    async def ensure_text_last(
        self,
        chat_id: int,
        user_id: int = 0,
        *,
        preserve_message_id: Optional[int] = None,
    ) -> int:
        """Publish the final semantic panel without graph/media dependencies.

        This is a narrow recovery path for a failed ``/start`` render. It performs no
        actuator action and resolves the same final HMI state/keyboard functions that
        production composition installed; only the optional graph transport is skipped.
        """
        chat_id = int(chat_id)
        user_id = int(user_id or 0)
        async with self._locks[chat_id]:
            previous = self._panel_by_chat.get(chat_id)
            try:
                live = await self.app.hass.get_all_live()
            except Exception as exc:
                logger.warning("/start text fallback HA read failed; rendering degraded panel: %s", exc)
                live = {}

            # Import at recovery time so late production HMI wrappers (output truth,
            # AUTONOMOUS, ownership) remain authoritative for the fallback panel.
            import operator_hmi as hmi

            state = hmi.build_operator_hmi_state(self.app, live)
            text = hmi.render_operator_panel(state)
            markup = hmi.build_operator_keyboard(self.app, state)
            sent = await self.app.bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode=self.app.ParseMode.HTML,
                reply_markup=markup,
            )
            new_id = int(sent.message_id)
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

            # Chart range buttons edit the current L2 graph in-place. They
            # are not submenu navigation; periodic updates must continue.
            if data.startswith("operator_graph_"):
                self.leave_workspace(chat_id)
                self.adopt(chat_id, user_id)
                return

            if data in _TERMINAL_CALLBACKS:
                self.leave_workspace(chat_id)
                # The handler has finished sending its result. Publish exactly
                # one semantic graph/control panel at the bottom via the existing
                # graph renderer. Editing a prior photo does not reorder Telegram
                # messages, and the old ensure_last() could refresh a stale text
                # ID into a second panel after the graph.
                await self.publish_last(chat_id, user_id)
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
            # a second copy. Handler failures are recovered by PanelLastMiddleware via
            # ensure_text_last(), so this success path never duplicates a panel.
            if lower == "/start" or lower.startswith("/start@"):
                if not self.in_workspace(chat_id):
                    self.adopt(chat_id, user_id)
                return

            # These commands OPEN a read-only workspace. Keep that screen
            # last; its explicit "Back to panel" callback is the terminal edge.
            command = lower.split("@", 1)[0].split(None, 1)[0]
            if command in {"/logs", "/ai", "/entities", "/off"}:
                self.enter_workspace(chat_id)
                return

            # Plain text is commonly input within an active workflow.
            if not text.startswith("/"):
                return

            self.leave_workspace(chat_id)
            # /help and /stats have no Back callback. Put the canonical graph
            # after their result, once, instead of racing route-owned restores.
            if command in {"/help", "/stats"}:
                restore = getattr(self.app, "_restore_dashboard_to_bottom", None)
                if callable(restore):
                    panel_id = await restore(chat_id, user_id)
                    self.adopt(chat_id, user_id, panel_id)
                    return
            await self.ensure_last(chat_id, user_id)
