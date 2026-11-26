"""Telegram route for the canonical read-only AI analysis screen."""

from __future__ import annotations

from typing import Any

from runtime.ui.actions import UIAction
from runtime.ui.telegram.renderer import callback_data_for

ANALYSIS_CALLBACK_DATA = callback_data_for(UIAction.OPEN_ANALYSIS)
HOME_CALLBACK_DATA = callback_data_for(UIAction.OPEN_HOME)


async def handle_dialog_delivery(message: Any, **kwargs: Any) -> None:
    """Compatibility dispatch to the optional AI integration."""
    from integrations.ai.telegram_dialog import handle_dialog_delivery as deliver

    await deliver(message, **kwargs)




def install_analysis_screen(app: Any, **kwargs: Any) -> None:
    """Compatibility dispatch to the optional AI analysis presentation."""
    from integrations.ai.telegram_screen import install_analysis_screen as install
    install(app, **kwargs)




def __getattr__(name: str):
    """Lazy compatibility exports for former analysis presenter imports."""
    if name == "build_analysis_screen":
        from integrations.ai.screen import build_analysis_screen
        return build_analysis_screen
    raise AttributeError(name)


__all__ = [
    "ANALYSIS_CALLBACK_DATA",
    "HOME_CALLBACK_DATA",
    "install_analysis_screen",
    "handle_dialog_delivery",
    "build_analysis_screen",
]
