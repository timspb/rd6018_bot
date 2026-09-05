from __future__ import annotations

"""Telegram/HMI composition for D062/D063 managed external-Mix takeover.

The safety/ownership state machine lives in :mod:`rd_managed_mix`.  This module is
intentionally a thin composition layer: it keeps the existing public import path used
by bot.py/tests while avoiding a second, drifting copy of the D062 actuator logic.
"""

import html
import time
import uuid
from dataclasses import replace
from typing import Any, Optional

from aiogram import F
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from ha_history import HomeAssistantHistoryError
from operator_confirmation import ConfirmationStore
from pb_domain import BatteryChemistry
from rd6018_telemetry import finite_float
from rd_live_adoption import MIX_HARD_LIMIT_HOURS
from rd_managed_adoption import ManagedLiveAdoptionCoordinator
from rd_managed_mix import (
    ADOPTED_MIX_POLL_S,
    ADOPTED_MIX_SETPOINT_TOLERANCE,
    ManagedMixAdoptionCoordinator,
    ManagedMixPreview,
    ManagedMixState,
    PriorMixAge,
    PriorMixAgeSource,
    install_runtime_composition,
    resolve_prior_mix_age,
)
from v2_battery_catalog import list_batteries
from v2_ui import battery_button_label


__all__ = [
    "ADOPTED_MIX_POLL_S",
    "ADOPTED_MIX_SETPOINT_TOLERANCE",
    "ManagedMixAdoptionCoordinator",
    "ManagedMixPreview",
    "ManagedMixState",
    "PriorMixAge",
    "PriorMixAgeSource",
    "install_managed_mix_adoption",
    "resolve_prior_mix_age",
]


