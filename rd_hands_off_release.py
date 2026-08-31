from __future__ import annotations

import logging
import types
from typing import Any, Optional

from aiogram import F
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from manual_mode import ManualSessionState
from rd_control_mode import RdControlMode, RdControlModeManager
from runtime_safety import RuntimeSafetyError


logger = logging.getLogger(__name__)


def _auto_active(app: Any) -> bool:
    controller = getattr(app, "charge_controller", None)
    return bool(controller is not None and getattr(controller, "is_active", False))


def _manual_active(app: Any) -> bool:
    manual = getattr(app, "manual_session_manager", None)
    return bool(manual is not None and getattr(manual, "is_active", False))


def _managed_active(app: Any) -> bool:
    return _auto_active(app) or _manual_active(app)


def _active_session_token(app: Any) -> Optional[str]:
    """Stable identity for one destructive-release confirmation epoch."""
    active_auto = _auto_active(app)
    active_manual = _manual_active(app)
    if active_auto and active_manual:
        return None
    if active_auto:
        controller = app.charge_controller
        try:
            context = controller.recovery_trace_context
        except Exception:
            context = None
        if isinstance(context, dict):
            session_id = str(context.get("session_id") or "").strip()
            if session_id:
                return f"auto:{session_id}"
        started = getattr(controller, "total_start_time", None)
        if started:
            return f"auto-fallback:{float(started):.6f}"
        # Test/dev controllers may not expose the production trace identity. Object
        # identity is process-local and is still safer than an unbound confirmation.
        return f"auto-object:{id(controller)}"
    if active_manual:
        manual = app.manual_session_manager
        started = float(getattr(manual, "started_at", 0.0) or 0.0)
        if started > 0:
            return f"manual:{started:.6f}"
        return f"manual-object:{id(manual)}"
    return None


def _mark_auto_mix_released(controller: Any) -> None:
    if str(getattr(controller, "current_stage", "")) != str(
        getattr(controller, "STAGE_MIX", "Mix")
    ):
        return
    authority = getattr(controller, "_mix_active_authority", None)
    session_id_fn = getattr(controller, "_mix_authority_session_id", None)
    if authority is None or not callable(session_id_fn):
        return
    mark_terminal = getattr(authority, "mark_terminal", None)
    if not callable(mark_terminal):
        return
    try:
        mark_terminal(session_id_fn(), "RELEASED_TO_RD_HANDS_OFF")
    except Exception as exc:
        # Durable HANDS_OFF remains the outer actuator boundary. Preserve the error for
        # operator/audit visibility, but never re-acquire RD control merely because a
        # chemistry-accounting record could not be terminalized.
        logger.warning("Failed to terminalize Mix authority during RD release: %s", exc)


def _retire_auto_without_output_change(app: Any) -> None:
    controller = getattr(app, "charge_controller", None)
    if controller is None:
        return
    if getattr(controller, "is_active", False):
        _mark_auto_mix_released(controller)
        stop = getattr(controller, "stop", None)
        if not callable(stop):
            raise RuntimeSafetyError(
                "RD HANDS_OFF could not retire automatic charge software authority"
            )
        stop(clear_session=True)
    clear = getattr(controller, "_clear_session_file", None)
    if callable(clear):
        clear()
    if getattr(controller, "is_active", False):
        raise RuntimeSafetyError(
            "RD HANDS_OFF automatic software authority remained active after retirement"
        )


