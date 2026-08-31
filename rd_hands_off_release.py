from __future__ import annotations

import logging
import types
from typing import Any

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


async def _disarm_edge_lease(manager: RdControlModeManager) -> None:
    guard = manager.guard
    if not bool(getattr(guard, "edge_lease_enforced", False)):
        return
    lease = getattr(guard, "edge_safety_lease", None)
    if lease is None:
        raise RuntimeSafetyError(
            "RD HANDS_OFF blocked: edge safety lease cannot be disarmed"
        )
    try:
        disarmed = bool(await lease.disarm())
    except Exception as exc:
        raise RuntimeSafetyError(
            f"RD HANDS_OFF blocked: edge safety lease disarm failed: {exc}"
        ) from exc
    if not disarmed:
        raise RuntimeSafetyError(
            "RD HANDS_OFF blocked: edge safety lease disarm was not confirmed"
        )


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
        # HANDS_OFF durability itself is the authority boundary. A stale diagnostic
        # clock must not be allowed to re-acquire the actuator, so failure here is
        # logged but cannot undo an already-committed operator release.
        logger.warning("Failed to terminalize Mix authority during RD release: %s", exc)


def _retire_auto_without_output_change(app: Any) -> None:
    controller = getattr(app, "charge_controller", None)
    if controller is None or not getattr(controller, "is_active", False):
        return
    _mark_auto_mix_released(controller)
    stop = getattr(controller, "stop", None)
    if not callable(stop):
        raise RuntimeSafetyError(
            "RD HANDS_OFF could not retire automatic charge software authority"
        )
    stop(clear_session=True)


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


def install_rd_hands_off_release(
    app: Any,
    manager: RdControlModeManager,
) -> RdControlModeManager:
    """Allow the operator to release an active managed charge without touching Output.

    The persistent HANDS_OFF decision is committed before software charge authority is
    retired. The edge lease is then positively disarmed while the managed session is
    still intact. Only after both steps succeed does in-process HANDS_OFF become active;
    from that instant the outer actuator wrapper blocks every bot write while AUTO or
    Manual runners are retired without issuing Output OFF or rewriting setpoints.
    """
    if bool(getattr(manager, "_active_release_installed", False)):
        return manager

    original_enter = manager.enter_hands_off

    async def enter_hands_off_with_active_release(self: RdControlModeManager) -> bool:
        if self.hands_off:
            return True
        if bool(getattr(self.guard, "_off_unconfirmed", False)):
            raise RuntimeSafetyError(
                "RD HANDS_OFF blocked: previous managed Output OFF is still unconfirmed"
            )

        active_auto = _auto_active(app)
        active_manual = _manual_active(app)
        if not active_auto and not active_manual:
            return bool(await original_enter())

        # Commit the operator's ownership choice first. If edge disarm then fails,
        # roll the durable choice back while managed software authority is still live.
        self._write_mode(RdControlMode.HANDS_OFF)
        try:
            await _disarm_edge_lease(self)
        except Exception:
            try:
                self._write_mode(RdControlMode.PB_MANAGED)
            except Exception as rollback_exc:
                logger.error(
                    "RD HANDS_OFF durable rollback failed after lease-disarm failure: %s",
                    rollback_exc,
                )
            raise

        # From this point onward no background task is allowed to touch the RD6018.
        self.mode = RdControlMode.HANDS_OFF
        self.guard._orphan_output_seen_at = None

        # Retire software ownership only; do not invoke managed stop paths because
        # those are defined to perform verified physical OFF.
        try:
            await _retire_manual_without_output_change(app)
        except Exception as exc:
            logger.error("Failed to fully retire Manual state after RD release: %s", exc)
            manual = getattr(app, "manual_session_manager", None)
            if manual is not None:
                manual.state = ManualSessionState.STOPPED
                manual.stop_reason = "released_to_rd_hands_off"
                manual.cooling_started_at = None
        try:
            _retire_auto_without_output_change(app)
        except Exception as exc:
            logger.error("Failed to fully retire AUTO state after RD release: %s", exc)
            controller = getattr(app, "charge_controller", None)
            if controller is not None and hasattr(controller, "current_stage"):
                try:
                    controller.current_stage = getattr(controller, "STAGE_IDLE", "Idle")
                except Exception:
                    pass

        return True

    manager.enter_hands_off = types.MethodType(
        enter_hands_off_with_active_release,
        manager,
    )
    manager._active_release_installed = True
    return manager
