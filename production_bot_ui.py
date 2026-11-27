from __future__ import annotations

import html
from dataclasses import replace
from pathlib import Path
from typing import Any, Dict

from aiogram import F
from aiogram.exceptions import TelegramBadRequest
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from battery_registry import BatteryRecord, upsert_battery
from pb_domain import (
    BatteryChemistry,
    BatteryCondition,
    BatteryIdentity,
    BatteryLifecycle,
    ChargeIntent,
)
from battery_catalog import list_batteries
from ui_support import (
    battery_button_label,
    build_program_preview,
    format_active_evidence,
    format_battery_card,
    intent_label,
    profile_for_chemistry,
)
from application.intents import OperatorIntent, OperatorIntentKind
from application.operator_read_source import OperatorReadSource
from runtime.charge.profiles.manual import has_manual_profile
from runtime.ui.telegram.charge import (
    CHARGE_CALLBACK_DATA,
    PendingStart,
    _clear_pending_program_state,
    _pending_intent,
    _pending_profile,
    _pending_start,
    legacy_profile_from_callback as _profile_from_callback,
    selected_program_for_user,
)
from runtime.ui.telegram.details import HOME_CALLBACK_DATA
from runtime.ui.telegram.recipe_buttons import (
    _preview_keyboard,
    _recipe_preview_keyboard,
    install_start_recipe_selection_routes,
)

async def _ack_callback(call: Any, *args: Any, **kwargs: Any) -> None:
    """Expired Telegram callback acknowledgement must not abort navigation."""
    try:
        await call.answer(*args, **kwargs)
    except TelegramBadRequest as exc:
        reason = str(exc).lower()
        if "query is too old" not in reason and "query id is invalid" not in reason:
            raise


MANUAL_PROFILE_PATH = Path(__file__).resolve().parent / "config" / "charge" / "manual.yaml"


_new_battery_input: set[int] = set()
_installed = False


# Compatibility exports for existing callback users; presentation-only implementation.
from runtime.ui.telegram.battery_selection import (
    _battery_callback_token,
    _battery_callback_data,
    _battery_rows,
    _battery_pages,
    _selected_battery,
    resolve_battery_callback as _resolve_battery_callback,
    selected_battery_for_user,
)


# Compatibility export: START result formatting is presentation only.
from runtime.ui.components.hmi_values import format_start_feedback


def _intent_keyboard(prefix: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="⚡ Обычный", callback_data=f"{prefix}_normal"),
                InlineKeyboardButton(text="🛠 Recovery", callback_data=f"{prefix}_recovery"),
            ],
            [
                InlineKeyboardButton(text="🔄 Condition", callback_data=f"{prefix}_conditioning"),
                InlineKeyboardButton(text="🔬 Диагностика", callback_data=f"{prefix}_diagnostic"),
            ],
            [InlineKeyboardButton(text="⬅️ Режимы", callback_data=CHARGE_CALLBACK_DATA)],
        ]
    )


def _parse_intent(value: str) -> ChargeIntent:
    return ChargeIntent(str(value).strip().lower())


# Compatibility exports for the legacy pipe-only Telegram form.
# All battery input parsing is owned by battery_input.
from battery_input import (
    _parse_chemistry,
    parse_legacy_pipe_battery_spec as parse_battery_spec,
)


async def _safe_answer(event: Any, text: str, *, reply_markup=None) -> None:
    message = event.message if hasattr(event, "message") and event.message is not None else event
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)


async def _route_profile_intent(app: Any, call: Any, profile: str) -> bool:
    interface = getattr(app, "operator_interface", None)
    submit = getattr(interface, "submit_intent", None)
    if not callable(submit):
        return True
    user = str(getattr(getattr(call, "from_user", None), "id", "0"))
    result = await submit(
        OperatorIntent(OperatorIntentKind.SELECT_CHARGE_PROFILE, "telegram", user, {"profile": profile})
    )
    if getattr(result, "status", None) == "rejected":
        await _ack_callback(call, "Профиль недоступен", show_alert=True)
        return False
    return True


