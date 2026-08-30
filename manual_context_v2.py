from __future__ import annotations

import hashlib
import html
from dataclasses import replace
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware, F
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message, TelegramObject

from battery_registry import get_battery
from manual_mode import ManualChargeRequest, ManualSessionState
from manual_runtime_v2 import ProductionManualSessionManager
from manual_text_v2 import ParsedManualCommand, _format_start, manual_help_text, parse_manual_command
from v2_battery_catalog import list_batteries


class BoundManualTextMiddleware(BaseMiddleware):
    """Own the next Manual text when the operator selected a physical battery first.

    Battery identity is longitudinal metadata only. It never imports chemistry targets,
    capacity-derived current, intent, or any other AUTO authority into Manual.
    """

    def __init__(self, app: Any) -> None:
        self.app = app
        self.pending_battery: Dict[int, str] = {}

    @staticmethod
    def _carries_stop(parsed: ParsedManualCommand) -> bool:
        stop = parsed.request.stop
        return (
            parsed.reach_voltage_v is not None
            or parsed.reach_current_a is not None
            or any(
                value is not None
                for value in (
                    stop.max_active_seconds,
                    stop.voltage_ge_v,
                    stop.voltage_le_v,
                    stop.current_ge_a,
                    stop.current_le_a,
                    stop.delta,
                )
            )
        )

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        if not isinstance(event, Message) or not event.text:
            return await handler(event, data)
        user_id = event.from_user.id if event.from_user else 0
        battery_id = self.pending_battery.get(user_id)
        if not battery_id:
            return await handler(event, data)
        if event.text.strip().startswith("/"):
            return await handler(event, data)

        try:
            parsed = parse_manual_command(event.text)
        except ValueError as exc:
            self.pending_battery.pop(user_id, None)
            await event.answer(f"❌ {html.escape(str(exc))}\n\n{manual_help_text()}")
            return None
        if parsed is None:
            self.pending_battery.pop(user_id, None)
            await event.answer("❌ Не распознал параметры Manual.\n\n" + manual_help_text())
            return None

        self.pending_battery.pop(user_id, None)
        if not await self.app._check_chat_and_respond(event):
            return None
        if await get_battery(battery_id) is None:
            await event.answer(
                "❌ Выбранная сохранённая АКБ больше не найдена. "
                "Откройте Manual заново и выберите актуальную запись."
            )
            return None

        manager = getattr(self.app, "manual_session_manager", None)
        if not isinstance(manager, ProductionManualSessionManager):
            await event.answer("❌ V2 Manual runtime не инициализирован.")
            return None

        bound_request = replace(parsed.request, battery_id=battery_id)
        bound = ParsedManualCommand(
            request=bound_request,
            reach_voltage_v=parsed.reach_voltage_v,
            reach_current_a=parsed.reach_current_a,
        )
        if self._carries_stop(bound):
            clear_overlay = getattr(self.app, "_clear_manual_off", None)
            if callable(clear_overlay):
                clear_overlay()

        replaced_active = manager.is_active
        try:
            if replaced_active:
                enabled = await manager.replace(
                    bound.request,
                    reach_voltage_v=bound.reach_voltage_v,
                    reach_current_a=bound.reach_current_a,
                )
            else:
                enabled = await manager.start(
                    bound.request,
                    reach_voltage_v=bound.reach_voltage_v,
                    reach_current_a=bound.reach_current_a,
                )
        except (RuntimeError, ValueError) as exc:
            await event.answer(f"❌ Manual не запущен: {html.escape(str(exc))}")
            return None
        if not enabled:
            await event.answer(
                "❌ Manual не запущен: безопасное программирование/включение RD6018 не подтверждено."
            )
            return None

        self.app.last_chat_id = event.chat.id
        self.app.last_user_id = user_id
        await event.answer(
            _format_start(bound, replaced=replaced_active)
            + f"\nАКБ: <code>{html.escape(battery_id)}</code> (только history identity)"
        )
        schedule = getattr(self.app, "schedule_dashboard_after_60", None)
        if callable(schedule):
            schedule(event.chat.id, user_id)
        return None


def install_manual_context_preprocessor(app: Any) -> BoundManualTextMiddleware:
    existing = getattr(app, "_v2_bound_manual_middleware", None)
    if isinstance(existing, BoundManualTextMiddleware):
        return existing
    middleware = BoundManualTextMiddleware(app)
    # Must be registered before manual_text_v2 so a battery-bound request owns its
    # numeric payload before the generic Manual parser sees the same message.
    app.router.message.outer_middleware.register(middleware)
    app._v2_bound_manual_middleware = middleware
    return middleware


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
    if getattr(app, "_v2_manual_context_ui_installed", False):
        return
    middleware = install_manual_context_preprocessor(app)
    token_map: Dict[tuple[int, str], str] = {}

    base_builder = app._build_charge_modes_keyboard

    def _build_modes_with_manual_context() -> InlineKeyboardMarkup:
        markup = base_builder()
        rows = []
        for row in markup.inline_keyboard:
            replaced_row = []
            for button in row:
                if button.callback_data == "v2_manual":
                    replaced_row.append(
                        InlineKeyboardButton(text=button.text, callback_data="v2_manual_choose")
                    )
                else:
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
        rows.append([InlineKeyboardButton(text="⬅ К программам", callback_data="charge_modes")])
        await call.message.answer(
            "<b>Manual: привязка к истории</b>\n\n"
            "Можно выбрать физическую АКБ только для longitudinal history/diagnostics. "
            "Её chemistry/Ah не меняют Manual V/I и не дают дополнительных разрешений.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        )

    @app.router.callback_query(F.data == "v2_manual_unbound")
    async def _manual_unbound(call: CallbackQuery) -> None:
        if not await app._check_chat_and_respond(call):
            return
        await call.answer()
        user_id = call.from_user.id if call.from_user else 0
        generic = getattr(app, "_v2_manual_text_middleware", None)
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
            "V/I всё равно задаёт оператор; профиль АКБ не меняет уставки.\n\n"
            + manual_help_text()
        )

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
                    [InlineKeyboardButton(text="⬅ К программам", callback_data="charge_modes")],
                ]
            ),
        )

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
        try:
            enabled = await manager.start(
                request,
                reach_voltage_v=manager.reach_voltage_v,
                reach_current_a=manager.reach_current_a,
            )
        except (RuntimeError, ValueError) as exc:
            await call.message.answer(f"❌ Manual не возобновлён: {html.escape(str(exc))}")
            return
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
        confirmed = await manager.stop("interrupted_manual_discarded")
        await call.message.answer(
            "🗑 Прерванный Manual отменён; Output подтверждён OFF."
            if confirmed
            else "⚠️ Запрос отменён, но подтверждение Output OFF не получено — проверьте RD6018."
        )

    app._v2_manual_context_ui_installed = True
