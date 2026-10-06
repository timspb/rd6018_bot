"""Canonical Telegram route for cancelling the compatibility Custom wizard."""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiogram import F

from runtime.ui.actions import UIAction
from runtime.ui.routing.registry import route_for
from runtime.ui.telegram.renderer import callback_data_for


CUSTOM_CANCEL_CALLBACK_DATA = callback_data_for(UIAction.CANCEL_CUSTOM)


def install_custom_cancel_route(
    app: Any,
    *,
    cancel_state: Callable[[int], None],
    home_handler: Callable[[Any], Awaitable[None]],
) -> None:
    """Install Custom wizard cancellation without historical runtime imports."""

    if bool(getattr(app, "_v3_custom_cancel_installed", False)):
        return
    route = route_for(UIAction.CANCEL_CUSTOM)
    if not route.navigation_only:
        raise RuntimeError("Custom cancel must remain navigation-only")

    @app.router.callback_query(F.data == CUSTOM_CANCEL_CALLBACK_DATA)
    async def _custom_cancel(call: Any) -> None:
        if not await app._check_chat_and_respond(call):
            return
        user_id = int(getattr(getattr(call, "from_user", None), "id", 0) or 0)
        cancel_state(user_id)
        try:
            await call.answer("Ручной режим отменен")
        except Exception:
            pass
        await home_handler(call)

    app._v3_custom_cancel_handler = _custom_cancel
    app._v3_custom_cancel_installed = True


__all__ = ["CUSTOM_CANCEL_CALLBACK_DATA", "install_custom_cancel_route"]
