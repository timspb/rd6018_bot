from __future__ import annotations

import hashlib
import html
from dataclasses import replace
from typing import Any, Awaitable, Callable, Dict

from aiogram import F
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message, TelegramObject

from battery_registry import get_battery
from manual_mode import ManualChargeRequest, ManualSessionState
from manual_runtime import ProductionManualSessionManager, ProductionManualUIRoute
from manual_text import (
    MANUAL_PROFILE_PATH,
    install_manual_text,
    ParsedManualCommand,
    _format_start,
    manual_help_text,
    parse_manual_command,
)
from runtime.charge.profiles.manual import load_manual_profile
from runtime.ui.telegram.charge import CHARGE_CALLBACK_DATA
from production_bot_ui import selected_battery_for_user
from battery_catalog import list_batteries


def _token(battery_id: str) -> str:
    return hashlib.sha256(str(battery_id).encode("utf-8")).hexdigest()[:12]


def _manual_request_summary(manager: ProductionManualSessionManager) -> str:
    request = manager.request
    if request is None:
        return "Сохранённого Manual-запроса нет."
    stop = request.stop
    conditions = []
    if stop.max_active_seconds is not None:
        conditions.append(f"T={stop.max_active_seconds / 3600.0:.2f}h active")
    if stop.voltage_ge_v is not None:
        conditions.append(f"V>={stop.voltage_ge_v:.2f}")
    if stop.voltage_le_v is not None:
        conditions.append(f"V<={stop.voltage_le_v:.2f}")
    if manager.reach_voltage_v is not None:
        conditions.append(f"V={manager.reach_voltage_v:.2f} reach")
    if stop.current_ge_a is not None:
        conditions.append(f"I>={stop.current_ge_a:.2f}")
    if stop.current_le_a is not None:
        conditions.append(f"I<={stop.current_le_a:.2f}")
    if manager.reach_current_a is not None:
        conditions.append(f"I={manager.reach_current_a:.2f} reach")
    if stop.delta is not None:
        conditions.append(f"delta={stop.delta:.3f}")
    battery = html.escape(request.battery_id) if request.battery_id else "без привязки"
    stop_text = html.escape(", ".join(conditions) if conditions else "только operator stop / hard safety")
    return (
        "<b>Прерванный Manual</b>\n"
        f"U={request.voltage_v:.2f} V · I={request.current_a:.2f} A\n"
        f"OVP={request.ovp_v:.2f} V · OCP={request.ocp_a:.2f} A\n"
        f"АКБ: <code>{battery}</code>\n"
        f"Stop: <code>{stop_text}</code>\n\n"
        "Перезапуск процесса не продолжает старый выход. Повторный запуск требует "
        "явного подтверждения и заново проходит telemetry/safety/readback/Output verification. "
        "Таймер активного времени начинается заново."
    )


