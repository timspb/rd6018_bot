"""Telegram middleware and composition for the single panel owner."""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from runtime.ui.telegram.panel_lifecycle import (
    TerminalPanelManager,
    _TERMINAL_CALLBACKS,
    _WORKSPACE_CALLBACKS,
    _WORKSPACE_CALLBACK_PREFIXES,
    _is_workspace_callback,
    _is_start_message,
)
logger = logging.getLogger("rd6018.ui")

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

    async def _recover_failed_start(self, event: TelegramObject, primary_exc: Exception) -> bool:
        if not _is_start_message(event):
            return False
        assert isinstance(event, Message)
        chat_id = int(event.chat.id)
        user_id = event.from_user.id if event.from_user else 0
        self.manager.leave_workspace(chat_id)
        try:
            new_id = await self.manager.ensure_text_last(chat_id, user_id)
        except Exception as fallback_exc:
            logger.warning(
                "/start fallback failed after primary dashboard error: primary=%s fallback=%s",
                primary_exc,
                fallback_exc,
            )
            return False
        logger.warning(
            "/start primary dashboard failed; recovered with text panel message_id=%s: %s",
            new_id,
            primary_exc,
        )
        return True

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        if isinstance(event, CallbackQuery):
            started_at = asyncio.get_running_loop().time()
            update = data.get("event_update") or data.get("update")
            update_id = getattr(update, "update_id", None)
            message = event.message
            user_id = getattr(getattr(event, "from_user", None), "id", None)
            chat_id = getattr(getattr(message, "chat", None), "id", None)
            callback_data = str(event.data or "")
            handler_name = getattr(handler, "__name__", type(handler).__name__)
            logger.info(
                "CALLBACK_TRACE enter update_id=%s user_id=%s chat_id=%s "
                "callback_data=%s handler=%s",
                update_id,
                user_id,
                chat_id,
                callback_data,
                handler_name,
            )
            if callback_data == "v2_battery_start":
                logger.info(
                    "START_CALLBACK_TRACE enter update_id=%s handler=%s",
                    update_id,
                    handler_name,
                )
            try:
                result = await self._handle_callback(handler, event, data)
            except Exception as exc:
                logger.info(
                    "CALLBACK_TRACE exception update_id=%s callback_data=%s "
                    "handler=%s duration_ms=%.1f exception=%s",
                    update_id,
                    callback_data,
                    handler_name,
                    (asyncio.get_running_loop().time() - started_at) * 1000,
                    type(exc).__name__,
                )
                raise
            logger.info(
                "CALLBACK_TRACE exit update_id=%s callback_data=%s handler=%s "
                "duration_ms=%.1f result=%s",
                update_id,
                callback_data,
                handler_name,
                (asyncio.get_running_loop().time() - started_at) * 1000,
                type(result).__name__ if result is not None else "None",
            )
            return result

        return await self._handle_callback(handler, event, data)

    async def _handle_callback(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        try:
            result = await handler(event, data)
        except Exception as exc:
            # /start is a pure presentation entrypoint. Its legacy handler retires the
            # previous panel before rendering the graph-backed replacement, so a media
            # transport/render failure used to leave the operator with no response.
            # Recover only this command through a graph-free truthful L2 panel. If the
            # fallback also fails (for example total Telegram outage), preserve normal
            # exception semantics instead of claiming success.
            if await self._recover_failed_start(event, exc):
                return None
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
            await manager.publish_last(
                int(chat_id),
                int(getattr(app, "last_user_id", 0) or 0),
            )
        except Exception as exc:
            logger.warning("terminal panel after notification failed: %s", exc)

    app._send_notify_safe = _notify_then_panel
    return manager
