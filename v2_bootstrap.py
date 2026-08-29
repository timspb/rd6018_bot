from __future__ import annotations

import time
from typing import Any

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

import v2_bot_ui
from battery_registry import init_battery_registry, upsert_battery as registry_upsert_battery
from pb_domain import ChargeIntent
from production_controller import ProductionChargeControllerV2
from v2_battery_input import parse_battery_spec
from v2_startup import start_profile_transactional


def install_v2(app: Any) -> None:
    """Install production V2 controller + Telegram presentation over bot_legacy."""
    if not isinstance(app.charge_controller, ProductionChargeControllerV2):
        app.charge_controller = ProductionChargeControllerV2(
            app.hass,
            notify_cb=app._charge_notify,
        )

    async def _upsert_from_ui(identity, lifecycle) -> None:
        await init_battery_registry()
        await registry_upsert_battery(
            identity,
            lifecycle,
            updated_at=time.time(),
        )

    # v2_bot_ui callback bodies resolve these module globals at execution time. Keep
    # the large Telegram adapter stable and inject the production-safe boundaries here.
    v2_bot_ui.upsert_battery = _upsert_from_ui
    v2_bot_ui._start_profile = start_profile_transactional
    v2_bot_ui.parse_battery_spec = parse_battery_spec

    # Keep the old pipe syntax backward compatible, but do not make the operator type
    # punctuation just to create a battery.  The primary UI now advertises natural
    # whitespace/comma input; the parser also accepts the historical pipe form.
    original_safe_answer = v2_bot_ui._safe_answer

    async def _safe_answer_natural_battery_input(event, text: str, *, reply_markup=None) -> None:
        if "ID | AGM/EFB/Ca/Ca | Ah | Производитель | Модель" in text:
            text = text.replace(
                "Одним сообщением:",
                "Одним сообщением — через пробелы или запятые:",
            )
            text = text.replace(
                "ID | AGM/EFB/Ca/Ca | Ah | Производитель | Модель",
                "ID AGM/EFB/Ca/Ca Ah Производитель Модель",
            )
            text = text.replace(
                "varta70 | AGM | 70 | Varta | Silver Dynamic AGM",
                "varta70 AGM 70 Varta Silver Dynamic AGM",
            )
            text += "\n\n<small>Запятые и старый разделитель | тоже поддерживаются.</small>"
        await original_safe_answer(event, text, reply_markup=reply_markup)

    v2_bot_ui._safe_answer = _safe_answer_natural_battery_input
    v2_bot_ui.install_v2_ui(app)

    # A stale legacy profile button can still populate awaiting_ah without a V2 intent.
    # Migration must be conservative: missing intent means NORMAL, never RECOVERY.
    installed_handle_ah = app.handle_ah_input

    async def _handle_ah_conservative(message, profile: str, user_id: int) -> None:
        v2_bot_ui._pending_intent.setdefault(user_id, ChargeIntent.NORMAL)
        await installed_handle_ah(message, profile, user_id)

    app.handle_ah_input = _handle_ah_conservative

    # In V2, an idle dashboard must not expose the old "turn on whatever setpoints are
    # currently in RD6018" shortcut. Starting always goes through chemistry -> intent
    # -> preview -> transactional enable. STOP remains the legacy hard-stop callback.
    installed_dashboard_keyboard = app._build_dashboard_keyboard

    def _build_v2_dashboard_keyboard(
        is_on: bool,
        user_id: int,
        *,
        back_to_dashboard: bool = False,
    ) -> InlineKeyboardMarkup:
        markup = installed_dashboard_keyboard(
            is_on,
            user_id,
            back_to_dashboard=back_to_dashboard,
        )
        if is_on:
            return markup

        rows = []
        for row in markup.inline_keyboard:
            new_row = []
            for button in row:
                if button.callback_data == "power_toggle":
                    new_row.append(
                        InlineKeyboardButton(
                            text="🚀 ПРОГРАММА",
                            callback_data="charge_modes",
                        )
                    )
                else:
                    new_row.append(button)
            rows.append(new_row)
        return InlineKeyboardMarkup(inline_keyboard=rows)

    app._build_dashboard_keyboard = _build_v2_dashboard_keyboard


async def init_v2_storage() -> None:
    """Create/migrate the physical battery and recovery-history tables at startup."""
    await init_battery_registry()
