"""Application-owned START transaction service.

This module owns the verified physical START transaction. Historical v2_startup.py
is retained only as a compatibility import facade during ERADICATION-09.
"""

from __future__ import annotations

from functools import wraps
from typing import Any

from application.execution_port import get_or_create_execution_port
from application.recipe_policy import chemistry_for_profile
from application.start_recipe_selection import (
    resolve_native_recipe_copy,
    resolve_user_step_recipe,
)
from application.start_event_context import (
    build_start_execution_identity,
    build_start_execution_intent,
)
from pb_domain import BatteryIdentity, ChargeContext
from recipe_engine import select_recipe_envelope
from safe_output import snapshot_from_live
from runtime.charge.runtime.stage_authority import (
    INITIAL_MAIN_THRESHOLD_V,
    select_initial_auto_target,
)
from runtime.ui.components.start_status import (
    format_start_enable_failure,
    format_start_html_error,
    format_start_persistence_failure,
    format_start_pre_enable_failure,
    format_start_success,
    format_start_unverified_failure,
)


async def _confirm_failed_start_is_off(app: Any, *, identity: Any, mode: str) -> bool:
    """Request shutdown only through the application-scoped execution owner."""
    try:
        intent = build_start_execution_intent(
            voltage_v=0.0,
            current_a=0.0,
            mode=f"{mode}_ROLLBACK_OFF",
            identity=identity,
            limits_reference="failed_start_containment",
        )
        result = await get_or_create_execution_port(app).disable(
            intent,
            identity=identity,
            reason="failed_start_containment",
        )
        return bool(result.verified)
    except Exception:
        return False


def _serialized_charge_start(operation):
    """Hold one app-scoped owner across START preflight, state and output ON.

    Emergency verified OFF retains its independent execution route.
    Nested ExecutionPort calls reuse the same task-owned lock.
    """
    @wraps(operation)
    async def wrapped(app: Any, event: Any, pending: Any) -> bool:
        port = get_or_create_execution_port(app)
        lock = port._guard_owner_lock
        if lock is None:
            raise RuntimeError("START cannot run without canonical owner lock")
        async with lock:
            return await operation(app, event, pending)
    return wrapped


