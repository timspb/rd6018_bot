"""Telegram route for the canonical entity-status screen."""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiogram import F

from runtime.ui.actions import UIAction
from runtime.ui.routing.registry import route_for
from runtime.ui.screens.entities import build_entities_screen
from runtime.ui.telegram.renderer import (
    callback_data_for,
    render_screen_markup,
    render_screen_text,
)


ENTITIES_CALLBACK_DATA = callback_data_for(UIAction.OPEN_ENTITIES)
HOME_CALLBACK_DATA = callback_data_for(UIAction.OPEN_HOME)


def install_entities_screen(
    app: Any,
    *,
    interface: Any,
    home_handler: Callable[[Any], Awaitable[None]],
) -> None:
    if bool(getattr(app, "_v3_entities_screen_installed", False)):
        return
    route = route_for(UIAction.OPEN_ENTITIES)
    if not route.navigation_only:
        raise RuntimeError("entities UI action must remain navigation-only")

    @app.router.callback_query(F.data == ENTITIES_CALLBACK_DATA)
    async def _entities(call: Any) -> None:
        if not await app._check_chat_and_respond(call):
            return
        try:
            await call.answer("Опрашиваю сущности...")
        except Exception:
            pass
        view = await interface.get_entity_statuses()
        screen = build_entities_screen(view)
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

    app._v3_entities_handler = _entities
    app._v3_entities_screen_installed = True


__all__ = ["ENTITIES_CALLBACK_DATA", "HOME_CALLBACK_DATA", "install_entities_screen"]
