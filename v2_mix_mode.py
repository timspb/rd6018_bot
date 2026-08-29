from __future__ import annotations

import html
from dataclasses import dataclass
from typing import Any, Dict, Optional

from aiogram import F
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from battery_fault_engine import DiagnosticAuthority
from legacy_recipe_adapter import chemistry_for_legacy_profile
from pb_domain import BatteryCondition, BatteryIdentity, ChargeContext, ChargeIntent
from recipe_engine import select_recipe_envelope
from safe_output import snapshot_from_live
from v2_battery_catalog import list_batteries
from v2_ui import battery_button_label, profile_for_chemistry


MIX_ONLY_MIN_START_V = 12.0
MIX_TARGETS_V = {
    "Ca/Ca": 16.5,
    "EFB": 16.5,
    "AGM": 16.3,
}
MIX_LIMIT_HOURS = {
    "Ca/Ca": 20.0,
    "EFB": 24.0,
    "AGM": 10.0,
}


@dataclass(frozen=True)
class PendingMixStart:
    profile: str
    capacity_ah: float
    battery_id: str
    condition: BatteryCondition = BatteryCondition.UNKNOWN


_mix_battery_pages: Dict[int, list[Any]] = {}
_mix_awaiting_ah: Dict[int, str] = {}
_mix_pending_start: Dict[int, PendingMixStart] = {}
_installed = False


def _profile_from_callback(data: str) -> Optional[str]:
    return {
        "v2_mix_profile_caca": "Ca/Ca",
        "v2_mix_profile_efb": "EFB",
        "v2_mix_profile_agm": "AGM",
    }.get(str(data or ""))


def _mix_current_a(capacity_ah: float) -> float:
    return min(12.0, max(0.1, float(capacity_ah) * 0.03))


def build_mix_only_preview(pending: PendingMixStart) -> str:
    target_v = MIX_TARGETS_V[pending.profile]
    target_i = _mix_current_a(pending.capacity_ah)
    limit_h = MIX_LIMIT_HOURS[pending.profile]
    return (
        f"<b>Автоматический Mix · {html.escape(pending.profile)} {pending.capacity_ah:g} Ah</b>\n\n"
        "<b>Старт сразу с Mix.</b> PREP, Main и промежуточные Recovery/Desulfation "
        "в этой программе не выполняются.\n"
        f"Минимальное Uакб для запуска: <b>{MIX_ONLY_MIN_START_V:.1f} V</b>. "
        "Ниже этого порога запуск отклоняется, без скрытого перехода в PREP.\n\n"
        f"Mix: до <b>{target_v:.1f} V</b> · ток ~0.03C ({target_i:.2f} A, max 12 A).\n"
        "CV: Imin → подтверждённый ΔI. CC: Vmax → подтверждённый ΔV.\n"
        "Нужно 3 разнесённых подтверждения; затем sticky-выдержка 2 ч.\n"
        f"Если Delta не сформировалась: fallback максимум <b>{limit_h:g} ч</b>.\n\n"
        "Завершение: Mix → SAFE_WAIT (до 2 ч) → Storage ~13.8 V / 1 A, Output ON.\n"
        "Перед включением действуют обычные V2 safety/readback/watchdog и diagnostic HV veto."
    )


async def _confirm_failed_start_is_off(app: Any) -> bool:
    try:
        return bool(await app.hass.turn_off(app.ENTITY_MAP["switch"]))
    except Exception:
        return False


async def _automatic_hv_block_reason(controller: Any) -> Optional[str]:
    refresh = getattr(controller, "_refresh_stored_diagnostics", None)
    if callable(refresh):
        await refresh()
    assessment = getattr(controller, "battery_fault_assessment", None)
    if assessment is None:
        return None
    if assessment.authority is not DiagnosticAuthority.BLOCK_AUTOMATIC_HV:
        return None
    reasons = ", ".join(getattr(assessment, "authority_reasons", ()) or ())
    return reasons or "confirmed cell-fault evidence"


