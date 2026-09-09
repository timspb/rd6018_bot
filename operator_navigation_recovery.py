from __future__ import annotations

from typing import Any

from aiogram import F


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
        await call.answer()
        user_id = call.from_user.id if call.from_user else 0
        chat_id = call.message.chat.id
        current_id = call.message.message_id

        dashboard_id = None
        user_dashboard = getattr(app, "user_dashboard", None)
        if isinstance(user_dashboard, dict):
            dashboard_id = user_dashboard.get(user_id)
        if dashboard_id is None:
            chat_dashboard = getattr(app, "chat_dashboard", None)
            if isinstance(chat_dashboard, dict):
                dashboard_id = chat_dashboard.get(chat_id)

        target = int(dashboard_id) if dashboard_id else int(current_id)
        if dashboard_id and int(dashboard_id) != int(current_id):
            try:
                await app.bot.delete_message(chat_id, current_id)
            except Exception:
                pass

        refresh = getattr(app, "_refresh_operator_panel", None)
        if callable(refresh):
            try:
                await refresh(chat_id, user_id, target)
                return
            except Exception:
                pass

        build = getattr(app, "_build_and_send_dashboard", None)
        if callable(build):
            await build(chat_id, user_id, old_msg_id=target)

    # Expose the handler for focused tests without depending on aiogram internals.
    app._operator_home_handler = _operator_home
    app._operator_navigation_recovery_installed = True
