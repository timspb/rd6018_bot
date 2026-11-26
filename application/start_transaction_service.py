"""Application-owned START transaction service.

This module owns the verified physical START transaction. Historical v2_startup.py
is retained only as a compatibility import facade during ERADICATION-09.
"""

from __future__ import annotations

import html
import asyncio
import tempfile
import time
import uuid
from pathlib import Path
from functools import wraps
from types import SimpleNamespace
from typing import Any

from application.execution_intent.models import ExecutionIntent, SafetyContext
from application.execution_port import get_or_create_execution_port
from application.recipe_policy import chemistry_for_profile
from application.start_transaction_adapter import StartTransactionOutcome, StartPersistenceStatus
from application.start_transaction_validation import (
    canonical_candidate_readback_matches,
    native_off_timestamp_after_receipt,
    start_off_receipt_completed_at,
)
from pb_domain import BatteryIdentity, ChargeContext
from recipe_engine import select_recipe_envelope
from runtime.charge.persistence import read_canonical_session
from runtime.journal.recovery_quarantine import RecoveryQuarantineJournal
from runtime.safety.output_policy import snapshot_from_live
from runtime.safety.runtime_guard import RuntimeSafetyError

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


def execution_identity_for_start(
    *, controller_context: Any, event_context: Any, pending_battery_id: Any, mode: str,
) -> Any:
    """Project existing trace context into the START execution identity."""
    if not isinstance(controller_context, dict):
        controller_context = {}
    trace_id = str(getattr(event_context, "trace_id", "") or "")
    session_id = str(controller_context.get("session_id") or "")
    if not session_id:
        session_id = f"{mode.lower()}:{pending_battery_id}"
    if not trace_id:
        trace_id = f"{mode.lower()}:{session_id}"
    return SimpleNamespace(session_id=session_id, trace_id=trace_id)


def build_start_execution_intent(
    *, voltage_v: float, current_a: float, mode: str, identity: Any, limits_reference: str,
) -> ExecutionIntent:
    """Build the typed physical intent from the already-selected START target."""
    return ExecutionIntent(
        requested_voltage_v=float(voltage_v),
        requested_current_a=float(current_a),
        requested_mode=mode,
        source_decision_id=f"{mode.lower()}:{identity.trace_id}",
        safety_context=SafetyContext(
            telemetry_state="FRESH", lease_state="V2_PHYSICAL_OWNER",
            verification_state="REQUIRED", limits_reference=limits_reference,
        ),
    )


def retire_previous_guard_for_start(controller: Any, *, session_file: Path = Path("charge_session.json"),
                                    quarantine_file: Path = Path("session_recovery_quarantine.json")) -> bool:
    """Retire memory only when an exact previous-session tombstone proves OFF.

    Called by the serialized START owner after independent physical Output-OFF
    preflight. A conflicting, active or unreadable journal fails closed.
    """
    guard = getattr(controller, "_main_current_guard", None)
    if guard is None:
        return True
    try:
        if session_file.is_symlink() or quarantine_file.is_symlink():
            return False
        if session_file.exists():
            if not session_file.is_file() or session_file.stat().st_size > 65536:
                return False
            doc = read_canonical_session(session_file)
            proven=(isinstance(doc, dict)
                    and doc.get("owner") == "runtime.charge.persistence"
                    and doc.get("schema_version") == 1 and doc.get("state") == "retired"
                    and doc.get("stage") == "RETIRED"
                    and doc.get("retirement_kind") == "operator_recovery_clearance"
                    and doc.get("output_intent") == "verified_off"
                    and bool(doc.get("verified_off_transaction_id"))
                    and doc.get("session_id") == guard.session_id
                    and doc.get("battery_id") == guard.battery_id)
        else:
            # A failed new START can remove the retired session document.
            # The canonical operator-clearance journal retains its verified
            # retirement identity; never infer clearance from absence alone.
            if not quarantine_file.is_file() or quarantine_file.stat().st_size > 65536:
                return False
            retired = RecoveryQuarantineJournal(quarantine_file).retirement_binding()
            proven=(bool(retired.get("confirmed_off_evidence"))
                    and retired.get("session_id") == guard.session_id
                    and retired.get("battery_id") == guard.battery_id)
    except (OSError, ValueError, UnicodeError, TypeError):
        return False
    if not proven:
        return False
    controller._main_current_guard = None
    controller._main_current_guard_revision = None
    return True


