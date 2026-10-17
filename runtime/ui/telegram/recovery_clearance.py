"""Private, two-step Telegram workflow for durable recovery quarantine clearance."""
from __future__ import annotations

import secrets
import time
from dataclasses import dataclass
from typing import Any

from aiogram import F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from config import ALLOWED_CHAT_IDS
from application.operator_recovery_clearance import AuthorizedRecoveryOperator

CALLBACK_PREFIX = "recovery_clear:"
NONCE_TTL_S = 120.0


@dataclass(frozen=True)
class _Confirmation:
    nonce: str
    user_id: int
    chat_id: int
    incident_id: str
    expires_at: float


class TelegramRecoveryAuthority:
    def __init__(self) -> None:
        self.pending: dict[str, _Confirmation] = {}

    def issue(self, *, user_id: int, chat_id: int, incident_id: str) -> _Confirmation:
        nonce = secrets.token_urlsafe(12)
        item = _Confirmation(nonce, user_id, chat_id, incident_id, time.monotonic() + NONCE_TTL_S)
        self.pending[nonce] = item
        return item

    def authorize_clearance(self, context: Any) -> AuthorizedRecoveryOperator | None:
        if not isinstance(context, _Confirmation):
            return None
        item = self.pending.get(context.nonce)
        if item is None or item != context:
            return None
        self.pending.pop(context.nonce, None)
        if item.expires_at < time.monotonic():
            return None
        return AuthorizedRecoveryOperator(str(item.user_id))


def _approved_private_event(event: Any) -> tuple[int, int] | None:
    user = getattr(event, "from_user", None)
    chat = getattr(event, "chat", None) or getattr(getattr(event, "message", None), "chat", None)
    user_id, chat_id = getattr(user, "id", None), getattr(chat, "id", None)
    chat_type = getattr(chat, "type", None)
    if (not isinstance(user_id, int) or user_id <= 0 or not isinstance(chat_id, int)
            or chat_id != user_id or chat_type != "private"):
        return None
    # This high-privilege operation intentionally ignores ALLOW_ALL_CHATS.
    if not ALLOWED_CHAT_IDS or -1 in ALLOWED_CHAT_IDS or user_id not in ALLOWED_CHAT_IDS:
        return None
    return user_id, chat_id


def install_recovery_clearance_route(app: Any, *, service: Any, journal: Any,
                                     authority: TelegramRecoveryAuthority) -> None:
    if getattr(app, "_recovery_clearance_route_installed", False):
        return

    @app.router.message(Command("recovery_clear"))
    async def _begin(message: Any) -> None:
        ids = _approved_private_event(message)
        if ids is None:
            await message.answer("Недоступно. Команда работает только в личном чате с ID из непустого ALLOWED_CHAT_IDS (ALLOW_ALL_CHATS не подходит).")
            return
        guard = app.execution_port.session_recovery_guard
        if not guard.quarantined:
            await message.answer("Карантин восстановления не активен.")
            return
        try:
            binding = journal.incident_binding()
        except Exception:
            await message.answer("Инцидент не имеет полной идентичности. Требуется ручная проверка; оборудование не затронуто.")
            return
        user_id, chat_id = ids
        item = authority.issue(user_id=user_id, chat_id=chat_id, incident_id=binding["incident_id"])
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="Подтвердить: OFF и завершить сессию", callback_data=CALLBACK_PREFIX + item.nonce)
        ]])
        await message.answer(
            f"Карантин: {binding['reason']}\nИнцидент: {binding['incident_id']}\nСессия: {binding['session_id']}\n\n"
            "Подтверждение действует 2 минуты. Будет выполнен проверенный Output OFF и необратимо завершена только эта сессия.",
            reply_markup=keyboard,
        )

    @app.router.callback_query(F.data.startswith(CALLBACK_PREFIX))
    async def _confirm(call: Any) -> None:
        ids = _approved_private_event(call)
        if ids is None:
            await call.answer("Только разрешённый личный чат", show_alert=True)
            return
        nonce = str(call.data)[len(CALLBACK_PREFIX):]
        item = authority.pending.get(nonce)
        if item is None or item.user_id != ids[0] or item.chat_id != ids[1] or item.expires_at < time.monotonic():
            authority.pending.pop(nonce, None)
            await call.answer("Подтверждение истекло или уже использовано. Запустите /recovery_clear заново.", show_alert=True)
            return
        try:
            binding = journal.incident_binding()
            if binding["incident_id"] != item.incident_id:
                authority.pending.pop(nonce, None)
                await call.answer("Инцидент изменился; запустите команду заново.", show_alert=True)
                return
        except Exception:
            await call.answer("Инцидент недоступен", show_alert=True)
            return
        await call.answer()
        result = await service.clear(item)
        text = ("Карантин снят. Старая сессия завершена; новый запуск требует отдельного действия START."
                if result.cleared else f"Карантин сохранён: {result.reason}. Output не включался.")
        try:
            await call.message.edit_text(text, reply_markup=None)
        except Exception:
            await call.message.answer(text)

    app._recovery_clearance_route_installed = True


__all__ = ["TelegramRecoveryAuthority", "install_recovery_clearance_route"]