def install_ui_support(
    app: Any,
    *,
    pending_intent_state=None,
    battery_upsert=None,
    battery_spec_parser=None,
    safe_answer=None,
    intent_keyboard=None,
    preview_keyboard=None,
    active_evidence_formatter=None,
    start_route=None,
) -> None:
    """Install the Telegram operator presentation/workflow over the runtime substrate.

    This installer owns presentation and callback composition only. Physical execution
    is submitted through the canonical production start route.
    """
    global _installed
    save_battery = battery_upsert or upsert_battery
    parse_battery = battery_spec_parser or parse_battery_spec
    answer = safe_answer or _safe_answer
    build_intent_keyboard = intent_keyboard or _intent_keyboard
    build_preview_keyboard = preview_keyboard or _preview_keyboard
    pending_intents = pending_intent_state if pending_intent_state is not None else _pending_intent
    format_evidence = active_evidence_formatter or format_active_evidence
    production_start_route = (
        start_route if start_route is not None
        else getattr(app, "_v3_production_start_route", None)
    )
    if _installed:
        return
    _installed = True

    original_dashboard_keyboard = app._build_dashboard_keyboard
    original_progress = app._format_stage_progress_line
    original_handle_ah = app.handle_ah_input
    original_handle_dialog = app.handle_dialog_mode

    def build_dashboard_keyboard(is_on: bool, user_id: int, *, back_to_dashboard: bool = False):
        markup = original_dashboard_keyboard(is_on, user_id, back_to_dashboard=back_to_dashboard)
        rows = list(markup.inline_keyboard)
        insert_at = max(0, len(rows) - (2 if back_to_dashboard else 1))
        return InlineKeyboardMarkup(inline_keyboard=rows)

    def charge_modes_text() -> str:
        return (
            "<b>🧭 Программа заряда</b>\n\n"
            "Сначала выберите химию или сохранённую физическую батарею, затем <b>intent</b>.\n\n"
            "⚡ Normal — полный штатный AUTO; Recovery/Mix включаются только по критериям стратегии.\n"
            "🛠 Recovery — восстановительный intent с HV только в разрешённом recipe/diagnostic envelope.\n"
            "🔄 Conditioning — сервисный режим в recipe envelope.\n"
            "🔬 Diagnostic — без автоматической HV-эскалации.\n\n"
            "В CV финиш оценивается по <b>Imin→ΔI</b>, в CC — по <b>Vmax→ΔV</b>."
        )

    def build_charge_modes_keyboard() -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="🟦 Ca/Ca", callback_data="v2_profile_caca"),
                    InlineKeyboardButton(text="🟧 EFB", callback_data="v2_profile_efb"),
                    InlineKeyboardButton(text="🟥 AGM", callback_data="v2_profile_agm"),
                ],
                [
                    InlineKeyboardButton(text="🔋 Мои АКБ", callback_data="v2_batteries"),
                    InlineKeyboardButton(text="➕ АКБ", callback_data="v2_battery_add"),
                ],
                [
                    InlineKeyboardButton(text="🛠 Ручной MAIN → MIX", callback_data="v2_manual_choose"),
                ],
                [InlineKeyboardButton(text="⬅️ Назад", callback_data=HOME_CALLBACK_DATA)],
            ]
        )

    def format_stage_progress_line(live: Dict[str, Any]) -> str:
        if app.charge_controller.is_active and app.charge_controller.current_stage in {
            app.charge_controller.STAGE_MAIN,
            app.charge_controller.STAGE_MIX,
        }:
            try:
                snap = app.charge_controller.ui_support_snapshot()
                compact = format_evidence(
                    snap,
                    voltage_v=app._safe_float(live.get("battery_voltage")),
                    current_a=app._safe_float(live.get("current")),
                    temp_c=app._safe_float(live.get("temp_ext")),
                )
                return compact
            except Exception:
                pass
        return original_progress(live)

    async def handle_ah_input(message: Any, profile: str, user_id: int) -> None:
        intent = pending_intents.pop(user_id, ChargeIntent.RECOVERY)
        try:
            capacity = float((message.text or "").strip().replace(",", "."))
        except ValueError:
            await original_handle_ah(message, profile, user_id)
            return
        if capacity < 1 or capacity > 500:
            await original_handle_ah(message, profile, user_id)
            return
        app.awaiting_ah.pop(user_id, None)
        pending = PendingStart(
            profile=profile,
            capacity_ah=capacity,
            intent=intent,
            battery_id=f"adhoc:{profile}:{capacity:g}:{user_id}",
            condition=BatteryCondition.UNKNOWN,
        )
        _pending_start[user_id] = pending
        preview = build_program_preview(
            profile=profile,
            capacity_ah=capacity,
            intent=intent,
            condition=BatteryCondition.UNKNOWN,
            battery_id=pending.battery_id,
        )
        await message.answer(
            preview.text,
            parse_mode=ParseMode.HTML,
            reply_markup=build_preview_keyboard("v2_quick_start"),
        )

    app._build_dashboard_keyboard = build_dashboard_keyboard
    app._charge_modes_text = charge_modes_text
    app._build_charge_modes_keyboard = build_charge_modes_keyboard
    app._format_stage_progress_line = format_stage_progress_line
    app.handle_ah_input = handle_ah_input
    from runtime.ui.telegram.battery_selection import install_battery_add_route

    install_battery_add_route(
        app,
        new_battery_input=_new_battery_input,
        acknowledge=_ack_callback,
        answer=answer,
        fallback_handler=original_handle_dialog,
        parse_battery=parse_battery,
        save_battery=save_battery,
        list_saved_batteries=list_batteries,
        format_battery_card=format_battery_card,
        battery_rows=_battery_rows,
        charge_callback_data=CHARGE_CALLBACK_DATA,
    )
    app.handle_dialog_mode = app.handle_battery_add_input

    @app.router.callback_query(F.data == "v2_status")
    async def status_handler(call: Any) -> None:
        if not await app._check_chat_and_respond(call):
            return
        await _ack_callback(call, )
        live = await OperatorReadSource(app).read_live()
        snap = app.charge_controller.ui_support_snapshot()
        text = format_evidence(
            snap,
            voltage_v=app._safe_float(live.get("battery_voltage")),
            current_a=app._safe_float(live.get("current")),
            temp_c=app._safe_float(live.get("temp_ext")),
        )
        await answer(
            call,
            f"<b>🧭 Контроллер заряда</b>\n\n{text}\n\n"
            f"Stage: <code>{html.escape(app.charge_controller.current_stage)}</code>",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="⬅️ Дашборд", callback_data=HOME_CALLBACK_DATA)]]
            ),
        )

    @app.router.callback_query(F.data == "v2_batteries")
    async def batteries_handler(call: Any) -> None:
        if not await app._check_chat_and_respond(call):
            return
        await _ack_callback(call, )
        user_id = call.from_user.id if call.from_user else 0
        records = [r for r in await list_batteries(limit=20) if profile_for_chemistry(r.identity.chemistry)]
        _battery_pages[user_id] = records
        if not records:
            await answer(
                call,
                "<b>🔋 Реестр АКБ пуст.</b>\nДобавьте физическую батарею или используйте быстрый профиль.",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [InlineKeyboardButton(text="➕ Добавить АКБ", callback_data="v2_battery_add")],
                        [InlineKeyboardButton(text="⬅️ Режимы", callback_data=CHARGE_CALLBACK_DATA)],
                    ]
                ),
            )
            return
        rows = _battery_rows(records)
        rows.append([InlineKeyboardButton(text="➕ Добавить АКБ", callback_data="v2_battery_add")])
        rows.append([InlineKeyboardButton(text="⬅️ Режимы", callback_data=CHARGE_CALLBACK_DATA)])
        await answer(
            call,
            "<b>🔋 Физические аккумуляторы</b>\nВыберите батарею:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        )

    app._batteries_handler = batteries_handler

    @app.router.callback_query(
        F.data.startswith("v2_battery_")
        & ~F.data.in_({"v2_battery_add", "v2_battery_start"})
    )
    async def battery_select_handler(call: Any) -> None:
        if not await app._check_chat_and_respond(call):
            return
        await _ack_callback(call, )
        user_id = call.from_user.id if call.from_user else 0
        raw = (call.data or "").replace("v2_battery_", "", 1)
        if raw.startswith("id_"):
            record = await _resolve_battery_callback(raw, user_id)
            if record is None:
                await answer(
                    call,
                    "<b>Список АКБ устарел.</b> Откройте раздел АКБ заново.",
                    reply_markup=InlineKeyboardMarkup(
                        inline_keyboard=[
                            [InlineKeyboardButton(text="🔄 АКБ", callback_data="v2_batteries")],
                            [InlineKeyboardButton(text="⬅️ Режимы", callback_data=CHARGE_CALLBACK_DATA)],
                        ]
                    ),
                )
                return
            records = [record]
            idx = 0
        elif raw.isdigit():
            idx = int(raw)
            records = _battery_pages.get(user_id) or []
            if idx < 0 or idx >= len(records):
                records = [r for r in await list_batteries(limit=200) if profile_for_chemistry(r.identity.chemistry)]
                _battery_pages[user_id] = records
        else:
            return
        if idx < 0 or idx >= len(records):
            await answer(
                call,
                "<b>Список АКБ устарел.</b> Откройте раздел АКБ заново.",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [InlineKeyboardButton(text="🔄 АКБ", callback_data="v2_batteries")],
                        [InlineKeyboardButton(text="⬅️ Режимы", callback_data=CHARGE_CALLBACK_DATA)],
                    ]
                ),
            )
            return
        record = records[idx]
        _selected_battery[user_id] = record
        manual_button = []
        if has_manual_profile(MANUAL_PROFILE_PATH, record.identity.battery_id):
            manual_button = [[InlineKeyboardButton(
                text="▶️ Запустить сохранённый Manual",
                callback_data="v2_battery_manual",
            )]]
        await answer(
            call,
            f"{format_battery_card(record)}\n\n<b>Что делаем?</b>",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=manual_button + build_intent_keyboard("v2_bat_intent").inline_keyboard
            ),
        )
    async def _select_quick_profile(call: Any, profile: str) -> None:
        if not await app._check_chat_and_respond(call):
            return
        await _ack_callback(call, )
        if profile not in {"Ca/Ca", "EFB", "AGM"}:
            await _ack_callback(call, "Неизвестный профиль", show_alert=True)
            return
        if not await _route_profile_intent(app, call, profile):
            return
        user_id = call.from_user.id if call.from_user else 0
        _pending_profile[user_id] = profile
        await answer(
            call,
            f"<b>{html.escape(profile)}</b>\nВыберите intent. Normal — полный штатный AUTO; стандартный Recovery/Mix используется только по критериям стратегии.",
            reply_markup=build_intent_keyboard("v2_quick_intent"),
        )

    app._select_quick_profile = _select_quick_profile

    @app.router.callback_query(F.data.startswith("v2_profile_"))
    async def quick_profile_handler(call: Any) -> None:
        profile = _profile_from_callback(call.data or "")
        if not profile:
            return
        await _select_quick_profile(call, profile)

    @app.router.callback_query(F.data.startswith("v2_quick_intent_"))
    async def quick_intent_handler(call: Any) -> None:
        if not await app._check_chat_and_respond(call):
            return
        await _ack_callback(call, )
        user_id = call.from_user.id if call.from_user else 0
        profile = _pending_profile.get(user_id)
        if not profile:
            await _ack_callback(call, "Сначала выберите профиль", show_alert=True)
            return
        intent = _parse_intent((call.data or "").replace("v2_quick_intent_", "", 1))
        _pending_intent[user_id] = intent
        app.awaiting_ah[user_id] = profile
        await answer(
            call,
            f"{html.escape(intent_label(intent))} · <b>{html.escape(profile)}</b>\n\nВведите ёмкость АКБ в Ah. После ввода покажу программу перед запуском.",
        )

    @app.router.callback_query(F.data == "v2_quick_start")
    async def quick_start_handler(call: Any) -> None:
        trace = getattr(app, "logger", None)
        if trace is not None:
            trace.info("QUICK_START_TRACE enter")
        if not await app._check_chat_and_respond(call):
            if trace is not None:
                trace.info("QUICK_START_TRACE chat_guard=DENY")
            return
        if trace is not None:
            trace.info("QUICK_START_TRACE chat_guard=PASS")
        await _ack_callback(call, )
        user_id = call.from_user.id if call.from_user else 0
        message = getattr(call, "message", None)
        if trace is not None:
            trace.info("QUICK_START_TRACE user_state user_id=%s", user_id)
        pending = _pending_start.get(user_id)
        if trace is not None:
            if pending is None:
                trace.info("QUICK_START_TRACE pending=MISS")
            else:
                trace.info(
                    "QUICK_START_TRACE pending=FOUND profile=%s intent=%s capacity_ah=%s battery_id=%s",
                    pending.profile,
                    pending.intent.value,
                    pending.capacity_ah,
                    pending.battery_id,
                )
        if pending is None:
            await _ack_callback(call, "Preview устарел — выберите режим заново", show_alert=True)
            return
        route = production_start_route
        if trace is not None:
            trace.info("QUICK_START_TRACE route=%s", "FOUND" if route is not None else "MISSING")
        if route is None:
            await _ack_callback(call, "START route is not installed", show_alert=True)
            return
        intent = OperatorIntent(
            OperatorIntentKind.START_CHARGE,
            "telegram",
            str(user_id),
            {
                "profile": pending.profile,
                "capacity_ah": pending.capacity_ah,
                "battery_identity": None,
                "battery_id": pending.battery_id,
                "intent": pending.intent,
                "condition": pending.condition,
            },
        )
        if trace is not None:
            trace.info(
                "QUICK_START_TRACE request profile=%s intent=%s capacity_ah=%s",
                pending.profile,
                pending.intent.value,
                pending.capacity_ah,
            )
        try:
            result = await route.submit(intent)
        except Exception as exc:
            if trace is not None:
                trace.info("QUICK_START_TRACE route=EXCEPTION type=%s", type(exc).__name__)
            raise
        if trace is not None:
            trace.info(
                "QUICK_START_TRACE result accepted=%s reason=%s mode=%s",
                result.accepted,
                result.reason,
                getattr(getattr(result.port_result, "mode", None), "value", None),
            )
        if not result.accepted:
            if message is not None:
                await message.answer(format_start_feedback(result), parse_mode=None)
            if trace is not None:
                trace.info("QUICK_START_TRACE response=REJECTED")
            return
        _clear_pending_program_state(app, user_id)
        if trace is not None:
            trace.info("QUICK_START_TRACE pending=CLEARED after_route=PASS")
        # Do not render a panel before the START result. The terminal
        # navigation middleware publishes the authoritative graph/control
        # panel once, after this handler has delivered feedback.
        # The route owns preflight and transactional safety; the callback only
        # submits the operator intent and never touches hardware directly.
        # The callback was acknowledged before the transactional START.  That
        # transaction can outlive Telegram's callback-query window; send its
        # result as a chat message instead of answering an expired query.
        if message is not None:
            await message.answer(format_start_feedback(result), parse_mode=None)
        if trace is not None:
            trace.info("QUICK_START_TRACE response=ACCEPTED")

    install_start_recipe_selection_routes(
        app,
        pending_start=_pending_start,
        acknowledge=_ack_callback,
        answer=answer,
        preview_keyboard=build_preview_keyboard,
    )

    @app.router.callback_query(F.data.startswith("v2_bat_intent_"))
    async def battery_intent_handler(call: Any) -> None:
        if not await app._check_chat_and_respond(call):
            return
        user_id = call.from_user.id if call.from_user else 0
        record = _selected_battery.get(user_id)
        if record is None:
            await _ack_callback(call, "Сначала выберите АКБ", show_alert=True)
            return
        profile = profile_for_chemistry(record.identity.chemistry)
        if profile is None:
            await _ack_callback(call, "Для этой химии пока нет auto-profile", show_alert=True)
            return
        await _ack_callback(call)
        intent = _parse_intent((call.data or "").replace("v2_bat_intent_", "", 1))
        pending = PendingStart(
            profile=profile,
            capacity_ah=record.identity.nominal_capacity_ah,
            intent=intent,
            battery_id=record.identity.battery_id,
            condition=record.lifecycle.condition,
        )
        _pending_start[user_id] = pending
        preview = build_program_preview(
            profile=profile,
            capacity_ah=pending.capacity_ah,
            intent=intent,
            condition=pending.condition,
            battery_id=pending.battery_id,
        )
        await answer(
            call,
            f"{format_battery_card(record)}\n\n{preview.text}",
            reply_markup=_recipe_preview_keyboard(app, "v2_battery_start"),
        )
