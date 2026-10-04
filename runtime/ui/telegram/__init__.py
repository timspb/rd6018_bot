"""Telegram transport adapters for canonical V3 screens."""

from .renderer import (
    CALLBACK_PREFIX,
    action_from_callback_data,
    callback_data_for,
    render_button,
    render_screen_markup,
    render_screen_text,
)
from .details import install_operator_details_screen
from .entities import install_entities_screen
from .help import install_help_screen
from .journal import install_journal_screen
from .service import install_service_details_screen

__all__ = [
    "CALLBACK_PREFIX",
    "action_from_callback_data",
    "callback_data_for",
    "install_journal_screen",
    "install_entities_screen",
    "install_help_screen",
    "install_operator_details_screen",
    "install_service_details_screen",
    "render_button",
    "render_screen_markup",
    "render_screen_text",
]