def _begin_mix_only_controller_session(
    controller: Any,
    *,
    profile: str,
    capacity_ah: float,
    battery_v: float,
    current_a: float,
    temp_ext_c: float,
    ah_now: float,
) -> None:
    """Create a truthful Mix-first session without ever entering PREP/Main."""
    controller._init_session(
        profile,
        int(round(capacity_ah)),
        controller.STAGE_MIX,
    )
    controller._session_start_reason = "Automatic Mix"
    now = float(controller.stage_start_time)
    controller._start_ah = float(ah_now)
    controller._stage_start_ah = float(ah_now)
    controller._stage_start_voltage = float(battery_v)
    controller._stage_start_current = float(current_a)
    controller._stage_start_temp = float(temp_ext_c)
    controller._reset_delta_and_blanking(now)

    begin_trace = getattr(controller, "_begin_trace_identity", None)
    if callable(begin_trace):
        begin_trace()
    init_shadow = getattr(controller, "_initialize_shadow_session", None)
    if callable(init_shadow):
        init_shadow(started_at=getattr(controller, "_v2_trace_started_at", now))


async def start_mix_transactional(app: Any, event: Any, pending: PendingMixStart) -> bool:
    """Start Mix directly through the same protected V2 Output-enable boundary."""
    message = event.message if hasattr(event, "message") and event.message is not None else event
    user = getattr(event, "from_user", None) or getattr(message, "from_user", None)
    user_id = user.id if user else 0
    controller = app.charge_controller

    if controller.is_active:
        await message.answer("⚠️ Сначала остановите текущую программу.")
        return False

    live = await app.hass.get_all_live()
    snapshot = snapshot_from_live(live)
    if snapshot is None:
        await message.answer(
            "❌ Нет полного набора защитной телеметрии "
            "(U/I/температуры/Output/OVP/OCP). Auto Mix не запущен."
        )
        return False
    if snapshot.output_on:
        await message.answer(
            "❌ RD6018 уже показывает Output ON. Auto Mix разрешён только после подтверждённого OFF."
        )
        return False
    if snapshot.battery_voltage_v < MIX_ONLY_MIN_START_V:
        await message.answer(
            f"❌ Auto Mix не запущен: Uакб={snapshot.battery_voltage_v:.2f} V < "
            f"{MIX_ONLY_MIN_START_V:.1f} V. Для такой АКБ сначала нужен обычный заряд/PREP."
        )
        return False

    ah_now = app._safe_float(live.get("ah"))
    controller.configure_recovery_context(
        battery_id=pending.battery_id,
        intent=ChargeIntent.NORMAL,
        condition_before=pending.condition,
    )

    hv_block = await _automatic_hv_block_reason(controller)
    if hv_block is not None:
        await message.answer(
            "🛑 <b>Auto Mix заблокирован диагностикой.</b>\n"
            f"<code>{html.escape(hv_block)}</code>",
            parse_mode=ParseMode.HTML,
        )
        return False

    try:
        _begin_mix_only_controller_session(
            controller,
            profile=pending.profile,
            capacity_ah=pending.capacity_ah,
            battery_v=snapshot.battery_voltage_v,
            current_a=snapshot.current_a,
            temp_ext_c=snapshot.temp_ext_c,
            ah_now=ah_now,
        )
        target_v, target_i = controller._mix_target(snapshot.temp_ext_c)
        target_i = float(app._cap_current(target_i))

        identity = BatteryIdentity(
            battery_id=pending.battery_id,
            chemistry=chemistry_for_legacy_profile(pending.profile),
            nominal_capacity_ah=float(pending.capacity_ah),
        )
        envelope = select_recipe_envelope(
            ChargeContext(
                identity=identity,
                intent=ChargeIntent.NORMAL,
                condition=pending.condition,
            ),
            expert_high_voltage=False,
        )
        result = await app.hass.safe_enable_output(
            voltage_v=float(target_v),
            current_a=target_i,
            ovp_v=float(target_v) + float(app.OVP_OFFSET),
            ocp_a=target_i + float(app.OCP_OFFSET),
            recipe_voltage_ceiling_v=float(envelope.voltage_ceiling_v),
        )
    except Exception as exc:
        off_confirmed = await _confirm_failed_start_is_off(app)
        if off_confirmed:
            controller.stop(clear_session=True)
            suffix = " Выход подтверждён OFF."
        else:
            suffix = (
                " 🚨 <b>Output OFF НЕ подтверждён.</b> Автовключение заблокировано; "
                "проверьте RD6018/HA."
            )
        await message.answer(
            f"❌ Auto Mix отменён: ошибка безопасного включения "
            f"({html.escape(type(exc).__name__)}).{suffix}",
            parse_mode=ParseMode.HTML,
        )
        return False

    if not result.enabled:
        off_confirmed = await _confirm_failed_start_is_off(app)
        if off_confirmed:
            controller.stop(clear_session=True)
            state_text = "Выход подтверждён OFF."
        else:
            state_text = (
                "🚨 <b>Output OFF НЕ подтверждён.</b> Контроллер оставлен активным "
                "для fail-closed контроля."
            )
        detail = html.escape(result.detail or "RD6018 не подтвердил безопасное включение")
        await message.answer(
            f"❌ <b>Auto Mix не запущен.</b> {state_text}\n<code>{detail}</code>",
            parse_mode=ParseMode.HTML,
        )
        return False

    app.last_checkpoint_time = app.time.time()
    app.last_chat_id = message.chat.id
    app.last_user_id = user_id
    app.log_event(
        controller.current_stage,
        snapshot.battery_voltage_v,
        snapshot.current_a,
        snapshot.temp_ext_c,
        ah_now,
        f"V2_START | MIX_ONLY | PREP_MAIN_RECOVERY_SKIPPED | battery={pending.battery_id}",
    )
    await message.answer(
        f"✅ <b>Auto Mix запущен</b>\n"
        f"{html.escape(pending.profile)} {pending.capacity_ah:g} Ah · сразу Mix\n"
        f"АКБ: <code>{html.escape(pending.battery_id)}</code>\n"
        f"Uакб до старта: {snapshot.battery_voltage_v:.2f} V",
        parse_mode=ParseMode.HTML,
    )
    try:
        old = app.user_dashboard.get(user_id)
        await app.send_dashboard(message, old_msg_id=old)
    except Exception:
        pass
    return True