def _install_hmi_composition(app: Any, coordinator: ManagedMixAdoptionCoordinator) -> None:
    import operator_hmi

    if bool(getattr(operator_hmi, "_d062_managed_mix_wrapped", False)):
        return
    original_state = operator_hmi.build_operator_hmi_state
    original_keyboard = operator_hmi.build_operator_keyboard
    original_details = operator_hmi.render_operator_details
    original_more = operator_hmi._more_keyboard

    def battery_label() -> str:
        pieces = [coordinator.battery_id]
        if coordinator.chemistry is not None:
            pieces.append(coordinator.chemistry.value)
        if coordinator.capacity_ah > 0:
            pieces.append(f"{coordinator.capacity_ah:g} Ah")
        return " · ".join(piece for piece in pieces if piece)

    def progress(regulator: str) -> str:
        used = coordinator.total_active_elapsed_s / 3600.0
        limit_s = coordinator.hard_limit_s
        limit = "?" if limit_s is None else f"{limit_s / 3600.0:g}"
        if coordinator.off_pending:
            return f"Output OFF containment · Mix budget {used:.1f}/{limit}ч"
        if coordinator.finish_hold_started_at_s is not None:
            held = max(0.0, time.time() - coordinator.finish_hold_started_at_s)
            return f"Δ подтверждена · выдержка {held / 3600.0:.1f}/2ч · Mix {used:.1f}/{limit}ч"
        criterion = (
            "Imin → ΔI"
            if regulator == "CV"
            else ("Vmax → ΔV" if regulator == "CC" else "CV/CC Delta")
        )
        return f"MIX_ADOPTED · {criterion} → 2ч → OFF · бюджет {used:.1f}/{limit}ч"

    def build_state(app_arg: Any, live: Any) -> Any:
        state = original_state(app_arg, live)
        if coordinator.active or coordinator.off_pending:
            authority = coordinator.current_authority
            return replace(
                state,
                process_state=operator_hmi.HmiProcessState.ADOPTED_MIX,
                authority=operator_hmi.HmiAuthority.ADOPTED_MIX,
                title=(
                    "RD6018 · MIX ПОД УПРАВЛЕНИЕМ"
                    if coordinator.active
                    else "RD6018 · MIX · OFF PENDING"
                ),
                battery_label=battery_label(),
                target_voltage_v=(
                    float(authority.set_voltage_v)
                    if authority is not None
                    else state.target_voltage_v
                ),
                current_limit_a=(
                    float(authority.set_current_a)
                    if authority is not None
                    else state.current_limit_a
                ),
                progress=progress(state.regulator),
                attention="warning" if coordinator.off_pending else state.attention,
            )
        return state

    def build_keyboard(app_arg: Any, state: Any) -> InlineKeyboardMarkup:
        if coordinator.active or coordinator.off_pending:
            return InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="⏹ Остановить Mix",
                            callback_data="operator_managed_mix_stop",
                        )
                    ],
                    [
                        InlineKeyboardButton(text="ℹ Подробнее", callback_data="operator_details"),
                        InlineKeyboardButton(text="📈 График", callback_data="operator_graph"),
                    ],
                    [
                        InlineKeyboardButton(text="🔋 АКБ", callback_data="v2_batteries"),
                        InlineKeyboardButton(text="⋯ Ещё", callback_data="operator_more"),
                    ],
                ]
            )
        markup = original_keyboard(app_arg, state)
        if (
            state.process_state is operator_hmi.HmiProcessState.HANDS_OFF
            and bool(state.output_on)
        ):
            rows = [list(row) for row in markup.inline_keyboard]
            rows.insert(
                1,
                [
                    InlineKeyboardButton(
                        text="🎯 Забрать Mix под управление",
                        callback_data="rd_managed_mix",
                    )
                ],
            )
            return InlineKeyboardMarkup(inline_keyboard=rows)
        return markup

    def details(app_arg: Any, state: Any, live: Any) -> str:
        if coordinator.active or coordinator.off_pending:
            authority = coordinator.current_authority
            used = coordinator.total_active_elapsed_s / 3600.0
            limit_s = coordinator.hard_limit_s
            limit_h = None if limit_s is None else limit_s / 3600.0
            ovp = finite_float(live.get("ovp"))
            ocp = finite_float(live.get("ocp"))
            authority_text = (
                f"Authority current: {authority.set_voltage_v:.2f}V/{authority.set_current_a:.2f}A"
                if authority is not None
                else "Authority current: —"
            )
            protections = (
                f"Защиты RD: OVP {ovp:.2f}V · OCP {ocp:.2f}A"
                if ovp is not None and ocp is not None
                else "Защиты RD: —"
            )
            return (
                "<b>MIX_ADOPTED · managed ownership</b>\n\n"
                f"АКБ: {html.escape(battery_label() or '—')}\n"
                f"Output: {'ON' if state.output_on else 'OFF'} · {html.escape(state.regulator)}\n"
                f"Prior age: {coordinator.prior_elapsed_s / 3600.0:.2f}ч "
                f"(<code>{html.escape(coordinator.prior_age_source or '—')}</code>)\n"
                f"Active budget: {used:.2f}/{limit_h if limit_h is not None else '?'}ч\n"
                f"{authority_text}\n"
                f"{protections}\n\n"
                "Delta evidence начата заново после edge adoption; Recorder не переносит Imin/Vmax. "
                "Нормальный финиш — verified OFF, без SAFE_WAIT/Storage.\n"
                f"Последнее: <code>{html.escape(coordinator.last_status or '—')}</code>"
            )
        return original_details(app_arg, state, live)

    def more(state: Any) -> InlineKeyboardMarkup:
        markup = original_more(state)
        if coordinator.active or coordinator.off_pending:
            rows: list[list[InlineKeyboardButton]] = []
            for row in markup.inline_keyboard:
                converted: list[InlineKeyboardButton] = []
                for button in row:
                    if button.callback_data == "rd_live_mix_status":
                        converted.append(
                            InlineKeyboardButton(
                                text="🎯 Статус Managed Mix",
                                callback_data="rd_managed_mix_status",
                            )
                        )
                    else:
                        converted.append(button)
                rows.append(converted)
            return InlineKeyboardMarkup(inline_keyboard=rows)
        return markup

    operator_hmi.build_operator_hmi_state = build_state
    operator_hmi.build_operator_keyboard = build_keyboard
    operator_hmi.render_operator_details = details
    operator_hmi._more_keyboard = more
    operator_hmi._d062_managed_mix_wrapped = True


