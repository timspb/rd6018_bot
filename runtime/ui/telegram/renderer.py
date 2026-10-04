"""Telegram-only renderer for declarative V3 UI contracts."""

from __future__ import annotations

import html

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from runtime.ui.actions import UIAction
from runtime.ui.buttons import ButtonSpec
from runtime.ui.screen import ScreenSpec


CALLBACK_PREFIX = "ui:"


def callback_data_for(action: UIAction) -> str:
    return f"{CALLBACK_PREFIX}{action.value}"


def action_from_callback_data(data: str) -> UIAction:
    raw = str(data or "")
    if not raw.startswith(CALLBACK_PREFIX):
        raise ValueError("not a canonical UI callback")
    return UIAction(raw[len(CALLBACK_PREFIX):])


def render_button(spec: ButtonSpec) -> InlineKeyboardButton:
    return InlineKeyboardButton(
        text=spec.label,
        callback_data=callback_data_for(spec.action),
    )


def render_screen_markup(screen: ScreenSpec) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [render_button(button) for button in row]
            for row in screen.buttons
        ]
    )


def render_screen_text(screen: ScreenSpec) -> str:
    title = f"<b>{html.escape(screen.title)}</b>"
    body = str(screen.body or "")
    return f"{title}\n\n{body}" if body else title


__all__ = [
    "CALLBACK_PREFIX",
    "action_from_callback_data",
    "callback_data_for",
    "render_button",
    "render_screen_markup",
    "render_screen_text",
]
