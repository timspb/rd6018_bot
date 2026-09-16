"""Telegram transport adapter for the transport-neutral operator feedback port."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass
class TelegramOperatorFeedbackAdapter:
    """Send or edit operator feedback without acquiring execution authority."""

    message: Any

    async def publish(
        self,
        *,
        trace_id: str,
        status: str,
        message: str,
        metadata: Mapping[str, Any],
    ) -> None:
        await self.message.answer(str(message))

    async def update(
        self,
        *,
        trace_id: str,
        status: str,
        message: str,
        metadata: Mapping[str, Any],
    ) -> None:
        editor = getattr(self.message, "edit_text", None)
        if editor is None:
            raise RuntimeError("telegram_feedback_update_requires_editable_message")
        await editor(str(message))
