from __future__ import annotations

import asyncio
import time
from datetime import datetime
from typing import Any

from aiogram import F
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

import v2_bot_ui
from battery_diagnostics_store import init_battery_diagnostics_store
from battery_registry import init_battery_registry, upsert_battery as registry_upsert_battery
from diagnostic_controller import DiagnosticProductionChargeControllerV2
from manual_runtime_v2 import ProductionManualSessionManager
from manual_text_v2 import install_manual_text_v2
from pb_domain import ChargeIntent
from runtime_safety_v2 import install_v2_runtime_safety
from telegram_panel import install_panel_last
from v2_battery_input import parse_battery_spec
from v2_sg_ui import install_sg_ui, sg_menu_button
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
        "Диагностика — наблюдение без автоматического перехода на высокое напряжение.\n\n"
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
                sg_menu_button(),
            ],
            [
                InlineKeyboardButton(text="Ручной режим", callback_data="v2_manual"),
                InlineKeyboardButton(text="Условие OFF", callback_data="menu_off"),
            ],
            [InlineKeyboardButton(text="⬅ К панели", callback_data="charge_back")],
        ]
    )


async def _managed_aware_charge_monitor_poll(app: Any) -> None:
    """Run one legacy informational-monitor poll without contradicting managed control."""
    live = await app.hass.get_all_live()
    output_on = str(live.get("switch", "")).lower() == "on"
    battery_v = app._safe_float(live.get("battery_voltage"))
    current_a = app._safe_float(live.get("current"))
    now = datetime.now()

    if not output_on:
        app.zero_current_since = None
        return

    manual = getattr(app, "manual_session_manager", None)
    manual_active = bool(manual is not None and manual.is_active)
    if app.charge_controller.is_active or manual_active:
        app.zero_current_since = None
        return

    if current_a <= 0.0:
        if app.zero_current_since is None:
            app.zero_current_since = now
        elif (now - app.zero_current_since).total_seconds() >= app.ZERO_CURRENT_THRESHOLD_MINUTES * 60:
            if not app.last_idle_alert_at or (now - app.last_idle_alert_at) >= app.IDLE_ALERT_COOLDOWN:
                msg = (
                    "⚠️ Выход включен, но потребление отсутствует. "
                    "Не забудьте выключить прибор."
                )
                app.logger.info("Charge monitor (idle): %s", msg)
                app.last_idle_alert_at = now
                app._charge_notify(msg)
    else:
        app.zero_current_since = None

    if battery_v >= 13.5 and current_a < 0.1:
        cooldown = app.STORAGE_ALERT_COOLDOWN if battery_v < 14.0 else app.CHARGE_ALERT_COOLDOWN
        if app.last_charge_alert_at and (now - app.last_charge_alert_at) < cooldown:
            return
        msg = (
            f"⚠️ Заряд завершён или аккумулятор почти полон. "
            f"Ток упал до {current_a:.2f}А при напряжении {battery_v:.2f}В."
        )
        app.logger.info("Charge monitor (unmanaged): %s", msg)
        app.last_charge_alert_at = now
        app._charge_notify(msg)


def _install_managed_charge_monitor_guard(app: Any) -> None:
    if getattr(app, "_v2_managed_charge_monitor_guard_installed", False):
        return

    async def managed_aware_charge_monitor() -> None:
        while True:
            await asyncio.sleep(15 * 60)
            try:
                await _managed_aware_charge_monitor_poll(app)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                app.logger.error("charge_monitor (network/error): %s", exc)
                await asyncio.sleep(60)

    app.charge_monitor = managed_aware_charge_monitor
    app._v2_managed_charge_monitor_guard_installed = True


def install_v2(app: Any, *, install_ui: bool = True) -> None:
    """Install production V2 controller/safety and the operator-facing Telegram UI."""
    if not isinstance(app.charge_controller, DiagnosticProductionChargeControllerV2):
        app.charge_controller = DiagnosticProductionChargeControllerV2(
            app.hass,
            notify_cb=app._charge_notify,
        )

    if not isinstance(
        getattr(app, "manual_session_manager", None),
        ProductionManualSessionManager,
    ):
        app.manual_session_manager = ProductionManualSessionManager(app)

    # The old five-step Custom dialog is retained only as a stale-message/rollback
    # compatibility surface. Its final action is first-class Manual authority, never the
    # chemistry-aware Custom/Main FSM. Current V2 UI uses the native Manual command DSL.
    app.start_custom_charge = app.manual_session_manager.start_from_legacy_ui

    install_v2_runtime_safety(app)
    _install_managed_charge_monitor_guard(app)
    install_manual_text_v2(app)

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

    original_safe_answer = v2_bot_ui._safe_answer

    async def _safe_answer_operator(event, text: str, *, reply_markup=None) -> None:
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

        replacements = {
            "🧭 V2 controller": "Контроллер заряда",
            "Stage:": "Этап:",
            "Выберите intent. Высоковольтный этап доступен только Recovery/Conditioning.": (
                "Выберите цель программы. Высоковольтный этап доступен только для "
                "восстановления или кондиционирования."
            ),
            "Preview устарел": "Предпросмотр устарел",
            "auto-profile": "автоматической программы",
        }
        for old, new in replacements.items():
            text = text.replace(old, new)
        await original_safe_answer(event, text, reply_markup=reply_markup)

    v2_bot_ui._safe_answer = _safe_answer_operator
    v2_bot_ui._intent_keyboard = _operator_intent_keyboard
    v2_bot_ui._preview_keyboard = _operator_preview_keyboard

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
    install_sg_ui(app)
    install_dashboard_polish(app, v2_bot_ui)

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

    installed_handle_ah = app.handle_ah_input

    async def _handle_ah_conservative(message, profile: str, user_id: int) -> None:
        v2_bot_ui._pending_intent.setdefault(user_id, ChargeIntent.NORMAL)
        await installed_handle_ah(message, profile, user_id)

    app.handle_ah_input = _handle_ah_conservative

    install_panel_last(app)


async def init_v2_storage() -> None:
    """Create/migrate physical battery, recovery and diagnostic evidence storage."""
    await init_battery_registry()
    await init_battery_diagnostics_store()
