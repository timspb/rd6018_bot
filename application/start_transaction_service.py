"""Application-owned START transaction service.

This module owns the verified physical START transaction. Historical v2_startup.py
is retained only as a compatibility import facade during ERADICATION-09.
"""

from __future__ import annotations

import html
from functools import wraps
from types import SimpleNamespace
from typing import Any

from application.execution_intent.models import ExecutionIntent, SafetyContext
from application.execution_port import get_or_create_execution_port
from application.recipe_policy import chemistry_for_profile
from pb_domain import BatteryIdentity, ChargeContext
from recipe_engine import select_recipe_envelope
from safe_output import snapshot_from_live

_START_INTENT_LABELS = {
    "normal": "Обычный заряд",
    "recovery": "Восстановление",
    "conditioning": "Кондиционирование",
    "diagnostic": "Диагностика",
}


def _intent_label(intent: Any) -> str:
    value = str(getattr(intent, "value", intent))
    return _START_INTENT_LABELS.get(value, value)


INITIAL_MAIN_THRESHOLD_V = 12.0


def _execution_identity(app: Any, event: Any, pending: Any, *, mode: str) -> Any:
    controller_context = getattr(app.charge_controller, "recovery_trace_context", {})
    if not isinstance(controller_context, dict):
        controller_context = {}
    event_context = getattr(event, "context", None)
    trace_id = str(getattr(event_context, "trace_id", "") or "")
    session_id = str(controller_context.get("session_id") or "")
    if not session_id:
        session_id = f"{mode.lower()}:{getattr(pending, 'battery_id', 'unbound')}"
    if not trace_id:
        trace_id = f"{mode.lower()}:{session_id}"
    return SimpleNamespace(session_id=session_id, trace_id=trace_id)


def _execution_intent(
    *,
    voltage_v: float,
    current_a: float,
    mode: str,
    identity: Any,
    limits_reference: str,
) -> ExecutionIntent:
    return ExecutionIntent(
        requested_voltage_v=float(voltage_v),
        requested_current_a=float(current_a),
        requested_mode=mode,
        source_decision_id=f"{mode.lower()}:{identity.trace_id}",
        safety_context=SafetyContext(
            telemetry_state="FRESH",
            lease_state="V2_PHYSICAL_OWNER",
            verification_state="REQUIRED",
            limits_reference=limits_reference,
        ),
    )


