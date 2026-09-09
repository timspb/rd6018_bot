from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional, Tuple

import charge_logic


DONE_STATE_VERSION = 1
DONE_COMPLETION_STORAGE = "storage"
DONE_COMPLETION_TERMINAL = "terminal"
DONE_OUTPUT_ON = "on"
DONE_OUTPUT_OFF = "off"


def _set_done_outcome(
    controller: Any,
    completion_kind: Optional[str],
    output_intent: str,
    *,
    authoritative: bool,
) -> None:
    controller._done_completion_kind = completion_kind
    controller._done_output_intent = output_intent
    controller._done_outcome_authoritative = bool(authoritative)


def _read_session_document() -> Dict[str, Any]:
    path = charge_logic.SESSION_FILE
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            document = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {}
    return document if isinstance(document, dict) else {}


def _explicit_storage_outcome(document: Dict[str, Any]) -> bool:
    return (
        document.get("done_state_version") == DONE_STATE_VERSION
        and document.get("completion_kind") == DONE_COMPLETION_STORAGE
        and document.get("output_intent") == DONE_OUTPUT_ON
    )


def _write_done_outcome(controller: Any) -> None:
    if controller.current_stage != controller.STAGE_DONE:
        return
    document = _read_session_document()
    if not document:
        return

    completion_kind = getattr(controller, "_done_completion_kind", None)
    output_intent = getattr(controller, "_done_output_intent", DONE_OUTPUT_OFF)
    if completion_kind != DONE_COMPLETION_STORAGE or output_intent != DONE_OUTPUT_ON:
        completion_kind = DONE_COMPLETION_TERMINAL
        output_intent = DONE_OUTPUT_OFF

    document["done_state_version"] = DONE_STATE_VERSION
    document["completion_kind"] = completion_kind
    document["output_intent"] = output_intent

    terminal_metadata = document.get("terminal_metadata")
    if isinstance(terminal_metadata, dict):
        terminal_metadata["completion_kind"] = completion_kind
        terminal_metadata["output_intent"] = output_intent

    if completion_kind == DONE_COMPLETION_STORAGE:
        # The legacy save happens before the queued SAFE_WAIT -> Done setpoint writes
        # reach RD6018, so _device_set_* may still contain the old Mix/HV program.
        # A resumable Storage record must therefore persist the canonical Storage
        # target, never the last observed device setpoint.
        target_v, target_i = controller._storage_target()
        document["target_voltage"] = float(target_v)
        document["target_current"] = float(target_i)
        document["target_finish_time"] = None
        document["finish_timer_start"] = None

    path = charge_logic.SESSION_FILE
    tmp_path = f"{path}.done-outcome.tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as handle:
            json.dump(document, handle, ensure_ascii=False, indent=2)
        os.replace(tmp_path, path)
    except OSError:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except OSError:
            pass
        raise


def restore_allows_auto_enable(controller: Any) -> bool:
    """Fail closed for restored Done unless durable state proves managed Storage."""
    done_stage = getattr(controller, "STAGE_DONE", "Done")
    if controller.current_stage == done_stage:
        return bool(
            getattr(controller, "_done_outcome_authoritative", False)
            and getattr(controller, "_done_completion_kind", None)
            == DONE_COMPLETION_STORAGE
            and getattr(controller, "_done_output_intent", DONE_OUTPUT_OFF)
            == DONE_OUTPUT_ON
        )
    cooling_stage = getattr(controller, "STAGE_COOLING", None)
    if cooling_stage is not None and controller.current_stage == cooling_stage:
        return False
    return True


def _paused_done_resume_is_authorized(app: Any, controller: Any) -> bool:
    """Apply the same durable Done intent to the separate operator-pause resume path."""
    pause_active = getattr(app, "_operator_pause_active", None)
    if not callable(pause_active) or not bool(pause_active()):
        return True

    done_stage = getattr(controller, "STAGE_DONE", "Done")
    if controller.current_stage == done_stage:
        return restore_allows_auto_enable(controller)

    if bool(getattr(controller, "is_active", False)):
        return True

    # After a process restart the controller may still be Idle until the pause handler
    # calls try_restore_session(). Inspect the durable document *before* that call so a
    # legacy/terminal Done record cannot use the pause UI as an alternate energization
    # path around the normal startup restore guard.
    document = _read_session_document()
    if document.get("stage") != done_stage:
        return True
    return _explicit_storage_outcome(document)


