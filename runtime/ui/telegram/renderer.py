"""Telegram-only renderer for declarative V3 UI contracts."""

from __future__ import annotations

import html
from urllib.parse import parse_qsl, urlencode

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from runtime.ui.actions import UIAction
from runtime.ui.buttons import ButtonSpec
from runtime.ui.screen import ScreenSpec


CALLBACK_PREFIX = "ui:"


def callback_data_for(
    action: UIAction,
    payload: tuple[tuple[str, str], ...] = (),
) -> str:
    base = f"{CALLBACK_PREFIX}{action.value}"
    if not payload:
        return base
    encoded = urlencode(tuple((str(key), str(value)) for key, value in payload))
    data = f"{base}?{encoded}"
    if len(data.encode("utf-8")) > 64:
        raise ValueError("Telegram callback_data exceeds 64-byte limit")
    return data


def decode_callback_data(data: str) -> tuple[UIAction, dict[str, str]]:
    raw = str(data or "")
    if not raw.startswith(CALLBACK_PREFIX):
        raise ValueError("not a canonical UI callback")
    encoded = raw[len(CALLBACK_PREFIX):]
    action_raw, separator, query = encoded.partition("?")
    action = UIAction(action_raw)
    payload: dict[str, str] = {}
    if separator:
        for key, value in parse_qsl(query, keep_blank_values=True, strict_parsing=True):
            if key in payload:
                raise ValueError(f"duplicate canonical UI payload key: {key}")
            payload[key] = value
    return action, payload


def action_from_callback_data(data: str) -> UIAction:
    action, _payload = decode_callback_data(data)
    return action


def render_button(spec: ButtonSpec) -> InlineKeyboardButton:
    return InlineKeyboardButton(
        text=spec.label,
        callback_data=callback_data_for(spec.action, spec.payload),
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
    "decode_callback_data",
    "render_button",
    "render_screen_markup",
    "render_screen_text",
]