async def _retire_manual_without_output_change(app: Any) -> None:
    manual = getattr(app, "manual_session_manager", None)
    if manual is None or not getattr(manual, "is_active", False):
        return

    retire = getattr(manual, "_retire_runner", None)
    if callable(retire):
        await retire()
    else:
        task = getattr(manual, "_task", None)
        if task is not None and not task.done():
            task.cancel()

    # This is deliberately not ManualSessionManager.stop(): stop() owns a physical
    # Output OFF. Releasing RD ownership retires only software timers/evidence/tasks.
    manual.state = ManualSessionState.STOPPED
    manual.stop_reason = "released_to_rd_hands_off"
    manual.cooling_started_at = None
    if hasattr(manual, "_previous_voltage_v"):
        manual._previous_voltage_v = None
    if hasattr(manual, "_previous_current_a"):
        manual._previous_current_a = None
    reset_delta = getattr(manual, "_reset_delta_tracking", None)
    if callable(reset_delta):
        reset_delta()
    persist = getattr(manual, "_persist", None)
    if callable(persist):
        persist()

    task = getattr(manual, "_task", None)
    if getattr(manual, "is_active", False) or (task is not None and not task.done()):
        raise RuntimeSafetyError(
            "RD HANDS_OFF Manual software authority remained active after retirement"
        )


def _edge_release_api(manager: RdControlModeManager) -> Any:
    guard = manager.guard
    if not bool(getattr(guard, "edge_lease_enforced", False)):
        return None
    lease = getattr(guard, "edge_safety_lease", None)
    if lease is None:
        raise RuntimeSafetyError(
            "RD HANDS_OFF blocked: edge safety lease is required but unavailable"
        )
    required = (
        "suspend_renewals",
        "resume_renewals",
        "prepare_hands_off_release",
        "release_to_hands_off",
    )
    if any(not callable(getattr(lease, name, None)) for name in required):
        raise RuntimeSafetyError(
            "RD HANDS_OFF blocked: installed edge lease has no live-Output ownership-release contract"
        )
    return lease


async def _release_active_transaction(
    app: Any,
    manager: RdControlModeManager,
    *,
    expected_token: str,
) -> bool:
    """Transfer one exact active session to durable HANDS_OFF without touching Output."""
    async with manager._transition_lock:
        if manager.hands_off:
            return True
        if bool(getattr(manager.guard, "_off_unconfirmed", False)):
            raise RuntimeSafetyError(
                "RD HANDS_OFF blocked: previous managed Output OFF is still unconfirmed"
            )

        current_token = _active_session_token(app)
        if current_token is None:
            raise RuntimeSafetyError(
                "RD HANDS_OFF blocked: managed authority is absent or internally inconsistent"
            )
        if current_token != expected_token:
            raise RuntimeSafetyError(
                "RD HANDS_OFF confirmation is stale: active charge session changed"
            )

        lease = _edge_release_api(manager)
        prepared = None

        # Provisional in-memory HANDS_OFF is a transition barrier only. It blocks new
        # starts/writes and prevents the normal managed get_all_live path from issuing
        # another lease heartbeat while the edge release is prepared. Durability is
        # committed only after the edge API itself is proved available and healthy.
        manager._release_in_progress = True
        manager.mode = RdControlMode.HANDS_OFF
        manager.guard._orphan_output_seen_at = None
        if lease is not None:
            lease.suspend_renewals()
        try:
            if lease is not None:
                prepared = await lease.prepare_hands_off_release()
            manager._write_mode(RdControlMode.HANDS_OFF)
        except Exception as exc:
            manager.mode = RdControlMode.PB_MANAGED
            manager._release_in_progress = False
            if lease is not None:
                lease.resume_renewals()
            if isinstance(exc, RuntimeSafetyError):
                raise
            raise RuntimeSafetyError(
                f"RD HANDS_OFF blocked before ownership commit: {exc}"
            ) from exc

        # From the durable commit onward the bot must never silently fall back to
        # PB_MANAGED: the edge command may have reached ESPHome even if its ACK is
        # subsequently lost. HANDS_OFF therefore remains the conservative authority
        # on every post-commit error; the local lease may still turn Output OFF later.
        edge_error: Optional[Exception] = None
        cleanup_errors: list[str] = []
        if lease is not None:
            try:
                await lease.release_to_hands_off(
                    expected_generation=getattr(prepared, "generation", None)
                )
            except Exception as exc:
                edge_error = exc

        try:
            await _retire_manual_without_output_change(app)
        except Exception as exc:
            logger.error("Failed to fully retire Manual state after RD release: %s", exc)
            cleanup_errors.append(f"Manual cleanup: {type(exc).__name__}: {exc}")
        try:
            _retire_auto_without_output_change(app)
        except Exception as exc:
            logger.error("Failed to fully retire AUTO state after RD release: %s", exc)
            cleanup_errors.append(f"AUTO cleanup: {type(exc).__name__}: {exc}")

        manager._release_in_progress = False

        if edge_error is not None or cleanup_errors:
            details: list[str] = []
            if edge_error is not None:
                details.append(
                    "edge ownership release was not positively acknowledged; local watchdog may still turn Output OFF"
                )
            details.extend(cleanup_errors)
            raise RuntimeSafetyError(
                "RD HANDS_OFF is durably active, but transfer completed with containment warning: "
                + "; ".join(details)
            )

        if _managed_active(app):
            raise RuntimeSafetyError(
                "RD HANDS_OFF is active, but stale managed software authority is still present"
            )
        return True