def _mix_menu_keyboard(records: list[Any]) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=battery_button_label(record),
                callback_data=f"v2_mix_bat_{idx}",
            )
        ]
        for idx, record in enumerate(records)
    ]
    rows.append(
        [
            InlineKeyboardButton(text="Ca/Ca", callback_data="v2_mix_profile_caca"),
            InlineKeyboardButton(text="EFB", callback_data="v2_mix_profile_efb"),
            InlineKeyboardButton(text="AGM", callback_data="v2_mix_profile_agm"),
        ]
    )
    rows.append([InlineKeyboardButton(text="⬅ К программам", callback_data="charge_modes")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _start_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="▶ Запустить Auto Mix", callback_data="v2_mix_start")],
            [InlineKeyboardButton(text="⬅ Auto Mix", callback_data="v2_mix")],
        ]
    )


async def _answer(event: Any, text: str, *, reply_markup=None) -> None:
    message = event.message if hasattr(event, "message") and event.message is not None else event
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)


def install_mix_only_mode(app: Any) -> None:
    global _installed
    if _installed:
        return
    _installed = True

    original_modes_keyboard = app._build_charge_modes_keyboard
    original_modes_text = app._charge_modes_text
    original_handle_ah = app.handle_ah_input

    def modes_keyboard() -> InlineKeyboardMarkup:
        markup = original_modes_keyboard()
        rows = [list(row) for row in markup.inline_keyboard]
        insert_at = next(
            (
                idx
                for idx, row in enumerate(rows)
                if any(button.callback_data == "v2_manual" for button in row)
            ),
            max(0, len(rows) - 1),
        )
        rows.insert(
            insert_at,
            [InlineKeyboardButton(text="⚗ Авто Mix", callback_data="v2_mix")],
        )
        return InlineKeyboardMarkup(inline_keyboard=rows)

    def modes_text() -> str:
        return (
            original_modes_text()
            + "\n\n<b>Auto Mix</b> — отдельная автоматическая программа: сразу Mix, "
            "без PREP/Main/Recovery; ниже 12.0 V старт запрещён."
        )

    async def handle_ah_input(message: Any, profile: str, user_id: int) -> None:
        mix_profile = _mix_awaiting_ah.get(user_id)
        if mix_profile is None:
            await original_handle_ah(message, profile, user_id)
            return
        try:
            capacity = float((message.text or "").strip().replace(",", "."))
        except ValueError:
            await message.answer("❌ Введите ёмкость числом, например <code>70</code>.", parse_mode=ParseMode.HTML)
            return
        if capacity < 1 or capacity > 500:
            await message.answer("❌ Ёмкость должна быть от 1 до 500 Ah.")
            return

        _mix_awaiting_ah.pop(user_id, None)
        app.awaiting_ah.pop(user_id, None)
        pending = PendingMixStart(
            profile=mix_profile,
            capacity_ah=capacity,
            battery_id=f"adhoc:mix:{mix_profile}:{capacity:g}:{user_id}",
        )
        _mix_pending_start[user_id] = pending
        await message.answer(
            build_mix_only_preview(pending),
            parse_mode=ParseMode.HTML,
            reply_markup=_start_keyboard(),
        )

    app._build_charge_modes_keyboard = modes_keyboard
    app._charge_modes_text = modes_text
    app.handle_ah_input = handle_ah_input

    @app.router.callback_query(F.data == "v2_mix")
    async def mix_menu_handler(call: Any) -> None:
        if not await app._check_chat_and_respond(call):
            return
        await call.answer()
        user_id = call.from_user.id if call.from_user else 0
        records = [
            record
            for record in await list_batteries(limit=20)
            if profile_for_chemistry(record.identity.chemistry) is not None
        ]
        _mix_battery_pages[user_id] = records
        await _answer(
            call,
            "<b>⚗ Автоматический Mix</b>\n\n"
            "Старт сразу с Mix без PREP/Main/Recovery. "
            "Выберите сохранённую АКБ или химию для разового запуска.",
            reply_markup=_mix_menu_keyboard(records),
        )

    @app.router.callback_query(F.data.startswith("v2_mix_profile_"))
    async def mix_quick_profile_handler(call: Any) -> None:
        if not await app._check_chat_and_respond(call):
            return
        await call.answer()
        profile = _profile_from_callback(call.data or "")
        if profile is None:
            return
        user_id = call.from_user.id if call.from_user else 0
        _mix_awaiting_ah[user_id] = profile
        app.awaiting_ah[user_id] = profile
        await _answer(
            call,
            f"<b>Auto Mix · {html.escape(profile)}</b>\n\n"
            "Введите ёмкость АКБ в Ah. После ввода покажу точную программу перед запуском.",
        )

    @app.router.callback_query(F.data.startswith("v2_mix_bat_"))
    async def mix_battery_handler(call: Any) -> None:
        if not await app._check_chat_and_respond(call):
            return
        await call.answer()
        user_id = call.from_user.id if call.from_user else 0
        raw = (call.data or "").replace("v2_mix_bat_", "", 1)
        if not raw.isdigit():
            return
        idx = int(raw)
        records = _mix_battery_pages.get(user_id) or []
        if idx < 0 or idx >= len(records):
            await call.answer("Список устарел — откройте Auto Mix заново", show_alert=True)
            return
        record = records[idx]
        profile = profile_for_chemistry(record.identity.chemistry)
        if profile is None:
            await call.answer("Для этой химии нет Auto Mix", show_alert=True)
            return
        pending = PendingMixStart(
            profile=profile,
            capacity_ah=record.identity.nominal_capacity_ah,
            battery_id=record.identity.battery_id,
            condition=record.lifecycle.condition,
        )
        _mix_pending_start[user_id] = pending
        await _answer(call, build_mix_only_preview(pending), reply_markup=_start_keyboard())

    @app.router.callback_query(F.data == "v2_mix_start")
    async def mix_start_handler(call: Any) -> None:
        if not await app._check_chat_and_respond(call):
            return
        await call.answer()
        user_id = call.from_user.id if call.from_user else 0
        pending = _mix_pending_start.get(user_id)
        if pending is None:
            await call.answer("Предпросмотр устарел — откройте Auto Mix заново", show_alert=True)
            return
        if await start_mix_transactional(app, call, pending):
            _mix_pending_start.pop(user_id, None)
