from __future__ import annotations

from typing import Any

from aiogram import F
from aiogram.exceptions import TelegramBadRequest


def install_operator_navigation_recovery(app: Any) -> None:
    """Register the real ``operator_done`` handler before the legacy no-op handler.

    ``operator_hmi`` historically registered ``operator_done`` as only ``call.answer()``.
    Because aiogram uses first-match handler order, installing this small navigation
    boundary first makes every existing ``⬅ К панели`` callback return to the live
    operator panel without changing any actuator authority.
    """
    if bool(getattr(app, "_operator_navigation_recovery_installed", False)):
        return

    @app.router.callback_query(F.data == "operator_done")
    async def _operator_home(call: Any) -> None:
        if not await app._check_chat_and_respond(call):
            return
        try:
            await call.answer()
        except TelegramBadRequest as exc:
            # Callback acknowledgement expires during intermittent Telegram API stalls.
            # Keep navigation available, but do not mask unrelated Telegram errors.
            detail = str(exc).lower()
            if "query is too old" not in detail and "query id is invalid" not in detail:
                raise
        # The single PanelLastMiddleware owns the return to L2 after this
        # callback completes. Rendering or deleting a panel here raced the
        # middleware and left duplicate text/photo controls in Telegram.

    # Expose the handler for focused tests without depending on aiogram internals.
    app._operator_home_handler = _operator_home
    app._operator_navigation_recovery_installed = True