def _install_release_confirmation_ui(
    app: Any,
    manager: RdControlModeManager,
) -> None:
    router = getattr(app, "router", None)
    original_dashboard = getattr(app, "_build_dashboard_keyboard", None)
    if router is None or not callable(original_dashboard):
        return
    if bool(getattr(manager, "_active_release_ui_installed", False)):
        return

    pending: dict[int, str] = {}

    def build_dashboard_keyboard(
        is_on: bool,
        user_id: int,
        *,
        back_to_dashboard: bool = False,
    ) -> InlineKeyboardMarkup:
        markup = original_dashboard(
            is_on,
            user_id,
            back_to_dashboard=back_to_dashboard,
        )
        if manager.hands_off or back_to_dashboard or not _managed_active(app):
            return markup

        rows: list[list[InlineKeyboardButton]] = []
        for row in markup.inline_keyboard:
            replaced: list[InlineKeyboardButton] = []
            for button in row:
                if str(getattr(button, "callback_data", "") or "") == "rd_hands_off_enable":
                    replaced.append(
                        InlineKeyboardButton(
                            text=button.text,
                            callback_data="rd_hands_off_release_confirm",
                        )
                    )
                else:
                    replaced.append(button)
            rows.append(replaced)
        return InlineKeyboardMarkup(inline_keyboard=rows)

    app._build_dashboard_keyboard = build_dashboard_keyboard

    async def prompt_active_release(call: Any) -> None:
        if not await app._check_chat_and_respond(call):
            return
        token = _active_session_token(app)
        if token is None:
            await call.answer(
                "Активная управляемая сессия уже изменилась или отсутствует",
                show_alert=True,
            )
            return
        user = getattr(call, "from_user", None)
        user_id = int(getattr(user, "id", 0) or 0)
        pending[user_id] = token
        await call.answer()
        await call.message.answer(
            "⚠️ <b>Отпустить RD6018 из-под управления ботом?</b>\n\n"
            "После подтверждения зарядная автоматика, Delta и таймеры будут сняты, "
            "edge-lease будет передан в HANDS_OFF, а текущий Output и V/I/OVP/OCP останутся без изменений.\n\n"
            "Pb-защита бота больше не будет вмешиваться, пока включён режим РД — не лезь.",
            parse_mode=app.ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="🔓 ОТПУСТИТЬ РД",
                            callback_data="rd_hands_off_release_execute",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="Отмена",
                            callback_data="rd_hands_off_release_cancel",
                        )
                    ],
                ]
            ),
        )

    # The base rd_hands_off_enable handler consults this dynamically. Therefore even
    # an old Telegram message carrying the pre-confirmation callback cannot bypass the
    # two-step active-session release contract.
    manager._active_release_prompt = prompt_active_release

    @router.callback_query(F.data == "rd_hands_off_release_confirm")
    async def _confirm_active_release(call: Any) -> None:
        await prompt_active_release(call)

    @router.callback_query(F.data == "rd_hands_off_release_execute")
    async def _execute_active_release(call: Any) -> None:
        if not await app._check_chat_and_respond(call):
            return
        user = getattr(call, "from_user", None)
        user_id = int(getattr(user, "id", 0) or 0)
        expected = pending.pop(user_id, None)
        current = _active_session_token(app)
        if expected is None or current is None or current != expected:
            await call.answer(
                "Подтверждение устарело: активная сессия изменилась. Откройте действие заново.",
                show_alert=True,
            )
            return

        manager._active_release_authorization_token = expected
        try:
            await manager.enter_hands_off()
        except Exception as exc:
            if manager.hands_off:
                await call.answer("HANDS_OFF включён с предупреждением", show_alert=True)
                await call.message.answer(
                    "⚠️ <b>Режим РД уже зафиксирован.</b>\n"
                    f"{str(exc)}\n"
                    "Не считайте edge-watchdog снятым, пока это не подтверждено телеметрией.",
                    parse_mode=app.ParseMode.HTML,
                )
            else:
                await call.answer(str(exc), show_alert=True)
            return
        finally:
            manager._active_release_authorization_token = None

        await call.answer("Режим РД включён")
        await call.message.answer(
            "🔓 <b>Режим РД — не лезь включён.</b>\n"
            "Зарядная автоматика отпущена. Текущий Output и уставки не изменялись.",
            parse_mode=app.ParseMode.HTML,
        )

    @router.callback_query(F.data == "rd_hands_off_release_cancel")
    async def _cancel_active_release(call: Any) -> None:
        if not await app._check_chat_and_respond(call):
            return
        user = getattr(call, "from_user", None)
        user_id = int(getattr(user, "id", 0) or 0)
        pending.pop(user_id, None)
        await call.answer("Отменено")

    manager._active_release_ui_installed = True