def install_done_storage_restore(app: Any) -> None:
    """Add explicit durable Done/Storage output intent to the final production controller.

    Historically the same ``Done`` stage represented two physically opposite states:
    normal managed Storage (Output ON) and terminal/fault stop (Output OFF).  The legacy
    restore guard therefore had to block every Done restore.  This composition wrapper
    records the distinction durably and lets only an explicitly persisted Storage
    outcome pass the existing full safe-enable restore transaction.
    """
    if getattr(app, "_done_storage_restore_installed", False):
        return

    controller = app.charge_controller
    _set_done_outcome(
        controller,
        None,
        DONE_OUTPUT_OFF,
        authoritative=False,
    )
    controller._done_transition_source_stage = None

    original_save_session = controller._save_session
    original_try_restore_session = controller.try_restore_session
    original_tick = controller.tick
    original_operator_pause_toggle = getattr(app, "_operator_pause_toggle", None)

    def save_session_with_done_outcome(voltage: float, current: float, ah: float) -> Any:
        if controller.current_stage == controller.STAGE_DONE:
            source_stage = getattr(controller, "_done_transition_source_stage", None)
            if (
                source_stage == controller.STAGE_SAFE_WAIT
                and getattr(controller, "previous_stage", None) == controller.STAGE_SAFE_WAIT
            ):
                _set_done_outcome(
                    controller,
                    DONE_COMPLETION_STORAGE,
                    DONE_OUTPUT_ON,
                    authoritative=True,
                )
            elif not getattr(controller, "_done_outcome_authoritative", False):
                _set_done_outcome(
                    controller,
                    DONE_COMPLETION_TERMINAL,
                    DONE_OUTPUT_OFF,
                    authoritative=True,
                )
        else:
            _set_done_outcome(
                controller,
                None,
                DONE_OUTPUT_OFF,
                authoritative=False,
            )

        result = original_save_session(voltage, current, ah)
        if controller.current_stage == controller.STAGE_DONE:
            _write_done_outcome(controller)
        return result

    def try_restore_session_with_done_outcome(*args: Any, **kwargs: Any) -> Tuple[bool, Optional[str]]:
        document = _read_session_document()
        _set_done_outcome(
            controller,
            None,
            DONE_OUTPUT_OFF,
            authoritative=False,
        )
        ok, message = original_try_restore_session(*args, **kwargs)
        if not ok:
            return ok, message

        if controller.current_stage == controller.STAGE_DONE:
            if _explicit_storage_outcome(document):
                _set_done_outcome(
                    controller,
                    DONE_COMPLETION_STORAGE,
                    DONE_OUTPUT_ON,
                    authoritative=True,
                )
            else:
                # Legacy, corrupt, diagnostic and otherwise ambiguous Done records are
                # normalized to OFF.  Missing metadata can never infer energization.
                _set_done_outcome(
                    controller,
                    DONE_COMPLETION_TERMINAL,
                    DONE_OUTPUT_OFF,
                    authoritative=True,
                )
            _write_done_outcome(controller)
        else:
            _set_done_outcome(
                controller,
                None,
                DONE_OUTPUT_OFF,
                authoritative=False,
            )
        return ok, message

    async def tick_with_done_outcome(*args: Any, **kwargs: Any) -> Any:
        stage_before = controller.current_stage
        if stage_before != controller.STAGE_DONE:
            # Clear any prior Done authority before an active stage can reach another
            # terminal state.  SAFE_WAIT is reclassified to Storage only if the same
            # live tick actually performs SAFE_WAIT -> Done.
            _set_done_outcome(
                controller,
                None,
                DONE_OUTPUT_OFF,
                authoritative=False,
            )
        controller._done_transition_source_stage = stage_before
        try:
            return await original_tick(*args, **kwargs)
        finally:
            controller._done_transition_source_stage = None

    async def operator_pause_toggle_with_done_guard(call: Any) -> Any:
        if not _paused_done_resume_is_authorized(app, controller):
            return (
                "Продолжение заблокировано: сохранённый Done не имеет "
                "подтверждённого Storage Output ON intent"
            )
        assert callable(original_operator_pause_toggle)
        return await original_operator_pause_toggle(call)

    controller._save_session = save_session_with_done_outcome
    controller.try_restore_session = try_restore_session_with_done_outcome
    controller.tick = tick_with_done_outcome
    app._restore_allows_auto_enable = restore_allows_auto_enable
    if callable(original_operator_pause_toggle):
        app._operator_pause_toggle = operator_pause_toggle_with_done_guard
    app._done_storage_restore_installed = True
