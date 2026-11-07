"""Telegram presentation lifecycle helpers for keeping the operator panel last."""

from __future__ import annotations

from typing import Any


async def restore_dashboard_to_bottom(app: Any, chat_id: int, user_id: int) -> None:
    owner = getattr(app, "terminal_panel_manager", None)
    if owner is not None:
        await owner.publish_last(int(chat_id), int(user_id))


__all__ = ["restore_dashboard_to_bottom"]
