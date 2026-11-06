"""Telegram presentation lifecycle helpers for keeping the operator panel last."""

from __future__ import annotations

from typing import Any


async def restore_dashboard_to_bottom(app: Any, chat_id: int, user_id: int) -> None:
    restore = getattr(app, "_restore_dashboard_to_bottom", None)
    if callable(restore):
        await restore(int(chat_id), int(user_id))
        return
    schedule = getattr(app, "schedule_dashboard_after_60", None)
    if callable(schedule):
        schedule(int(chat_id), int(user_id))


__all__ = ["restore_dashboard_to_bottom"]