def install_manual_context_ui(app: Any) -> None:
    if getattr(app, "_manual_context_ui_installed", False):
        return
    middleware = install_manual_text(app)
    token_map: Dict[tuple[int, str], str] = {}

    base_builder = app._build_charge_modes_keyboard

    def _build_modes_with_manual_context() -> InlineKeyboardMarkup:
        markup = base_builder()
        rows = []
        for row in markup.inline_keyboard:
            replaced_row = []
            for button in row:
                replaced_row.append(button)
            rows.append(replaced_row)
        manager = getattr(app, "manual_session_manager", None)
        if isinstance(manager, ProductionManualSessionManager) and manager.state is ManualSessionState.INTERRUPTED:
            rows.insert(
                max(0, len(rows) - 1),
                [InlineKeyboardButton(text="↻ Прерванный Manual", callback_data="v2_manual_interrupted")],
            )
        return InlineKeyboardMarkup(inline_keyboard=rows)

    app._build_charge_modes_keyboard = _build_modes_with_manual_context

    @app.router.callback_query(F.data == "v2_manual_choose")
    async def _manual_choose(call: CallbackQuery) -> None:
        if not await app._check_chat_and_respond(call):
            return
        await call.answer()
        user_id = call.from_user.id if call.from_user else 0
        records = await list_batteries(limit=30)
        rows = [[InlineKeyboardButton(text="Без привязки к АКБ", callback_data="v2_manual_unbound")]]
        for record in records:
            battery_id = record.identity.battery_id
            tok = _token(battery_id)
            token_map[(user_id, tok)] = battery_id
            label = f"{battery_id} · {record.identity.chemistry.value} · {record.identity.nominal_capacity_ah:g}Ah"
            rows.append([InlineKeyboardButton(text=label[:55], callback_data=f"v2_mbind:{tok}")])
        rows.append([InlineKeyboardButton(text="⬅ К программам", callback_data=CHARGE_CALLBACK_DATA)])
        await call.message.answer(
            "<b>Manual: привязка к истории</b>\n\n"
            "Можно выбрать физическую АКБ только для longitudinal history/diagnostics. "
            "Её chemistry/Ah не меняют Manual V/I и не дают дополнительных разрешений.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        )

    app._manual_choose_handler = _manual_choose

    @app.router.callback_query(F.data == "v2_manual_unbound")
    async def _manual_unbound(call: CallbackQuery) -> None:
        if not await app._check_chat_and_respond(call):
            return
        await call.answer()
        user_id = call.from_user.id if call.from_user else 0
        generic = getattr(app, "_manual_text_middleware", None)
        if generic is not None:
            generic.pending_users.add(user_id)
        await call.message.answer(manual_help_text())

    @app.router.callback_query(F.data.startswith("v2_mbind:"))
    async def _manual_bind(call: CallbackQuery) -> None:
        if not await app._check_chat_and_respond(call):
            return
        await call.answer()
        user_id = call.from_user.id if call.from_user else 0
        tok = str(call.data).split(":", 1)[1]
        battery_id = token_map.get((user_id, tok))
        if not battery_id or await get_battery(battery_id) is None:
            await call.answer("Список устарел — откройте Manual заново", show_alert=True)
            return
        middleware.pending_battery[user_id] = battery_id
        await call.message.answer(
            f"<b>Manual для истории АКБ <code>{html.escape(battery_id)}</code></b>\n"
            "Параметры этого Manual сохранятся отдельно для выбранной АКБ.\n\n"
            + manual_help_text()
        )

    @app.router.callback_query(F.data == "v2_battery_manual")
    async def _start_saved_battery_manual(call: CallbackQuery) -> None:
        if not await app._check_chat_and_respond(call):
            return
        await call.answer()
        user_id = call.from_user.id if call.from_user else 0
        record = selected_battery_for_user(user_id)
        if record is None:
            await call.answer("Сначала выберите АКБ", show_alert=True)
            return
        battery_id = record.identity.battery_id
        try:
            profile = load_manual_profile(MANUAL_PROFILE_PATH, battery_id=battery_id)
        except (OSError, ValueError) as exc:
            await call.message.answer(f"❌ Сохранённый Manual не прочитан: {html.escape(str(exc))}")
            return
        manager = getattr(app, "manual_session_manager", None)
        if not isinstance(manager, ProductionManualSessionManager):
            await call.message.answer("❌ V2 Manual runtime не инициализирован.")
            return
        route = getattr(app, "manual_ui_route", None)
        if not isinstance(route, ProductionManualUIRoute) or route.manager is not manager:
            await call.message.answer("Manual application route unavailable.")
            return
        request = ManualChargeRequest.from_profile(
            profile, battery_id=battery_id,
            capacity_ah=record.identity.nominal_capacity_ah,
        )
        result = await route.submit_request(
            request, chat_id=call.message.chat.id, user_id=user_id
        )
        enabled = result.accepted
        if not enabled:
            await call.message.answer("❌ Manual не запущен: safety/readback transaction не подтверждён.")
            return
        app.last_chat_id = call.message.chat.id
        app.last_user_id = user_id
        await call.message.answer(
            _format_start(
                ParsedManualCommand(
                    request=ManualChargeRequest.from_profile(
                        profile,
                        battery_id=battery_id,
                        capacity_ah=record.identity.nominal_capacity_ah,
                    )
                ),
                replaced=False,
            ) + f"\nАКБ: <code>{html.escape(battery_id)}</code>"
        )
        show_now = getattr(app, "_build_and_send_dashboard", None)
        if callable(show_now):
            await show_now(call.message.chat.id, user_id)

    @app.router.callback_query(F.data == "v2_manual_interrupted")
    async def _manual_interrupted(call: CallbackQuery) -> None:
        if not await app._check_chat_and_respond(call):
            return
        await call.answer()
        manager = getattr(app, "manual_session_manager", None)
        if not isinstance(manager, ProductionManualSessionManager) or manager.state is not ManualSessionState.INTERRUPTED:
            await call.answer("Прерванного Manual больше нет", show_alert=True)
            return
        await call.message.answer(
            _manual_request_summary(manager),
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="▶ Авторизовать заново", callback_data="v2_manual_reauthorize")],
                    [InlineKeyboardButton(text="🗑 Отменить запрос", callback_data="v2_manual_discard")],
                    [InlineKeyboardButton(text="⬅ К программам", callback_data=CHARGE_CALLBACK_DATA)],
                ]
            ),
        )

    app._manual_interrupted_handler = _manual_interrupted

    @app.router.callback_query(F.data == "v2_manual_reauthorize")
    async def _manual_reauthorize(call: CallbackQuery) -> None:
        if not await app._check_chat_and_respond(call):
            return
        await call.answer()
        manager = getattr(app, "manual_session_manager", None)
        if not isinstance(manager, ProductionManualSessionManager) or manager.state is not ManualSessionState.INTERRUPTED:
            await call.answer("Запрос уже изменился — откройте Manual заново", show_alert=True)
            return
        request = manager.request
        if request is None:
            await call.answer("Сохранённый запрос повреждён", show_alert=True)
            return
        if request.battery_id and await get_battery(request.battery_id) is None:
            await call.message.answer(
                "❌ Сохранённая привязка к АКБ больше не существует. "
                "Создайте новый Manual без привязки либо выберите актуальную АКБ."
            )
            return
        route = getattr(app, "manual_ui_route", None)
        if not isinstance(route, ProductionManualUIRoute) or route.manager is not manager:
            await call.message.answer("Manual application route unavailable.")
            return
        result = await route.submit_request(
            request,
            chat_id=call.message.chat.id,
            user_id=call.from_user.id if call.from_user else 0,
            reach_voltage_v=manager.reach_voltage_v,
            reach_current_a=manager.reach_current_a,
        )
        enabled = result.accepted
        if not enabled:
            await call.message.answer(
                "❌ Manual не возобновлён: fresh safety/readback transaction не подтверждён."
            )
            return
        app.last_chat_id = call.message.chat.id
        app.last_user_id = call.from_user.id if call.from_user else 0
        await call.message.answer(
            "<b>🛠 Manual заново авторизован</b>\n"
            "Сохранённые V/I/stop conditions применены через новый safety/readback transaction. "
            "Active-time таймер начат заново."
        )

    @app.router.callback_query(F.data == "v2_manual_discard")
    async def _manual_discard(call: CallbackQuery) -> None:
        if not await app._check_chat_and_respond(call):
            return
        await call.answer()
        manager = getattr(app, "manual_session_manager", None)
        if not isinstance(manager, ProductionManualSessionManager) or manager.state is not ManualSessionState.INTERRUPTED:
            await call.answer("Прерванного запроса больше нет", show_alert=True)
            return
        route = getattr(app, "manual_ui_route", None)
        if not isinstance(route, ProductionManualUIRoute) or route.manager is not manager:
            await call.message.answer("Manual application route unavailable.")
            return
        confirmed = await route.discard_interrupted()
        await call.message.answer(
            "🗑 Прерванный Manual отменён; Output подтверждён OFF."
            if confirmed
            else "⚠️ Запрос отменён, но подтверждение Output OFF не получено — проверьте RD6018."
        )

    app._manual_context_ui_installed = True