def _hours_text(seconds: float) -> str:
    return f"{max(0.0, float(seconds)) / 3600.0:.2f} ч"


def _preview_text(preview: ManagedMixPreview) -> str:
    limit_h = MIX_HARD_LIMIT_HOURS[preview.chemistry]
    remaining_h = max(0.0, limit_h - preview.prior_age.elapsed_s / 3600.0)
    fp = preview.fingerprint
    return (
        "<b>🎯 MIX_ADOPTED · managed live takeover</b>\n\n"
        f"АКБ: <code>{html.escape(preview.battery_id)}</code> · "
        f"{preview.chemistry.value} · {preview.capacity_ah:g} Ah\n"
        f"RD: {fp.set_voltage_v:.2f} V / {fp.set_current_a:.2f} A · "
        f"OVP {fp.ovp_v:.2f} / OCP {fp.ocp_a:.2f}\n"
        f"Prior active Mix: {_hours_text(preview.prior_age.elapsed_s)} · "
        f"{preview.prior_age.source.value}\n"
        f"Остаток chemistry budget сейчас: <b>{remaining_h:.2f} ч</b> из {limit_h:g} ч.\n\n"
        "На takeover бот не пишет Output/V/I/OVP/OCP. Delta начинается с нуля только после adoption. "
        "Возраст на Execute может только увеличиться: новый Recorder snapshot не может уменьшить уже "
        "принятый prior-age floor. Если Delta подтверждена до исчерпания budget, sticky 2ч hold может "
        "закончиться после границы budget; если hold не начата к границе — "
        "MIX_TIMEOUT → verified OFF + diagnose.\n"
        "Нормальный финиш: verified OFF; SAFE_WAIT/Storage не запускаются."
    )


