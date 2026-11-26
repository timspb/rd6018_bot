"""Telegram battery selection callbacks, process-local selection state and buttons.

Callback token encoding is unchanged for previously sent messages. The selected
BatteryRecord remains the exact registry object used by existing callers.
"""
from __future__ import annotations

import hashlib
import html
from typing import Any, Callable, Optional

from aiogram import F
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from battery_registry import BatteryRecord
from battery_catalog import list_batteries
from ui_support import battery_button_label, profile_for_chemistry


_battery_pages: dict[int, list[BatteryRecord]] = {}
_selected_battery: dict[int, BatteryRecord] = {}


def _battery_callback_token(battery_id: str) -> str:
    """Return a short deterministic identity token safe for Telegram callbacks."""
    return hashlib.sha256(str(battery_id).encode("utf-8")).hexdigest()[:12]


def _battery_callback_data(record: BatteryRecord) -> str:
    return f"v2_battery_id_{_battery_callback_token(record.identity.battery_id)}"


def _battery_rows(records: list[BatteryRecord]) -> list[list[InlineKeyboardButton]]:
    return [
        [InlineKeyboardButton(text=battery_button_label(record), callback_data=_battery_callback_data(record))]
        for record in records
    ]


async def resolve_battery_callback(raw: str, user_id: int) -> Optional[BatteryRecord]:
    """Resolve durable callbacks first, retaining legacy page indexes."""
    if raw.startswith("id_"):
        token = raw[3:]
        records = await list_batteries(limit=200)
        return next(
            (
                record
                for record in records
                if profile_for_chemistry(record.identity.chemistry)
                and _battery_callback_token(record.identity.battery_id) == token
            ),
            None,
        )
    if not raw.isdigit():
        return None
    idx = int(raw)
    records = _battery_pages.get(user_id) or []
    if idx < 0 or idx >= len(records):
        records = [
            record for record in await list_batteries(limit=200)
            if profile_for_chemistry(record.identity.chemistry)
        ]
        _battery_pages[user_id] = records
    return records[idx] if 0 <= idx < len(records) else None


def selected_battery_for_user(user_id: int) -> Optional[BatteryRecord]:
    return _selected_battery.get(int(user_id))


def install_battery_add_route(
    app: Any,
    *,
    new_battery_input: set[int],
    acknowledge: Callable[..., Any],
    answer: Callable[..., Any],
    fallback_handler: Callable[[Any], Any],
    parse_battery: Callable[[str], Any],
    save_battery: Callable[..., Any],
    list_saved_batteries: Callable[..., Any],
    format_battery_card: Callable[[BatteryRecord], str],
    battery_rows: Callable[[list[BatteryRecord]], list[list[InlineKeyboardButton]]],
    charge_callback_data: str,
) -> None:
    """Own battery-add callback and its free-text continuation."""
    if getattr(app, "_battery_add_route_installed", False):
        return

    @app.router.callback_query(F.data == "v2_battery_add")
    async def battery_add_handler(call: Any) -> None:
        if not await app._check_chat_and_respond(call):
            return
        await acknowledge(call)
        user_id = call.from_user.id if call.from_user else 0
        new_battery_input.add(user_id)
        await answer(
            call,
            "<b>➕ Добавление АКБ</b>\n\n"
            "Одним сообщением:\n"
            "<code>ID | AGM/EFB/Ca/Ca | Ah | Производитель | Модель</code>\n\n"
            "Например:\n<code>varta70 | AGM | 70 | Varta | Silver Dynamic AGM</code>",
        )

    async def handle_battery_add_input(message: Any) -> None:
        user_id = message.from_user.id if message.from_user else 0
        if user_id not in new_battery_input:
            await fallback_handler(message)
            return
        try:
            identity, lifecycle = parse_battery(message.text or "")
            await save_battery(identity, lifecycle)
        except Exception as exc:
            await message.answer(
                f"❌ {html.escape(str(exc))}\n\n"
                "Формат: <code>ID | AGM/EFB/Ca/Ca | Ah | Производитель | Модель</code>",
                parse_mode=ParseMode.HTML,
            )
            return
        new_battery_input.discard(user_id)
        records = await list_saved_batteries(limit=50)
        created = next(
            (item for item in records if item.identity.battery_id == identity.battery_id),
            None,
        )
        visible_records = [
            item for item in records if profile_for_chemistry(item.identity.chemistry)
        ]
        _battery_pages[user_id] = visible_records
        rows = battery_rows(visible_records)
        rows.append([InlineKeyboardButton(text="➕ Добавить АКБ", callback_data="v2_battery_add")])
        rows.append([InlineKeyboardButton(text="⬅️ Режимы", callback_data=charge_callback_data)])
        text = (
            (format_battery_card(created) if created else
             f"✅ АКБ <code>{html.escape(identity.battery_id)}</code> сохранена.")
            + "\n\n<b>Выберите сохранённую АКБ:</b>"
        )
        await message.answer(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        )

    app._battery_add_handler = battery_add_handler
    app.handle_battery_add_input = handle_battery_add_input
    app._battery_add_route_installed = True