async def _confirm_failed_start_is_off(app: Any, *, identity: Any, mode: str) -> bool:
    """Request shutdown only through the application-scoped execution owner."""
    try:
        intent = _execution_intent(
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
    main_sample_evidence = getattr(controller, "_main_sample_evidence", None)
    if main_sample_evidence is not None:
        main_sample_evidence.reset()
    target_v, target_i = controller._main_target(temp_ext)
    if hasattr(controller, "_v2_target_voltage_v"):
        controller._v2_target_voltage_v = float(target_v)
    if hasattr(controller, "_v2_last_stage"):
        controller._v2_last_stage = controller.STAGE_MAIN
    return float(target_v), float(target_i), True


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
    selected_recipe = None
    if getattr(pending, "recipe_id", None) is not None:
        try:
            catalog = app._user_recipe_catalog
            selected = catalog.library.load(
                str(pending.recipe_id), int(pending.recipe_version)
            )
            from runtime.charge.programs.recipe_preflight import inspect_recipe
            report = inspect_recipe(selected)
            if not report.admissible_structure:
                raise ValueError("; ".join(report.problems))
            if selected.steps[0]["action"] != "set":
                raise ValueError(
                    "Для START первый шаг пользовательского рецепта должен быть SET. "
                    "Черновик OFF не запускается и не включает Output."
                )
            selected_recipe = selected
        except (AttributeError, TypeError, ValueError, OSError) as exc:
            await message.answer(
                "❌ Рецепт не готов к START: " + html.escape(str(exc)),
                parse_mode=app.ParseMode.HTML,
            )
            return False

    # Resolve the exact native copy before any physical START. The original
    # dynamic algorithm remains the owner; only its accepted settings differ.
    selected_native = None
    native_name = getattr(pending, "native_recipe_name", None)
    if native_name is not None:
        try:
            if selected_recipe is not None:
                raise ValueError("native and user step recipes are mutually exclusive")
            from runtime.charge.programs.native_recipe_draft_library import NativeRecipeDraftLibrary
            from runtime.charge.programs.native_recipe_session import select_native_recipe_version
            catalog = app._user_recipe_catalog
            library = NativeRecipeDraftLibrary(
                catalog.library.root.parent / "native_recipe_drafts")
            selected_native = select_native_recipe_version(
                library, str(native_name),
                int(getattr(pending, "native_recipe_version")),
                profile=pending.profile, intent=pending.intent,
            )
        except (AttributeError, TypeError, ValueError, KeyError, OSError) as exc:
            await message.answer(
                "❌ Копия штатного рецепта не готова к START: "
                + html.escape(str(exc)), parse_mode=app.ParseMode.HTML,
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
    execution_identity = _execution_identity(
        app,
        event,
        pending,
        mode="AUTO_START",
    )

    prep_skipped = False
    enable_attempted = False
    try:
        target_v, target_i, prep_skipped = _select_initial_auto_target(
            app,
            battery_v=battery_v,
            temp_ext=temp_ext,
            ah_now=ah_now,
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
                safety_context=_execution_intent(
                    voltage_v=float(target_v), current_a=float(app._cap_current(target_i)),
                    mode="AUTO_START", identity=execution_identity,
                    limits_reference="recipe_envelope").safety_context,
                voltage_ceiling_v=float(envelope.voltage_ceiling_v),
                state_path=(Path(app._user_recipe_catalog.library.root) /
                            '_runs' / execution_identity.session_id.replace(':', '_') /
                            'runner.json'),
            )

        requested_i = float(app._cap_current(target_i))
        execution_intent = _execution_intent(
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
            await message.answer('START отменён до включения: ' +
                                 html.escape(str(exc)), parse_mode=app.ParseMode.HTML)
            return False
        off_confirmed = await _confirm_failed_start_is_off(
            app,
            identity=execution_identity,
            mode="AUTO_START",
        )
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

    if not result.verified:
        off_confirmed = await _confirm_failed_start_is_off(
            app,
            identity=execution_identity,
            mode="AUTO_START",
        )
        if off_confirmed:
            app.charge_controller.stop(clear_session=True)
            state_text = "Выход подтверждён OFF."
        else:
            state_text = (
                "🚨 <b>Output OFF НЕ подтверждён.</b> Контроллер оставлен активным и заблокированным "
                "для контроля безопасности; проверьте RD6018/HA."
            )
        detail = html.escape(result.reason or "RD6018 не подтвердил безопасное включение")
        await message.answer(
            f"❌ <b>Запуск отменён.</b> {state_text}\n<code>{detail}</code>",
            parse_mode=app.ParseMode.HTML,
        )
        return False

    if recipe_binding is not None:
        # The verified START already applied the recipe's initial SET.
        # Persist that step as entered before allowing the next tick:
        # otherwise the runner would issue the identical physical SET again.
        try:
            from dataclasses import replace
            from runtime.charge.programs.recipe_engine import StepState
            from runtime.charge.programs.recipe_runner import RunnerState
            from runtime.charge.programs.recipe_runner_store import save_runner
            recipe = recipe_binding.session.recipe
            initialized = RunnerState(
                step=StepState(recipe.digest, 0, float(app.time.time()))
            )
            save_runner(recipe_binding.state_path, recipe, initialized)
            recipe_binding.session = replace(recipe_binding.session, state=initialized)
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
                "❌ Сохранение начального состояния рецепта не удалось "
                f"({html.escape(type(exc).__name__)}). "
                + ("Output OFF подтверждён." if off_confirmed
                   else "🚨 Output OFF не подтверждён; проверьте RD6018 вручную."),
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
    prep_line = (
        f"\nПервый SET рецепта: {target_v:.2f} В / {requested_i:.2f} А."
        if recipe_binding is not None
        else (
            f"\nPREP пропущен: Uакб={battery_v:.2f} V ≥ {INITIAL_MAIN_THRESHOLD_V:.1f} V."
            if prep_skipped
            else f"\nPREP: мягкий ток до Uакб ≥ {INITIAL_MAIN_THRESHOLD_V:.1f} V."
        )
    )
    await message.answer(
        f"✅ <b>Заряд запущен</b>\n"
        f"{html.escape(pending.profile)} {pending.capacity_ah:g} Ah · "
        f"{html.escape(_intent_label(pending.intent))}\n"
        f"АКБ: <code>{html.escape(pending.battery_id)}</code>{prep_line}",
        parse_mode=app.ParseMode.HTML,
    )
    try:
        old = app.user_dashboard.get(user_id)
        await app.send_dashboard(message, old_msg_id=old)
    except Exception:
        pass
    return True
