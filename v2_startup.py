from __future__ import annotations

import html
from typing import Any

from legacy_recipe_adapter import chemistry_for_legacy_profile
from pb_domain import BatteryIdentity, ChargeContext
from recipe_engine import select_recipe_envelope
from safe_output import snapshot_from_live
from v2_ui import intent_label


INITIAL_MAIN_THRESHOLD_V = 12.0


async def _confirm_failed_start_is_off(app: Any) -> bool:
    """Request shutdown and return True only when the HA boundary confirms OFF."""
    try:
        return bool(await app.hass.turn_off(app.ENTITY_MAP["switch"]))
    except Exception:
        return False


def _select_initial_auto_target(
    app: Any,
    *,
    battery_v: float,
    temp_ext: float,
    ah_now: float,
) -> tuple[float, float, bool]:
    """Atomically choose PREP or Main before the first Output ON.

    V1 could expose one tick where logical stage=PREP while physical setpoints already
    belonged to Main. V2 removes that split: <12.0 V remains PREP at ~0.01C; >=12.0 V
    starts directly in Main and records the skipped PREP as an audit event.
    """
    controller = app.charge_controller
    if float(battery_v) < INITIAL_MAIN_THRESHOLD_V:
        target_v, target_i = controller._prep_target(temp_ext)
        return float(target_v), float(target_i), False

    now = float(app.time.time())
    controller.current_stage = controller.STAGE_MAIN
    controller.stage_start_time = now
    controller._stage_start_ah = float(ah_now)
    controller._start_ah = float(ah_now)
    clear_restored = getattr(controller, "_clear_restored_targets", None)
    if callable(clear_restored):
        clear_restored()
    reset_blanking = getattr(controller, "_reset_delta_and_blanking", None)
    if callable(reset_blanking):
        reset_blanking(now)
    if hasattr(controller, "_v2_main_plateau_since"):
        controller._v2_main_plateau_since = None
    target_v, target_i = controller._main_target(temp_ext)
    if hasattr(controller, "_v2_target_voltage_v"):
        controller._v2_target_voltage_v = float(target_v)
    if hasattr(controller, "_v2_last_stage"):
        controller._v2_last_stage = controller.STAGE_MAIN
    return float(target_v), float(target_i), True


async def start_profile_transactional(app: Any, event: Any, pending: Any) -> bool:
    """Start one profile only through the recipe-aware safe output coordinator."""
    message = event.message if hasattr(event, "message") and event.message is not None else event
    user = getattr(event, "from_user", None) or getattr(message, "from_user", None)
    user_id = user.id if user else 0

    rd_mode = getattr(app, "rd_control_mode_manager", None)
    if rd_mode is not None and bool(getattr(rd_mode, "hands_off", False)):
        await message.answer(
            "🔓 Режим РД — не лезь включён. Сначала верните контроль заряда; "
            "текущий Output и уставки не изменены."
        )
        return False

    if app.charge_controller.is_active:
        await message.answer("⚠️ Сначала остановите текущую программу.")
        return False

    live = await app.hass.get_all_live()
    snapshot = snapshot_from_live(live)
    if snapshot is None:
        await message.answer(
            "❌ Нет полного набора защитной телеметрии "
            "(U/I/температуры/Output/OVP/OCP). Запуск запрещён системой защиты."
        )
        return False
    if snapshot.output_on:
        await message.answer(
            "❌ RD6018 уже показывает Output ON. Новый запуск разрешён только после подтверждённого OFF."
        )
        return False

    battery_v = snapshot.battery_voltage_v
    current = snapshot.current_a
    temp_ext = snapshot.temp_ext_c
    ah_now = app._safe_float(live.get("ah"))

    app.charge_controller.configure_recovery_context(
        battery_id=pending.battery_id,
        intent=pending.intent,
        condition_before=pending.condition,
    )
    app.charge_controller.start(pending.profile, int(round(pending.capacity_ah)))

    prep_skipped = False
    try:
        target_v, target_i, prep_skipped = _select_initial_auto_target(
            app,
            battery_v=battery_v,
            temp_ext=temp_ext,
            ah_now=ah_now,
        )

        identity = BatteryIdentity(
            battery_id=pending.battery_id,
            chemistry=chemistry_for_legacy_profile(pending.profile),
            nominal_capacity_ah=float(pending.capacity_ah),
        )
        envelope = select_recipe_envelope(
            ChargeContext(
                identity=identity,
                intent=pending.intent,
                condition=pending.condition,
            ),
            expert_high_voltage=False,
        )

        result = await app.hass.safe_enable_output(
            voltage_v=float(target_v),
            current_a=float(app._cap_current(target_i)),
            ovp_v=float(target_v) + float(app.OVP_OFFSET),
            ocp_a=float(app._cap_current(target_i)) + float(app.OCP_OFFSET),
            recipe_voltage_ceiling_v=float(envelope.voltage_ceiling_v),
        )
    except Exception as exc:
        off_confirmed = await _confirm_failed_start_is_off(app)
        if off_confirmed:
            app.charge_controller.stop(clear_session=True)
            suffix = " Выход подтверждён OFF."
        else:
            suffix = (
                " 🚨 <b>Output OFF НЕ подтверждён.</b> Автовключение заблокировано; "
                "проверьте RD6018/HA и при необходимости отключите выход или питание вручную."
            )
        await message.answer(
            f"❌ Запуск отменён: ошибка безопасного включения "
            f"({html.escape(type(exc).__name__)}).{suffix}",
            parse_mode=app.ParseMode.HTML,
        )
        return False

    if not result.enabled:
        off_confirmed = await _confirm_failed_start_is_off(app)
        if off_confirmed:
            app.charge_controller.stop(clear_session=True)
            state_text = "Выход подтверждён OFF."
        else:
            state_text = (
                "🚨 <b>Output OFF НЕ подтверждён.</b> Контроллер оставлен активным и заблокированным "
                "для контроля безопасности; проверьте RD6018/HA."
            )
        detail = html.escape(result.detail or "RD6018 не подтвердил безопасное включение")
        await message.answer(
            f"❌ <b>Запуск отменён.</b> {state_text}\n<code>{detail}</code>",
            parse_mode=app.ParseMode.HTML,
        )
        return False

    app.last_checkpoint_time = app.time.time()
    app.last_chat_id = message.chat.id
    app.last_user_id = user_id
    start_reason = (
        f"V2_START | PREP_SKIPPED_INITIAL_VOLTAGE={battery_v:.3f}V | "
        if prep_skipped
        else "V2_START | PREP_REQUIRED | "
    )
    app.log_event(
        app.charge_controller.current_stage,
        battery_v,
        current,
        temp_ext,
        ah_now,
        f"{start_reason}intent={pending.intent.value} battery={pending.battery_id}",
    )
    prep_line = (
        f"\nPREP пропущен: Uакб={battery_v:.2f} V ≥ {INITIAL_MAIN_THRESHOLD_V:.1f} V."
        if prep_skipped
        else f"\nPREP: мягкий ток до Uакб ≥ {INITIAL_MAIN_THRESHOLD_V:.1f} V."
    )
    await message.answer(
        f"✅ <b>Заряд запущен</b>\n"
        f"{html.escape(pending.profile)} {pending.capacity_ah:g} Ah · "
        f"{html.escape(intent_label(pending.intent))}\n"
        f"АКБ: <code>{html.escape(pending.battery_id)}</code>{prep_line}",
        parse_mode=app.ParseMode.HTML,
    )
    try:
        old = app.user_dashboard.get(user_id)
        await app.send_dashboard(message, old_msg_id=old)
    except Exception:
        pass
    return True