def _select_initial_auto_target(
    app: Any,
    *,
    battery_v: float,
    temp_ext: float,
    ah_now: float,
    controller: Any | None = None,
    now_s: float | None = None,
) -> tuple[float, float, bool]:
    """Atomically choose PREP or Main before the first Output ON.

    V1 could expose one tick where logical stage=PREP while physical setpoints already
    belonged to Main. V2 removes that split: <12.0 V remains PREP at ~0.01C; >=12.0 V
    starts directly in Main and records the skipped PREP as an audit event.
    """
    controller = controller or app.charge_controller
    if float(battery_v) < INITIAL_MAIN_THRESHOLD_V:
        target_v, target_i = controller._prep_target(temp_ext)
        return float(target_v), float(target_i), False

    now = float(app.time.time()) if now_s is None else float(now_s)
    from runtime.charge.session import set_current_stage
    set_current_stage(controller, controller.STAGE_MAIN, now_s=now)
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
    async def wrapped(app: Any, event: Any, pending: Any) -> Any:
        port = get_or_create_execution_port(app)
        lock = port._guard_owner_lock
        if lock is None:
            raise RuntimeError("START cannot run without canonical owner lock")
        async with lock:
            return await operation(app, event, pending)
    return wrapped


@_serialized_charge_start
async def start_profile_transactional_result(app: Any, event: Any, pending: Any) -> StartTransactionOutcome:
    """Run the single verified START transaction and return its durable outcome."""
    message = event.message if hasattr(event, "message") and event.message is not None else event
    user = getattr(event, "from_user", None) or getattr(message, "from_user", None)
    user_id = user.id if user else 0
    persistence_status = StartPersistenceStatus.NOT_ATTEMPTED
    output_off_confirmed = False
    output_off_unconfirmed = False
    session_contained = False

    def outcome(started: bool, reason: str = "") -> StartTransactionOutcome:
        return StartTransactionOutcome(
            trace_id=str(getattr(getattr(event, "context", None), "trace_id", "") or ""),
            started=started, contained=session_contained,
            output_off_confirmed=output_off_confirmed,
            output_off_unconfirmed=output_off_unconfirmed,
            session_contained=session_contained,
            persistence_status=persistence_status,
            reason=reason or getattr(message, "last_answer", None) or "",
        )

    rd_mode = getattr(app, "rd_control_mode_manager", None)
    if rd_mode is not None and bool(getattr(rd_mode, "hands_off", False)):
        await message.answer(
            "🔓 Режим РД — не лезь включён. Сначала верните контроль заряда; "
            "текущий Output и уставки не изменены."
        )
        return outcome(False)

    if app.charge_controller.is_active:
        await message.answer("⚠️ Сначала остановите текущую программу.")
        return outcome(False)

    port = get_or_create_execution_port(app)
    try:
        port.authorize_managed_start()
    except RuntimeSafetyError as exc:
        await message.answer(f"⚠️ Запуск заблокирован: {exc}")
        return outcome(False)

    if port.session_recovery_guard.quarantined:
        await message.answer(
            "⚠️ Запуск заблокирован после неподтверждённого восстановления. "
            "Сначала требуется отдельное операторское восстановление при подтверждённом Output OFF."
        )
        return outcome(False)

    if getattr(app.charge_controller, "_guarded_restore_candidate", None) is not None:
        await message.answer(
            "⚠️ Запуск заблокирован: сохранённая MAIN Guard сессия остаётся в карантине. "
            "Требуется отдельное подтверждённое восстановление."
        )
        return outcome(False)

    live = await port.read_live()
    snapshot = snapshot_from_live(live)
    if snapshot is None:
        await message.answer(
            "❌ Нет полного набора защитной телеметрии "
            "(U/I/температуры/Output). Запуск запрещён системой защиты."
        )
        return outcome(False)
    if snapshot.output_on:
        await message.answer(
            "❌ RD6018 уже показывает Output ON. Новый запуск разрешён только после подтверждённого OFF."
        )
        return outcome(False)

    # The existing profile START energizes Output before the recipe runner
    # receives its first step. OFF/WAIT-first drafts must never take that path.
    selected_recipe = None
    if getattr(pending, "recipe_id", None) is not None:
        try:
            catalog = app._user_recipe_catalog
            from application.start_recipe_selection import select_user_recipe_for_start
            selected_recipe = select_user_recipe_for_start(
                catalog=catalog, recipe_id=str(pending.recipe_id),
                version=int(pending.recipe_version),
            )
        except (AttributeError, TypeError, ValueError, OSError) as exc:
            await message.answer(
                "❌ Рецепт не готов к START: " + html.escape(str(exc)),
                parse_mode=app.ParseMode.HTML,
            )
            return outcome(False)

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
            return outcome(False)

    battery_v = snapshot.battery_voltage_v
    current = snapshot.current_a
    temp_ext = snapshot.temp_ext_c
    ah_now = app._safe_float(live.get("ah"))

    from runtime.charge.persistence import (
        SESSION_FILE, StartPendingAction, StartPendingStatus,
        begin_start_pending, finish_start_pending, project_session_document,
        read_start_pending,
    )
    from runtime.charge.session import new_trace_identity
    from runtime.output.command_receipt import OutputCommandReceipt

    live_controller = app.charge_controller
    controller_type = type(live_controller)
    started_at = float(app.time.time())
    saved_at = float(app.time.time())
    transaction_id = uuid.uuid4().hex
    execution_identity = execution_identity_for_start(
        controller_context=getattr(live_controller, "recovery_trace_context", {}),
        event_context=getattr(event, "context", None),
        pending_battery_id=getattr(pending, "battery_id", "unbound"),
        mode="AUTO_START",
    )
    try:
        candidate = controller_type(
            app.hass,
            getattr(live_controller, "notify", None),
            host_configuration=live_controller.host_configuration,
            battery_id=pending.battery_id,
            recovery_intent=pending.intent,
            condition_before=pending.condition,
        )
        if candidate is live_controller:
            raise RuntimeError("detached controller identity is not distinct")
        candidate.configure_recovery_context(
            battery_id=pending.battery_id, intent=pending.intent,
            condition_before=pending.condition,
        )
        identity = new_trace_identity(candidate, now=started_at)
        candidate.start(
            pending.profile, int(round(pending.capacity_ah)), now_s=started_at,
            clear_session=False, trace_identity=identity,
        )
        execution_identity = execution_identity_for_start(
            controller_context=getattr(candidate, "recovery_trace_context", {}),
            event_context=getattr(event, "context", None),
            pending_battery_id=getattr(pending, "battery_id", "unbound"),
            mode="AUTO_START",
        )
        candidate._native_recipe_session_selection = selected_native
        target_v, target_i, prep_skipped = _select_initial_auto_target(
            app, battery_v=battery_v, temp_ext=temp_ext, ah_now=ah_now,
            controller=candidate, now_s=started_at,
        )
        battery_identity = BatteryIdentity(
            battery_id=pending.battery_id,
            chemistry=chemistry_for_profile(pending.profile),
            nominal_capacity_ah=float(pending.capacity_ah),
        )
        envelope = select_recipe_envelope(
            ChargeContext(identity=battery_identity, intent=pending.intent,
                          condition=pending.condition),
            expert_high_voltage=False,
        )
        if selected_recipe is not None:
            first = selected_recipe.steps[0]["params"]
            target_v, target_i = float(first["voltage_v"]), float(first["current_a"])
            if target_v > float(envelope.voltage_ceiling_v):
                raise ValueError("initial recipe SET exceeds battery voltage ceiling")
            if abs(float(app._cap_current(target_i)) - target_i) > 1e-6:
                raise ValueError("initial recipe SET exceeds active current limit")
        recipe_binding = None
        if selected_recipe is not None:
            from application.recipe_existing_session import prepare_existing_recipe_binding
            from application.recipe_execution_adapter import RecipeExecutionIdentity
            recipe_binding = prepare_existing_recipe_binding(
                catalog=app._user_recipe_catalog,
                recipe_id=str(pending.recipe_id), version=int(pending.recipe_version),
                port=port,
                recipe=selected_recipe,
                identity=RecipeExecutionIdentity(execution_identity.session_id,
                                                 execution_identity.trace_id),
                safety_context=build_start_execution_intent(
                    voltage_v=float(target_v), current_a=float(app._cap_current(target_i)),
                    mode="AUTO_START", identity=execution_identity,
                    limits_reference="recipe_envelope").safety_context,
                voltage_ceiling_v=float(envelope.voltage_ceiling_v),
                state_path=(Path(app._user_recipe_catalog.library.root) / "_runs" /
                            execution_identity.session_id.replace(":", "_") / "runner.json"),
            )
        requested_i = float(app._cap_current(target_i))
        projection_file = SESSION_FILE
        before_bytes = Path(SESSION_FILE).read_bytes() if Path(SESSION_FILE).exists() else None
        candidate_document = project_session_document(
            candidate, battery_v, current, ah_now,
            session_file=projection_file, now_s=saved_at,
        )
        after_projection = Path(SESSION_FILE).read_bytes() if Path(SESSION_FILE).exists() else None
        if candidate_document is None or after_projection != before_bytes:
            raise RuntimeError("detached canonical projection failed or mutated bytes")
    except Exception as exc:
        await message.answer("START отменён до подготовки: " + html.escape(str(exc)),
                             parse_mode=app.ParseMode.HTML)
        return outcome(False)

    pending_result = begin_start_pending(candidate_document, transaction_id=transaction_id, path=SESSION_FILE)
    if (pending_result.status != StartPendingStatus.COMMITTED
            or pending_result.pending_raw is None or pending_result.pending is None):
        unchanged_preimage = (
            pending_result.status == StartPendingStatus.NOT_COMMITTED
            and pending_result.observed_raw == before_bytes
            and pending_result.pending is None
        )
        persistence_status = (
            StartPersistenceStatus.NOT_ATTEMPTED if unchanged_preimage
            else StartPersistenceStatus.OUTCOME_UNCERTAIN
        )
        session_contained = True
        port.session_recovery_guard.quarantine("start_pending_write_uncertain")
        await message.answer("START заблокирован: не удалось подтвердить START_PENDING.")
        return outcome(False)
    pending_raw, pending_doc = pending_result.pending_raw, pending_result.pending
    persistence_status = StartPersistenceStatus.PENDING
    check_raw, check_doc, check_error = read_start_pending(SESSION_FILE)
    if check_error or check_raw != pending_raw or check_doc != pending_doc:
        persistence_status = StartPersistenceStatus.OUTCOME_UNCERTAIN
        session_contained = True
        port.session_recovery_guard.quarantine("start_pending_readback_mismatch")
        await message.answer("START заблокирован: START_PENDING readback не совпал.")
        return outcome(False)

    def quarantine(reason: str) -> None:
        nonlocal session_contained
        session_contained = True
        port.session_recovery_guard.quarantine(reason)

    def rollback_pending() -> bool:
        nonlocal persistence_status
        result = finish_start_pending(
            pending_raw, pending_doc, action=StartPendingAction.ROLLBACK,
            path=SESSION_FILE,
        )
        if result.status != StartPendingStatus.COMMITTED:
            persistence_status = StartPersistenceStatus.OUTCOME_UNCERTAIN
            quarantine("start_pending_rollback_uncertain")
            return False
        try:
            actual = Path(SESSION_FILE).read_bytes()
        except FileNotFoundError:
            actual = None
        except OSError:
            actual = b"?"
        expected = (pending_doc["previous_raw_utf8"].encode("utf-8")
                    if pending_doc["previous_exists"] else None)
        raw, pending_after, error = read_start_pending(SESSION_FILE)
        if actual != expected or pending_after is not None or error:
            persistence_status = StartPersistenceStatus.OUTCOME_UNCERTAIN
            quarantine("start_pending_rollback_readback_mismatch")
            return False
        persistence_status = StartPersistenceStatus.ROLLED_BACK
        return True

    async def settle_submitted_enable() -> bool:
        nonlocal output_off_confirmed, output_off_unconfirmed, session_contained
        try:
            receipt = await port.request_emergency_off_receipt()
        except BaseException:
            receipt = None
        receipt_completed = start_off_receipt_completed_at(
            receipt, receipt_type=OutputCommandReceipt,
        )
        if receipt_completed is None:
            output_off_unconfirmed = True
            session_contained = True
            quarantine("start_enable_off_receipt_invalid")
            return False
        reader = getattr(app.hass, "get_native_physical_output_report", None)
        if not callable(reader):
            output_off_unconfirmed = True
            session_contained = True
            quarantine("start_enable_native_reader_missing")
            return False
        deadline = asyncio.get_running_loop().time() + 10.0
        while asyncio.get_running_loop().time() < deadline:
            try:
                report = await reader()
            except Exception:
                report = None
            native_timestamp = native_off_timestamp_after_receipt(
                report,
                receipt_completed_monotonic=receipt_completed,
                connection_generation=receipt.connection_generation,
            )
            if (native_timestamp is not None
                    and 0.0 <= time.monotonic() - native_timestamp <= 8.0):
                output_off_confirmed = True
                try:
                    live_controller.stop(clear_session=False)
                except Exception:
                    output_off_unconfirmed = True
                    session_contained = True
                    quarantine("start_post_enable_live_stop_failed")
                    return False
                # A definite pending envelope is the only authority for exact rollback.
                # If COMMIT already landed (or the file changed), preserve those bytes
                # and quarantine rather than attempting a second/invented rollback.
                pending_raw_after, pending_after, pending_error = read_start_pending(SESSION_FILE)
                if (pending_error is not None or pending_raw_after != pending_raw
                        or pending_after != pending_doc):
                    output_off_confirmed = True
                    session_contained = True
                    quarantine("start_pending_not_exact_after_verified_off")
                    return False
                output_off_confirmed = True
                return rollback_pending()
            await asyncio.sleep(0.05)
        output_off_unconfirmed = True
        session_contained = True
        quarantine("start_enable_native_off_evidence_missing")
        return False

    def project_live_against_prior() -> dict[str, Any] | None:
        # The canonical projector fences pending documents. Give it a private
        # copy of the exact embedded prior bytes, keeping the real pending file
        # untouched and preserving the same previous-document extensions.
        with tempfile.TemporaryDirectory(prefix="rd6018-start-project-") as directory:
            projection_path = Path(directory) / "charge_session.json"
            if pending_doc["previous_exists"]:
                projection_path.write_bytes(
                    pending_doc["previous_raw_utf8"].encode("utf-8"))
            return project_session_document(
                live_controller, battery_v, current, ah_now,
                session_file=str(projection_path), now_s=saved_at,
            )

    try:
        # The canonical path now contains START_PENDING. Retirement must be
        # proved against its exact embedded preimage, never the wrapper.
        with tempfile.TemporaryDirectory(prefix="rd6018-start-retire-") as directory:
            prior_projection_path = Path(directory) / "charge_session.json"
            if pending_doc["previous_exists"]:
                prior_projection_path.write_bytes(
                    pending_doc["previous_raw_utf8"].encode("utf-8"))
            if not retire_previous_guard_for_start(
                    live_controller, session_file=prior_projection_path):
                raise RuntimeError("previous MAIN Guard retirement proof failed")
        pause_active = getattr(app, "_operator_pause_active", None)
        if callable(pause_active) and pause_active():
            clear_pause = getattr(app, "_clear_operator_pause", None)
            if not callable(clear_pause):
                raise RuntimeError("\u043f\u0440\u0435\u0434\u044b\u0434\u0443\u0449\u0430\u044f \u043f\u0430\u0443\u0437\u0430 \u0441\u0435\u0441\u0441\u0438\u0438 \u043d\u0435 \u043c\u043e\u0436\u0435\u0442 \u0431\u044b\u0442\u044c \u0431\u0435\u0437\u043e\u043f\u0430\u0441\u043d\u043e \u0441\u0431\u0440\u043e\u0448\u0435\u043d\u0430")
            clear_pause()
            app.log_event(live_controller.current_stage, battery_v, current,
                          temp_ext, ah_now, "OPERATOR_PAUSE_RETIRED_FOR_NEW_SESSION")
        live_controller._existing_recipe_execution_binding = None
        live_controller._recipe_tick_fault = None
        live_controller._native_recipe_session_selection = None
        live_controller.configure_recovery_context(
            battery_id=pending.battery_id, intent=pending.intent,
            condition_before=pending.condition,
        )
        live_controller.start(
            pending.profile, int(round(pending.capacity_ah)), now_s=started_at,
            clear_session=False, trace_identity=identity,
        )
        live_execution_identity = execution_identity_for_start(
            controller_context=getattr(live_controller, "recovery_trace_context", {}),
            event_context=getattr(event, "context", None),
            pending_battery_id=getattr(pending, "battery_id", "unbound"),
            mode="AUTO_START",
        )
        if (live_execution_identity.session_id != execution_identity.session_id
                or live_execution_identity.trace_id != execution_identity.trace_id):
            raise RuntimeError("candidate/live execution identity mismatch")
        live_controller._native_recipe_session_selection = selected_native
        _select_initial_auto_target(
            app, battery_v=battery_v, temp_ext=temp_ext, ah_now=ah_now,
            controller=live_controller, now_s=started_at,
        )
        live_document = project_live_against_prior()
        if live_document != candidate_document:
            raise RuntimeError("detached/live canonical projection parity mismatch")
    except Exception as exc:
        try:
            live_controller.stop(clear_session=False)
        except Exception:
            quarantine("start_pre_enable_live_rollback_failed")
        else:
            rollback_pending()
        await message.answer("START отменён до Output enable: " +
                             html.escape(str(exc)), parse_mode=app.ParseMode.HTML)
        return outcome(False)

    enable_submitted = False
    settlement_task: asyncio.Task | None = None
    try:
        execution_intent = build_start_execution_intent(
            voltage_v=float(target_v), current_a=requested_i,
            mode="AUTO_START", identity=execution_identity,
            limits_reference="recipe_envelope",
        )
        enable_submitted = True
        result = await port.enable(
            execution_intent, identity=execution_identity,
            recipe_voltage_ceiling_v=float(envelope.voltage_ceiling_v),
        )
        if not result.verified:
            settlement_task = asyncio.create_task(settle_submitted_enable())
            off_settled = await asyncio.shield(settlement_task)
            detail = html.escape(getattr(result, "reason", None) or getattr(result, "detail", None) or "RD6018 не подтвердил безопасное включение")
            if off_settled:
                status_text = "Выход подтверждён OFF; START_PENDING точно отменён."
            else:
                status_text = "🚨 OFF не доказан; START_PENDING сохранён, автоматическое управление помещено в карантин."
            await message.answer(
                f"❌ <b>Запуск отменён.</b> {status_text}\n<code>{detail}</code>",
                parse_mode=app.ParseMode.HTML,
            )
            return outcome(False)
        if recipe_binding is not None:
            from dataclasses import replace
            from runtime.charge.programs.recipe_engine import StepState
            from runtime.charge.programs.recipe_runner import RunnerState
            from runtime.charge.programs.recipe_runner_store import save_runner
            recipe = recipe_binding.session.recipe
            initialized = RunnerState(step=StepState(recipe.digest, 0, float(app.time.time())))
            save_runner(recipe_binding.state_path, recipe, initialized)
            recipe_binding.session = replace(recipe_binding.session, state=initialized)
        commit = finish_start_pending(
            pending_raw, pending_doc, candidate_document,
            action=StartPendingAction.COMMIT, path=SESSION_FILE,
        )
        committed_raw, committed_pending, committed_error = read_start_pending(SESSION_FILE)
        # A successful START requires both a definite COMMITTED result and
        # the independent exact canonical readback. Uncertain persistence must
        # enter the single OFF settlement path even if candidate bytes landed.
        if (commit.status != StartPendingStatus.COMMITTED
                or not canonical_candidate_readback_matches(
                    candidate_document,
                    generation=pending_doc["generation"],
                    observed_raw=committed_raw,
                    pending_envelope=committed_pending,
                    read_error=committed_error,
                )):
            persistence_status = StartPersistenceStatus.OUTCOME_UNCERTAIN
            raise RuntimeError("candidate commit exact readback failed")
        persistence_status = StartPersistenceStatus.COMMITTED
        if recipe_binding is not None:
            live_controller._existing_recipe_execution_binding = recipe_binding
    except asyncio.CancelledError:
        if enable_submitted:
            if settlement_task is None:
                settlement_task = asyncio.create_task(settle_submitted_enable())
            while not settlement_task.done():
                try:
                    await asyncio.shield(settlement_task)
                except asyncio.CancelledError:
                    continue
            try:
                settlement_task.result()
            except BaseException:
                quarantine("start_cancel_settlement_failed")
        else:
            try:
                live_controller.stop(clear_session=False)
            except Exception:
                quarantine("start_pre_enable_cancel_stop_failed")
            else:
                rollback_pending()
        raise
    except BaseException as exc:
        if enable_submitted:
            if settlement_task is None:
                settlement_task = asyncio.create_task(settle_submitted_enable())
            cancellation_during_settlement = False
            while not settlement_task.done():
                try:
                    await asyncio.shield(settlement_task)
                except asyncio.CancelledError:
                    cancellation_during_settlement = True
                except BaseException:
                    quarantine("start_enable_settlement_failed")
                    break
            if cancellation_during_settlement:
                try:
                    settlement_task.result()
                except BaseException:
                    quarantine("start_enable_settlement_failed")
                raise asyncio.CancelledError
            try:
                settlement_task.result()
            except BaseException:
                quarantine("start_enable_settlement_failed")
        else:
            try:
                live_controller.stop(clear_session=False)
            except Exception:
                quarantine("start_pre_enable_failure_stop_failed")
            else:
                rollback_pending()
        await message.answer(
            f"❌ Запуск отменён: ошибка транзакции ({html.escape(type(exc).__name__)}).",
            parse_mode=app.ParseMode.HTML,
        )
        return outcome(False)

    app.last_checkpoint_time = app.time.time()
    app.last_chat_id = message.chat.id
    app.last_user_id = user_id
    start_reason = (
        f"V2_START | USER_RECIPE_FIRST_SET={target_v:.3f}V,{requested_i:.3f}A | "
        if recipe_binding is not None else (
            f"V2_START | PREP_SKIPPED_INITIAL_VOLTAGE={battery_v:.3f}V | "
            if prep_skipped else "V2_START | PREP_REQUIRED | "
        )
    )
    app.log_event(live_controller.current_stage, battery_v, current, temp_ext,
                  ah_now, f"{start_reason}intent={pending.intent.value} battery={pending.battery_id}")
    prep_line = (
        f"\nПервый SET рецепта: {target_v:.2f} В / {requested_i:.2f} А."
        if recipe_binding is not None else (
            f"\nPREP пропущен: Uакб={battery_v:.2f} V ≥ {INITIAL_MAIN_THRESHOLD_V:.1f} V."
            if prep_skipped else f"\nPREP: мягкий ток до Uакб ≥ {INITIAL_MAIN_THRESHOLD_V:.1f} V."
        )
    )
    await message.answer(
        f"✅ <b>Заряд запущен</b>\n"
        f"{html.escape(pending.profile)} {pending.capacity_ah:g} Ah · "
        f"{html.escape(_intent_label(pending.intent))}\n"
        f"АКБ: <code>{html.escape(pending.battery_id)}</code>{prep_line}",
        parse_mode=app.ParseMode.HTML,
    )
    return outcome(True, "started")


async def start_profile_transactional(app: Any, event: Any, pending: Any) -> bool:
    """Compatibility wrapper for legacy callers of the single START owner."""
    return (await start_profile_transactional_result(app, event, pending)).started