def install_rd_hands_off_release(
    app: Any,
    manager: RdControlModeManager,
) -> RdControlModeManager:
    """Allow an explicitly confirmed active managed charge to become HANDS_OFF.

    The active path is distinct from normal verified-OFF lease disarm. It requires the
    edge node's dedicated live-Output ownership-release contract, binds confirmation to
    one exact session, serializes against other RD ownership transitions, and never
    rolls back to PB_MANAGED after the durable HANDS_OFF commit if edge ACK is lost.
    """
    if bool(getattr(manager, "_active_release_installed", False)):
        _install_release_confirmation_ui(app, manager)
        return manager

    original_enter = manager.enter_hands_off

    async def enter_hands_off_with_active_release(self: RdControlModeManager) -> bool:
        if self.hands_off:
            return True
        if not _managed_active(app):
            return bool(await original_enter())

        expected = getattr(self, "_active_release_authorization_token", None)
        current = _active_session_token(app)
        if expected is None or current is None or expected != current:
            raise RuntimeSafetyError(
                "RD HANDS_OFF blocked: active managed charge requires a fresh explicit confirmation"
            )
        # Single-use authorization; the transaction revalidates the same token again
        # after acquiring the ownership-transition lock.
        self._active_release_authorization_token = None
        return bool(
            await _release_active_transaction(
                app,
                self,
                expected_token=expected,
            )
        )

    manager.enter_hands_off = types.MethodType(
        enter_hands_off_with_active_release,
        manager,
    )
    manager._active_release_authorization_token = None
    manager._active_release_installed = True

    # A process may have crashed after durable HANDS_OFF was written but before the
    # old AUTO session file was retired. Never let that stale restore authority survive
    # merely because the process restarted in HANDS_OFF.
    if manager.hands_off:
        try:
            manager._clear_stale_auto_restore_authority()
        except Exception as exc:
            logger.error("Failed to clear stale AUTO restore state in HANDS_OFF: %s", exc)

    _install_release_confirmation_ui(app, manager)
    return manager