@_serialized_charge_start
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

    if get_or_create_execution_port(app).session_recovery_guard.quarantined:
        await message.answer(
            "⚠️ Запуск заблокирован после неподтверждённого восстановления. "
            "Сначала требуется отдельное операторское восстановление при подтверждённом Output OFF."
        )
        return False

    if getattr(app.charge_controller, "_guarded_restore_candidate", None) is not None:
        await message.answer(
            "⚠️ Запуск заблокирован: сохранённая MAIN Guard сессия остаётся в карантине. "
            "Требуется отдельное подтверждённое восстановление."
        )
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

    # The existing profile START energizes Output before the recipe runner
    # receives its first step. OFF/WAIT-first drafts must never take that path.
    # Select mutually-exclusive recipe forms before physical START. Keep the
    # two established error-feedback paths and their validation order intact.
    try:
        selected_recipe = resolve_user_step_recipe(app, pending)
    except (AttributeError, TypeError, ValueError, OSError) as exc:
        await message.answer(
            format_start_html_error("❌ Рецепт не готов к START: ", str(exc)),
            parse_mode=app.ParseMode.HTML,
        )
        return False
    try:
        selected_native = resolve_native_recipe_copy(
            app, pending, selected_recipe)
    except (AttributeError, TypeError, ValueError, KeyError, OSError) as exc:
        await message.answer(
            format_start_html_error(
                "❌ Копия штатного рецепта не готова к START: ", str(exc)
            ), parse_mode=app.ParseMode.HTML,
        )
        return False

    battery_v = snapshot.battery_voltage_v
    current = snapshot.current_a
    temp_ext = snapshot.temp_ext_c
    ah_now = app._safe_float(live.get("ah"))

    # Operator pause belongs to the session it paused.  If that old session was
    # not restored (the controller is inactive above), an explicit, fresh START
    # from confirmed Output OFF retires the orphaned pause before enabling the
    # new session.  Otherwise the background loop would switch this new charge
    # off immediately after safe_enable_output succeeds.
    pause_active = getattr(app, "_operator_pause_active", None)
    if callable(pause_active) and pause_active():
        clear_pause = getattr(app, "_clear_operator_pause", None)
        if not callable(clear_pause):
            await message.answer(
                "❌ Запуск запрещён: сохранена пауза предыдущей сессии, "
                "её состояние нельзя безопасно сбросить."
            )
            return False
        clear_pause()
        app.log_event(
            app.charge_controller.current_stage,
            battery_v,
            current,
            temp_ext,
            ah_now,
            "OPERATOR_PAUSE_RETIRED_FOR_NEW_SESSION",
        )

    # A previous recipe must never take control of a new charge session.
    app.charge_controller._existing_recipe_execution_binding = None
    app.charge_controller._recipe_tick_fault = None
    # A selected native-recipe snapshot belongs only to its original session.
    # A new START must not inherit a previous session's draft overrides.
    app.charge_controller._native_recipe_session_selection = None
    app.charge_controller.configure_recovery_context(
        battery_id=pending.battery_id,
        intent=pending.intent,
        condition_before=pending.condition,
    )
    app.charge_controller.start(pending.profile, int(round(pending.capacity_ah)))
    # The first PREP/MAIN target and the canonical session writer must already
    # see the same immutable selection. No mid-session live library reads.
    app.charge_controller._native_recipe_session_selection = selected_native
    execution_identity = build_start_execution_identity(
        event_context=getattr(event, "context", None),
        recovery_context=getattr(app.charge_controller, "recovery_trace_context", {}),
        battery_id=getattr(pending, "battery_id", "unbound"),
        mode="AUTO_START",
    )

    prep_skipped = False
    enable_attempted = False
    try:
        target_v, target_i, prep_skipped = select_initial_auto_target(
            app.charge_controller,
            battery_v=battery_v,
            temp_ext=temp_ext,
            ah_now=ah_now,
            now=float(app.time.time()),
        )

        identity = BatteryIdentity(
            battery_id=pending.battery_id,
            chemistry=chemistry_for_profile(pending.profile),
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

        # For a selected recipe, energize directly at its first SET target.
        # Using normal PREP/MAIN targets here could briefly apply a different
        # (possibly higher) voltage/current before the recipe's first tick.
        if selected_recipe is not None:
            first = selected_recipe.steps[0]["params"]
            target_v, target_i = float(first["voltage_v"]), float(first["current_a"])
            if target_v > float(envelope.voltage_ceiling_v):
                raise ValueError("initial recipe SET exceeds battery voltage ceiling")
            capped_i = float(app._cap_current(target_i))
            if abs(capped_i - target_i) > 1e-6:
                raise ValueError("initial recipe SET exceeds active current limit")

        recipe_binding = None
        if selected_recipe is not None:
            from pathlib import Path
            from application.recipe_existing_session import prepare_existing_recipe_binding
            from application.recipe_execution_adapter import RecipeExecutionIdentity
            recipe_binding = prepare_existing_recipe_binding(
                catalog=app._user_recipe_catalog,
                recipe_id=str(pending.recipe_id),
                version=int(pending.recipe_version),
                port=get_or_create_execution_port(app),
                identity=RecipeExecutionIdentity(execution_identity.session_id,
                                                 execution_identity.trace_id),
                safety_context=build_start_execution_intent(
                    voltage_v=float(target_v), current_a=float(app._cap_current(target_i)),
                    mode="AUTO_START", identity=execution_identity,
                    limits_reference="recipe_envelope").safety_context,
                voltage_ceiling_v=float(envelope.voltage_ceiling_v),
                state_path=(Path(app._user_recipe_catalog.library.root) /
                            '_runs' / execution_identity.session_id.replace(':', '_') /
                            'runner.json'),
                recipe=selected_recipe,
            )

        requested_i = float(app._cap_current(target_i))
        execution_intent = build_start_execution_intent(
            voltage_v=float(target_v),
            current_a=requested_i,
            mode="AUTO_START",
            identity=execution_identity,
            limits_reference="recipe_envelope",
        )
        enable_attempted = True
        result = await get_or_create_execution_port(app).enable(
            execution_intent,
            identity=execution_identity,
            recipe_voltage_ceiling_v=float(envelope.voltage_ceiling_v),
        )
    except Exception as exc:
        if not enable_attempted:
            app.charge_controller.stop(clear_session=True)
            await message.answer(
                format_start_pre_enable_failure(str(exc)),
                parse_mode=app.ParseMode.HTML,
            )
            return False
        off_confirmed = await _confirm_failed_start_is_off(
            app,
            identity=execution_identity,
            mode="AUTO_START",
        )
        if off_confirmed:
            app.charge_controller.stop(clear_session=True)
        await message.answer(
            format_start_enable_failure(
                type(exc).__name__, off_confirmed=off_confirmed
            ),
            parse_mode=app.ParseMode.HTML,
        )
        return False

    if not result.verified:
        off_confirmed = await _confirm_failed_start_is_off(
            app,
            identity=execution_identity,
            mode="AUTO_START",
        )
        if off_confirmed:
            app.charge_controller.stop(clear_session=True)
        await message.answer(
            format_start_unverified_failure(
                result.reason, off_confirmed=off_confirmed
            ),
            parse_mode=app.ParseMode.HTML,
        )
        return False

    if recipe_binding is not None:
        # The verified START already applied the recipe's initial SET.
        # Persist that step as entered before allowing the next tick:
        # otherwise the runner would issue the identical physical SET again.
        try:
            from application.recipe_existing_session import persist_initial_set
            persist_initial_set(
                recipe_binding, entered_at_s=float(app.time.time())
            )
        except Exception as exc:
            off_confirmed = await _confirm_failed_start_is_off(
                app, identity=execution_identity, mode="AUTO_START",
            )
            if off_confirmed:
                app.charge_controller.stop(clear_session=True)
            else:
                # Physical Output is uncertain: do not release ownership to
                # the ordinary profile tick loop. Keep the selected recipe
                # bound but faulted, so charge_session_tick performs no actions
                # until the operator resolves the physical state.
                app.charge_controller._existing_recipe_execution_binding = recipe_binding
                app.charge_controller._recipe_tick_fault = (
                    f"initial recipe state persistence failed: {type(exc).__name__}"
                )
            await message.answer(
                format_start_persistence_failure(
                    type(exc).__name__, off_confirmed=off_confirmed
                ),
                parse_mode=app.ParseMode.HTML,
            )
            return False
        app.charge_controller._existing_recipe_execution_binding = recipe_binding

    app.last_checkpoint_time = app.time.time()
    app.last_chat_id = message.chat.id
    app.last_user_id = user_id
    start_reason = (
        f"V2_START | USER_RECIPE_FIRST_SET={target_v:.3f}V,{requested_i:.3f}A | "
        if recipe_binding is not None
        else (
            f"V2_START | PREP_SKIPPED_INITIAL_VOLTAGE={battery_v:.3f}V | "
            if prep_skipped
            else "V2_START | PREP_REQUIRED | "
        )
    )
    app.log_event(
        app.charge_controller.current_stage,
        battery_v,
        current,
        temp_ext,
        ah_now,
        f"{start_reason}intent={pending.intent.value} battery={pending.battery_id}",
    )
    await message.answer(
        format_start_success(
            pending.profile,
            pending.capacity_ah,
            pending.intent,
            pending.battery_id,
            battery_voltage_v=battery_v,
            initial_threshold_v=INITIAL_MAIN_THRESHOLD_V,
            prep_skipped=prep_skipped,
            recipe_target_voltage_v=(target_v if recipe_binding is not None else None),
            recipe_target_current_a=(requested_i if recipe_binding is not None else None),
        ),
        parse_mode=app.ParseMode.HTML,
    )
    # Telegram PanelLastMiddleware publishes the single final graph/control
    # panel after the START confirmation message. Calling the historical
    # send_dashboard here races it and can create a second text panel.
    return True
