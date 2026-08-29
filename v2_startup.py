from __future__ import annotations

import html
from typing import Any

from legacy_recipe_adapter import chemistry_for_legacy_profile
from pb_domain import BatteryIdentity, ChargeContext
from recipe_engine import select_recipe_envelope
from v2_ui import intent_label


async def start_profile_transactional(app: Any, event: Any, pending: Any) -> bool:
    """Start one V2 profile only through the recipe-aware safe output coordinator.

    The UI may prepare controller state before the hardware transaction, but a failed
    programming/readback/preflight/enable step always stops the controller again and
    forces output OFF. No success message is emitted unless RD6018 confirmed ON.
    """
    message = event.message if hasattr(event, "message") and event.message is not None else event
    user = getattr(event, "from_user", None) or getattr(message, "from_user", None)
    user_id = user.id if user else 0

    if app.charge_controller.is_active:
        await message.answer("⚠️ Сначала остановите текущую сессию.")
        return False

    live = await app.hass.get_all_live()
    temp_raw = live.get("temp_ext")
    if temp_raw in (None, "", "unknown", "unavailable"):
        await message.answer(
            "❌ Нет валидной температуры temp_ext. V2 не разрешает запуск без датчика АКБ."
        )
        return False

    battery_v = app._safe_float(live.get("battery_voltage"))
    current = app._safe_float(live.get("current"))
    temp_ext = app._safe_float(temp_raw)
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
        app.charge_controller.stop(clear_session=True)
        try:
            await app.hass.turn_off(app.ENTITY_MAP["switch"])
        except Exception:
            pass
        await message.answer(
            f"❌ V2 запуск отменён: ошибка безопасной транзакции ({html.escape(type(exc).__name__)})."
        )
        return False

    if not result.enabled:
        app.charge_controller.stop(clear_session=True)
        try:
            await app.hass.turn_off(app.ENTITY_MAP["switch"])
        except Exception:
            pass
        detail = html.escape(result.detail or "RD6018 не подтвердил безопасное включение")
        await message.answer(
            f"❌ <b>V2 запуск отменён.</b> Выход оставлен OFF.\n<code>{detail}</code>",
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
