from __future__ import annotations

import html
from typing import Any

from legacy_recipe_adapter import chemistry_for_legacy_profile
from pb_domain import BatteryIdentity, ChargeContext
from recipe_engine import select_recipe_envelope
from safe_output import snapshot_from_live
from v2_ui import intent_label


async def _confirm_failed_start_is_off(app: Any) -> bool:
    """Request shutdown and return True only when the HA boundary confirms OFF."""
    try:
        return bool(await app.hass.turn_off(app.ENTITY_MAP["switch"]))
    except Exception:
        return False


async def start_profile_transactional(app: Any, event: Any, pending: Any) -> bool:
    """Start one V2 profile only through the recipe-aware safe output coordinator.

    No success message is emitted unless RD6018 confirmed ON. Conversely, a failed
    start may be described as safely OFF only when the hardware boundary confirms OFF;
    if shutdown cannot be proved, the controller session stays alive/inhibited so
    monitoring can keep retrying instead of forgetting a potentially energized output.
    """
    message = event.message if hasattr(event, "message") and event.message is not None else event
    user = getattr(event, "from_user", None) or getattr(message, "from_user", None)
    user_id = user.id if user else 0

    if app.charge_controller.is_active:
        await message.answer("⚠️ Сначала остановите текущую сессию.")
        return False

    live = await app.hass.get_all_live()
    snapshot = snapshot_from_live(live)
    if snapshot is None:
        await message.answer(
            "❌ Нет полного набора защитной телеметрии "
            "(U/I/temp_ext/temp_int/input/switch/OVP/OCP). V2 запуск запрещён."
        )
        return False
    if snapshot.output_on:
        await message.answer(
            "❌ RD6018 уже показывает Output ON. Новый запуск не разрешён до подтверждённого OFF."
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

    try:
        if battery_v < 12.0:
            target_v, target_i = app.charge_controller._prep_target(temp_ext)
        else:
            target_v, target_i = app.charge_controller._main_target(temp_ext)

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
            f"❌ V2 запуск отменён: ошибка безопасной транзакции "
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
                "🚨 <b>Output OFF НЕ подтверждён.</b> Контроллер оставлен активным/заблокированным "
                "для дальнейшего safety-контроля; проверьте RD6018/HA."
            )
        detail = html.escape(result.detail or "RD6018 не подтвердил безопасное включение")
        await message.answer(
            f"❌ <b>V2 запуск отменён.</b> {state_text}\n<code>{detail}</code>",
            parse_mode=app.ParseMode.HTML,
        )
        return False

    app.last_checkpoint_time = app.time.time()
    app.last_chat_id = message.chat.id
    app.last_user_id = user_id
    app.log_event(
        app.charge_controller.current_stage,
        battery_v,
        current,
        temp_ext,
        ah_now,
        f"V2_START | intent={pending.intent.value} battery={pending.battery_id}",
    )
    await message.answer(
        f"✅ <b>V2 заряд запущен</b>\n"
        f"{html.escape(pending.profile)} {pending.capacity_ah:g}Ah · "
        f"{html.escape(intent_label(pending.intent))}\n"
        f"АКБ: <code>{html.escape(pending.battery_id)}</code>",
        parse_mode=app.ParseMode.HTML,
    )
    try:
        old = app.user_dashboard.get(user_id)
        await app.send_dashboard(message, old_msg_id=old)
    except Exception:
        pass
    return True
