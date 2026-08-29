from __future__ import annotations

import time
from typing import Any

from aiogram import F
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

import v2_bot_ui
from battery_registry import init_battery_registry, upsert_battery as registry_upsert_battery
from pb_domain import ChargeIntent
from production_controller import ProductionChargeControllerV2
from runtime_safety_strict import install_strict_runtime_safety
from telegram_panel import install_panel_last
from v2_battery_input import parse_battery_spec
from v2_startup import start_profile_transactional
from v2_ui_polish import build_operator_dashboard_keyboard, install_dashboard_polish


def _operator_intent_keyboard(prefix: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Обычный", callback_data=f"{prefix}_normal"),
                InlineKeyboardButton(text="Восстановление", callback_data=f"{prefix}_recovery"),
            ],
            [
                InlineKeyboardButton(text="Кондиционирование", callback_data=f"{prefix}_conditioning"),
                InlineKeyboardButton(text="Диагностика", callback_data=f"{prefix}_diagnostic"),
            ],
            [InlineKeyboardButton(text="⬅ К программам", callback_data="charge_modes")],
        ]
    )


def _operator_preview_keyboard(start_callback: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="▶ Запустить программу", callback_data=start_callback)],
            [InlineKeyboardButton(text="⬅ Изменить", callback_data="charge_modes")],
        ]
    )


def _operator_modes_text() -> str:
    return (
        "<b>Программа заряда</b>\n\n"
        "Рекомендуемый путь — выбрать сохранённый аккумулятор: его химия, ёмкость и история "
        "будут привязаны к одной физической АКБ. Для разового запуска можно выбрать химию ниже.\n\n"
        "<b>Цель программы</b>\n"
        "Обычный — штатный заряд без автоматического высоковольтного этапа.\n"
        "Восстановление — высоковольтный этап разрешается только по подтверждённым признакам.\n"
        "Кондиционирование — сервисный режим внутри ограничений профиля.\n"
        "Диагностика — наблюдение без автоматической HV-эскалации.\n\n"
        "В CV окончание оценивается по Imin→ΔI; в CC — по Vmax→ΔV."
    )


def _operator_modes_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔋 Мои аккумуляторы", callback_data="v2_batteries")],
            [
                InlineKeyboardButton(text="Ca/Ca", callback_data="v2_profile_caca"),
                InlineKeyboardButton(text="EFB", callback_data="v2_profile_efb"),
                InlineKeyboardButton(text="AGM", callback_data="v2_profile_agm"),
            ],
            [
                InlineKeyboardButton(text="＋ Добавить АКБ", callback_data="v2_battery_add"),
                InlineKeyboardButton(text="Ручной режим", callback_data="profile_custom"),
            ],
            [
                InlineKeyboardButton(text="Условие OFF", callback_data="menu_off"),
                InlineKeyboardButton(text="⬅ К панели", callback_data="charge_back"),
            ],
        ]
    )


def install_v2(app: Any, *, install_ui: bool = True) -> None:
    """Install production V2 controller/safety and the operator-facing Telegram UI."""
    if not isinstance(app.charge_controller, ProductionChargeControllerV2):
        app.charge_controller = ProductionChargeControllerV2(
            app.hass,
            notify_cb=app._charge_notify,
        )

    # Safety is independent from presentation and remains installed even with V2_UI=0.
    install_strict_runtime_safety(app)

    if not install_ui:
        return

    async def _upsert_from_ui(identity, lifecycle) -> None:
        await init_battery_registry()
        await registry_upsert_battery(
            identity,
            lifecycle,
            updated_at=time.time(),
        )

    v2_bot_ui.upsert_battery = _upsert_from_ui
    v2_bot_ui._start_profile = start_profile_transactional
    v2_bot_ui.parse_battery_spec = parse_battery_spec

    # Keep old pipe syntax backward compatible while advertising normal free-form input.
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
            text += "\n\nЗапятые и старый разделитель | тоже поддерживаются."
        text = text.replace("🧭 V2 controller", "Контроллер заряда")
        await original_safe_answer(event, text, reply_markup=reply_markup)

    v2_bot_ui._safe_answer = _safe_answer_natural_battery_input
    v2_bot_ui._intent_keyboard = _operator_intent_keyboard
    v2_bot_ui._preview_keyboard = _operator_preview_keyboard

    # Exact saved-battery Start must precede the generic v2_battery_* selector.
    @app.router.callback_query(F.data == "v2_battery_start")
    async def _v2_battery_start_route(call: Any) -> None:
        if not await app._check_chat_and_respond(call):
            return
        await call.answer()
        user_id = call.from_user.id if call.from_user else 0
        pending = v2_bot_ui._pending_start.get(user_id)
        if pending is None:
            await call.answer("Предпросмотр устарел — выберите АКБ заново", show_alert=True)
            return
        if await start_profile_transactional(app, call, pending):
            v2_bot_ui._pending_start.pop(user_id, None)

    v2_bot_ui.install_v2_ui(app)
    install_dashboard_polish(app, v2_bot_ui)

    # Replace the inherited legacy navigation hierarchy with one stable operator panel.
    app._charge_modes_text = _operator_modes_text
    app._build_charge_modes_keyboard = _operator_modes_keyboard

    def _build_operator_dashboard(
        is_on: bool,
        user_id: int,
        *,
        back_to_dashboard: bool = False,
    ) -> InlineKeyboardMarkup:
        return build_operator_dashboard_keyboard(
            app,
            is_on,
            user_id,
            back_to_dashboard=back_to_dashboard,
        )

    app._build_dashboard_keyboard = _build_operator_dashboard

    # A stale legacy profile button can still populate awaiting_ah without an explicit
    # intent. Missing intent is conservative NORMAL, never implicit Recovery.
    installed_handle_ah = app.handle_ah_input

    async def _handle_ah_conservative(message, profile: str, user_id: int) -> None:
        v2_bot_ui._pending_intent.setdefault(user_id, ChargeIntent.NORMAL)
        await installed_handle_ah(message, profile, user_id)

    app.handle_ah_input = _handle_ah_conservative

    # Telegram message order is part of the operator UX: every prompt/notice/detail is
    # allowed to live above the terminal dashboard, but the control panel itself is
    # always restored as the last bot message. This is presentation-only and never
    # actuates HA/RD6018 on its own.
    install_panel_last(app)


async def init_v2_storage() -> None:
    """Create/migrate physical battery and recovery-history tables at startup."""
    await init_battery_registry()
