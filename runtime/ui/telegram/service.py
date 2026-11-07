"""Telegram route for the canonical service-details screen."""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiogram import F

from application.intents import OperatorIntent, OperatorIntentKind
from runtime.ui.actions import UIAction
from runtime.ui.routing.registry import route_for
from runtime.ui.screens.service import build_service_details_screen
from runtime.ui.telegram.renderer import (
    callback_data_for,
    render_screen_markup,
    render_screen_text,
)


SERVICE_CALLBACK_DATA = callback_data_for(UIAction.OPEN_SERVICE)
HOME_CALLBACK_DATA = callback_data_for(UIAction.OPEN_HOME)


def install_service_details_screen(
    app: Any,
    *,
    interface: Any,
    home_handler: Callable[[Any], Awaitable[None]],
) -> None:
    if bool(getattr(app, "_v3_service_details_installed", False)):
        return
    route = route_for(UIAction.OPEN_SERVICE)
    if not route.navigation_only:
        raise RuntimeError("service-details UI action must remain navigation-only")

    @app.router.callback_query(F.data == SERVICE_CALLBACK_DATA)
    async def _service(call: Any) -> None:
        if not await app._check_chat_and_respond(call):
            return
        submit = getattr(interface, "submit_intent", None)
        if callable(submit):
            user = str(getattr(getattr(call, "from_user", None), "id", "0"))
            result = await submit(
                OperatorIntent(
                    kind=OperatorIntentKind.SHOW_DIAGNOSTICS,
                    source="telegram",
                    user=user,
                )
            )
            if str(getattr(result, "status", "")) == "rejected":
                await call.answer("Сервисная информация недоступна", show_alert=True)
                return

        view = await interface.get_service_details()
        screen = build_service_details_screen(view)
        await call.answer()
        await call.message.answer(
            render_screen_text(screen),
            parse_mode=app.ParseMode.HTML,
            reply_markup=render_screen_markup(screen),
        )

    if not bool(getattr(app, "_v3_home_navigation_installed", False)):
        @app.router.callback_query(F.data == HOME_CALLBACK_DATA)
        async def _home(call: Any) -> None:
            await home_handler(call)

        app._v3_home_handler = _home
        app._v3_home_navigation_installed = True

    app._v3_service_details_handler = _service
    app._v3_service_details_installed = True


__all__ = ["HOME_CALLBACK_DATA", "SERVICE_CALLBACK_DATA", "install_service_details_screen"]