def install_managed_mix_adoption(
    app: Any,
    manager: Any,
    d061: ManagedLiveAdoptionCoordinator,
    *,
    install_ui: bool = True,
) -> ManagedMixAdoptionCoordinator:
    existing = getattr(app, "rd_managed_mix_adoption", None)
    if isinstance(existing, ManagedMixAdoptionCoordinator):
        return existing

    coordinator = ManagedMixAdoptionCoordinator(app, manager, d061)
    app.rd_managed_mix_adoption = coordinator
    install_runtime_composition(app, coordinator)

    if not install_ui:
        return coordinator

    _install_hmi_composition(app, coordinator)
    confirmations = ConfirmationStore()
    pending: dict[tuple[int, int], dict[str, Any]] = {}

    def key(call: Any) -> Optional[tuple[int, int]]:
        return confirmations.callback_identity(call)

    async def preview_for_item(call: Any, item: dict[str, Any], prior_age: PriorMixAge) -> None:
        record = item["record"]
        fp = item["fingerprint"]
        limit_h = MIX_HARD_LIMIT_HOURS[record.identity.chemistry]
        if prior_age.elapsed_s >= float(limit_h) * 3600.0:
            await call.answer(
                f"Возраст уже исчерпал Mix budget {limit_h:g}ч; managed adoption запрещён",
                show_alert=True,
            )
            return
        token = (
            f"d062:{item['nonce']}:{record.identity.battery_id}:"
            f"{fp.set_voltage_v:.3f}:{fp.set_current_a:.3f}:"
            f"{prior_age.elapsed_s:.1f}:{prior_age.source.value}"
        )
        preview = ManagedMixPreview(
            token=token,
            battery_id=record.identity.battery_id,
            chemistry=record.identity.chemistry,
            capacity_ah=record.identity.nominal_capacity_ah,
            fingerprint=fp,
            prior_age=prior_age,
            history=item.get("history"),
        )
        item["preview"] = preview
        await call.answer()
        await call.message.answer(
            _preview_text(preview),
            parse_mode=app.ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="Подтвердить MIX_ADOPTED",
                            callback_data="rd_managed_mix_confirm",
                        )
                    ],
                    [InlineKeyboardButton(text="Отмена", callback_data="rd_managed_mix_cancel")],
                ]
            ),
        )

    @app.router.callback_query(F.data == "rd_managed_mix")
    async def managed_mix_menu(call: Any) -> None:
        if not await app._check_chat_and_respond(call):
            return
        identity = key(call)
        if identity is None:
            await call.answer("Не удалось привязать workflow к чату", show_alert=True)
            return
        if not manager.hands_off:
            await call.answer("MIX_ADOPTED доступен только из HANDS_OFF", show_alert=True)
            return
        conflict = coordinator._conflict()
        if conflict is not None:
            await call.answer(conflict, show_alert=True)
            return
        live = await coordinator.guard._raw_live()
        try:
            fp = d061._preflight_live(live)
        except Exception as exc:
            await call.answer(str(exc), show_alert=True)
            return
        try:
            history = await coordinator.history_reader.read_mix_evidence(live=live)
            history_error = ""
        except HomeAssistantHistoryError as exc:
            history = None
            history_error = str(exc)
        records = [
            record
            for record in await list_batteries(limit=30)
            if record.identity.chemistry in MIX_HARD_LIMIT_HOURS
            and record.identity.chemistry is not BatteryChemistry.CUSTOM
        ]
        if not records:
            await call.answer("Нет сохранённой Pb АКБ подходящей химии", show_alert=True)
            return
        pending[identity] = {
            "nonce": uuid.uuid4().hex,
            "fingerprint": fp,
            "history": history,
            "history_error": history_error,
            "records": records,
            "declared_elapsed_s": 0.0,
            "declared": False,
        }
        rows = [
            [
                InlineKeyboardButton(
                    text=battery_button_label(record),
                    callback_data=f"rd_managed_mix_bat_{idx}",
                )
            ]
            for idx, record in enumerate(records)
        ]
        rows.append([InlineKeyboardButton(text="Отмена", callback_data="rd_managed_mix_cancel")])
        await call.answer()
        await call.message.answer(
            "🎯 <b>Какую физическую АКБ держит текущий Mix?</b>\n"
            "До edge execute этот workflow read-only.",
            parse_mode=app.ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        )

    @app.router.callback_query(F.data.startswith("rd_managed_mix_bat_"))
    async def managed_mix_battery(call: Any) -> None:
        identity = key(call)
        item = pending.get(identity) if identity is not None else None
        if item is None:
            await call.answer("Предпросмотр устарел", show_alert=True)
            return
        try:
            index = int(str(call.data).rsplit("_", 1)[-1])
            record = item["records"][index]
        except (ValueError, IndexError):
            await call.answer("Выбор АКБ устарел", show_alert=True)
            return
        item["record"] = record
        try:
            coordinator._chemistry_preflight(
                record.identity.chemistry,
                record.identity.nominal_capacity_ah,
                item["fingerprint"],
            )
        except Exception as exc:
            await call.answer(str(exc), show_alert=True)
            return

        history = item.get("history")
        if history is not None and history.output.reliable and history.output.elapsed_s is not None:
            prior = resolve_prior_mix_age(history)
            await preview_for_item(call, item, prior)
            return

        reason = (
            history.output.reason
            if history is not None
            else item.get("history_error") or "Recorder age unavailable"
        )
        await call.answer()
        await call.message.answer(
            "<b>Возраст внешнего Mix не доказан.</b>\n"
            f"Причина: {html.escape(str(reason))}\n\n"
            "D063 запрещает выдавать новый полный budget. Если время известно оператору, "
            "укажи его консервативно, округляя <b>вверх</b> до 30 минут. Кнопки складываются.",
            parse_mode=app.ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(text="0ч точно", callback_data="rd_managed_mix_age_zero"),
                        InlineKeyboardButton(text="+30м", callback_data="rd_managed_mix_age_0_5"),
                    ],
                    [
                        InlineKeyboardButton(text="+1ч", callback_data="rd_managed_mix_age_1"),
                        InlineKeyboardButton(text="+4ч", callback_data="rd_managed_mix_age_4"),
                    ],
                    [
                        InlineKeyboardButton(text="Сброс", callback_data="rd_managed_mix_age_reset"),
                        InlineKeyboardButton(
                            text="Подтвердить возраст",
                            callback_data="rd_managed_mix_age_confirm",
                        ),
                    ],
                    [InlineKeyboardButton(text="Отмена", callback_data="rd_managed_mix_cancel")],
                ]
            ),
        )

    @app.router.callback_query(F.data.startswith("rd_managed_mix_age_"))
    async def managed_mix_age(call: Any) -> None:
        identity = key(call)
        item = pending.get(identity) if identity is not None else None
        if item is None or "record" not in item:
            await call.answer("Возрастной workflow устарел", show_alert=True)
            return
        action = str(call.data).removeprefix("rd_managed_mix_age_")
        if action == "reset":
            item["declared_elapsed_s"] = 0.0
            item["declared"] = False
            await call.answer("Сброшено; возраст ещё не объявлен")
            return
        if action == "zero":
            item["declared_elapsed_s"] = 0.0
            item["declared"] = True
            now = float(coordinator._wall_time())
            prior = resolve_prior_mix_age(
                item.get("history"),
                declared_elapsed_s=0.0,
                declared_at_s=now,
                now_s=now,
            )
            await preview_for_item(call, item, prior)
            return
        increments = {"0_5": 0.5 * 3600.0, "1": 3600.0, "4": 4 * 3600.0}
        if action in increments:
            item["declared_elapsed_s"] = (
                float(item.get("declared_elapsed_s") or 0.0) + increments[action]
            )
            item["declared"] = True
            await call.answer(f"Объявлено: {_hours_text(item['declared_elapsed_s'])}")
            return
        if action == "confirm":
            if not bool(item.get("declared", False)):
                await call.answer(
                    "Сначала явно объяви возраст или нажми «0ч точно»",
                    show_alert=True,
                )
                return
            now = float(coordinator._wall_time())
            prior = resolve_prior_mix_age(
                item.get("history"),
                declared_elapsed_s=float(item["declared_elapsed_s"]),
                declared_at_s=now,
                now_s=now,
            )
            await preview_for_item(call, item, prior)
            return
        await call.answer("Неизвестная команда возраста", show_alert=True)

    @app.router.callback_query(F.data == "rd_managed_mix_confirm")
    async def managed_mix_confirm(call: Any) -> None:
        if not await app._check_chat_and_respond(call):
            return
        identity = key(call)
        item = pending.get(identity) if identity is not None else None
        preview = item.get("preview") if item is not None else None
        if not isinstance(preview, ManagedMixPreview):
            await call.answer("Предпросмотр устарел", show_alert=True)
            return
        if not confirmations.issue_for_call(call, preview.token):
            await call.answer("Не удалось создать подтверждение", show_alert=True)
            return
        await call.answer()
        await call.message.answer(
            "⚠️ <b>Последнее подтверждение MIX_ADOPTED.</b>\n"
            "Следующая кнопка начнёт edge ownership transfer. До неё RD не менялся.",
            parse_mode=app.ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="ВЫПОЛНИТЬ MANAGED MIX TAKEOVER",
                            callback_data="rd_managed_mix_execute",
                        )
                    ],
                    [InlineKeyboardButton(text="Отмена", callback_data="rd_managed_mix_cancel")],
                ]
            ),
        )

    @app.router.callback_query(F.data == "rd_managed_mix_execute")
    async def managed_mix_execute(call: Any) -> None:
        if not await app._check_chat_and_respond(call):
            return
        identity = key(call)
        item = pending.get(identity) if identity is not None else None
        preview = item.get("preview") if item is not None else None
        granted = confirmations.consume_for_call(call)
        if not isinstance(preview, ManagedMixPreview) or granted != preview.token:
            await call.answer(
                "Подтверждение отсутствует, истекло, использовано или относится к другой сессии",
                show_alert=True,
            )
            return
        try:
            await coordinator.adopt(preview)
        except Exception as exc:
            await call.answer(str(exc), show_alert=True)
            return
        pending.pop(identity, None)
        await call.answer("MIX_ADOPTED активен")
        await call.message.answer(
            "🎯 <b>Текущий Mix принят под PB_MANAGED.</b>\n"
            "Output/V/I/OVP/OCP на takeover не переписывались. Prior-age budget зафиксирован "
            "консервативно; Delta считается только из новых post-adoption source reports.",
            parse_mode=app.ParseMode.HTML,
        )

    @app.router.callback_query(F.data == "rd_managed_mix_status")
    async def managed_mix_status(call: Any) -> None:
        if not await app._check_chat_and_respond(call):
            return
        limit_s = coordinator.hard_limit_s
        limit_h = None if limit_s is None else limit_s / 3600.0
        await call.answer()
        await call.message.answer(
            "🎯 <b>MIX_ADOPTED</b>\n"
            f"Состояние: <code>{coordinator.state.value}</code>\n"
            f"АКБ: <code>{html.escape(coordinator.battery_id)}</code>\n"
            f"Prior: {coordinator.prior_elapsed_s / 3600.0:.2f}ч "
            f"({html.escape(coordinator.prior_age_source or '—')})\n"
            f"Всего active: {coordinator.total_active_elapsed_s / 3600.0:.2f}/"
            f"{limit_h if limit_h is not None else '?'}ч\n"
            f"Последнее: <code>{html.escape(coordinator.last_status or '—')}</code>",
            parse_mode=app.ParseMode.HTML,
        )

    @app.router.callback_query(F.data == "operator_managed_mix_stop")
    async def managed_mix_stop(call: Any) -> None:
        if not await app._check_chat_and_respond(call):
            return
        if not coordinator.managed_authority:
            await call.answer("Managed Mix уже не активен", show_alert=True)
            return
        token = f"d062-stop:{coordinator.session_id}:{coordinator.state.value}"
        confirmations.issue_for_call(call, token)
        await call.answer()
        await call.message.answer(
            "<b>Остановить MIX_ADOPTED?</b>\n\nБудет выполнен только verified Output OFF.",
            parse_mode=app.ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="⏹ ОСТАНОВИТЬ",
                            callback_data="operator_managed_mix_stop_execute",
                        )
                    ],
                    [InlineKeyboardButton(text="Продолжить Mix", callback_data="operator_done")],
                ]
            ),
        )

    @app.router.callback_query(F.data == "operator_managed_mix_stop_execute")
    async def managed_mix_stop_execute(call: Any) -> None:
        if not await app._check_chat_and_respond(call):
            return
        expected = f"d062-stop:{coordinator.session_id}:{coordinator.state.value}"
        if confirmations.consume_for_call(call) != expected:
            await call.answer(
                "Stop-подтверждение устарело или относится к другой сессии",
                show_alert=True,
            )
            return
        ok = await coordinator.stop_by_operator()
        if not ok:
            await call.answer("Output OFF пока не подтверждён", show_alert=True)
            return
        await call.answer("Output подтверждён OFF")
        await call.message.answer("⏹ MIX_ADOPTED остановлен. Output подтверждён OFF.")

    @app.router.callback_query(F.data == "rd_managed_mix_cancel")
    async def managed_mix_cancel(call: Any) -> None:
        identity = key(call)
        if identity is not None:
            pending.pop(identity, None)
        confirmations.cancel_for_call(call)
        await call.answer("Отменено; RD не изменён")

    return coordinator
