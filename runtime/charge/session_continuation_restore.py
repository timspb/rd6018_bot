"""Restore typed SAFE_WAIT continuations from a persisted session snapshot."""

from __future__ import annotations

from typing import Any, Mapping

from runtime.charge.strategy.final_safe_wait import (
    FinalSafeWaitContinuation,
    validate_final_continuation,
)
from runtime.charge.strategy.recovery_safe_wait import (
    RecoverySafeWaitContinuation,
    validate_recovery_continuation,
)


def restore_recovery_safe_wait(host: Any, document: Mapping[str, Any]) -> None:
    host._recovery_safe_wait = None
    raw = document.get("v2_recovery_safe_wait")
    if isinstance(raw, dict):
        try:
            raw_generation = raw.get("session_generation")
            candidate = RecoverySafeWaitContinuation(
                source_stage=str(raw.get("source_stage") or ""),
                next_stage=str(raw.get("next_stage") or ""),
                target_voltage_v=float(raw.get("target_voltage_v")),
                target_current_a=float(raw.get("target_current_a")),
                started_at=float(raw.get("started_at")),
                session_id=str(raw.get("session_id") or host._v2_trace_session_id or "") or None,
                session_generation=(float(raw_generation) if raw_generation is not None
                                    else float(host._v2_trace_started_at)),
                recovery_attempt=int(raw.get("recovery_attempt", host.antisulfate_count)),
                agm_stage_idx=int(raw.get("agm_stage_idx", host._agm_stage_idx)),
            )
        except (TypeError, ValueError, OverflowError):
            candidate = None
        if (candidate is not None and validate_recovery_continuation(
                candidate, session_id=host._v2_trace_session_id,
                session_generation=host._v2_trace_started_at,
                expected_source_stage=host.STAGE_DESULFATION,
                expected_next_stage=host.STAGE_MAIN,
        ) and candidate.recovery_attempt == int(host.antisulfate_count)
                and candidate.agm_stage_idx == int(host._agm_stage_idx)):
            host._recovery_safe_wait = candidate
        return

    # One-way migration from the pre-cutover persisted SAFE_WAIT representation.
    if (host.current_stage == host.STAGE_SAFE_WAIT
            and host._safe_wait_next_stage == host.STAGE_MAIN
            and host._safe_wait_target_v > 0.0 and host._safe_wait_target_i > 0.0
            and host._safe_wait_start > 0.0):
        host._recovery_safe_wait = RecoverySafeWaitContinuation(
            source_stage=host.STAGE_DESULFATION, next_stage=host.STAGE_MAIN,
            target_voltage_v=float(host._safe_wait_target_v),
            target_current_a=float(host._safe_wait_target_i),
            started_at=float(host._safe_wait_start), session_id=host._v2_trace_session_id,
            session_generation=float(host._v2_trace_started_at),
            recovery_attempt=int(host.antisulfate_count), agm_stage_idx=int(host._agm_stage_idx),
        )


def restore_final_safe_wait(host: Any, document: Mapping[str, Any]) -> None:
    host._final_safe_wait = None
    raw = document.get("v2_final_safe_wait")
    if isinstance(raw, dict):
        try:
            raw_generation = raw.get("session_generation")
            candidate = FinalSafeWaitContinuation(
                source_stage=str(raw.get("source_stage") or ""),
                next_stage=str(raw.get("next_stage") or ""),
                target_voltage_v=float(raw.get("target_voltage_v")),
                target_current_a=float(raw.get("target_current_a")),
                started_at=float(raw.get("started_at")),
                session_id=str(raw.get("session_id") or host._v2_trace_session_id or "") or None,
                completion_reason=str(raw.get("completion_reason") or ""),
                session_generation=(float(raw_generation) if raw_generation is not None
                                    else float(host._v2_trace_started_at)),
            )
        except (TypeError, ValueError, OverflowError):
            candidate = None
        if candidate is not None and validate_final_continuation(
                candidate, session_id=host._v2_trace_session_id,
                session_generation=host._v2_trace_started_at,
                expected_next_stage=host.STAGE_DONE,
                allowed_source_stages={host.STAGE_MAIN, host.STAGE_MIX}):
            host._final_safe_wait = candidate
        return

    # One-way migration from pre-cutover successful final SAFE_WAIT.
    if (host.current_stage == host.STAGE_SAFE_WAIT
            and host._safe_wait_next_stage == host.STAGE_DONE
            and host._safe_wait_target_v > 0.0 and host._safe_wait_target_i > 0.0
            and host._safe_wait_start > 0.0):
        source_stage = str(host.previous_stage or host.STAGE_MIX)
        if source_stage not in {host.STAGE_MAIN, host.STAGE_MIX}:
            return
        host._final_safe_wait = FinalSafeWaitContinuation(
            source_stage=source_stage, next_stage=host.STAGE_DONE,
            target_voltage_v=float(host._safe_wait_target_v),
            target_current_a=float(host._safe_wait_target_i),
            started_at=float(host._safe_wait_start), session_id=host._v2_trace_session_id,
            completion_reason=str(host._last_transition_reason or "restored_successful_completion"),
            session_generation=float(host._v2_trace_started_at),
        )


def finish_session_restore(
    host: Any, *, output_is_on: Any, is_cv: Any, is_cc: Any,
    session_file: str, success_message: str | None, enrich_restored_session: Any,
    guarded_activation: bool = False,
) -> tuple[bool, str | None]:
    """Sequence accepted ordinary snapshot, continuations, and extensions.

    Guard-bearing documents reach this continuation only after the canonical
    startup owner validates activation. Their bytes are already authoritative,
    so identity enrichment is deliberately skipped.
    """
    snapshot = getattr(host, "_session_restore_snapshot", None)
    document = dict(snapshot.document) if snapshot is not None else {}
    host._restore_desulfation_stage_clock(document)
    restore_recovery_safe_wait(host, document)
    restore_final_safe_wait(host, document)
    host._initialize_shadow_session(started_at=host._v2_trace_started_at)
    if (
        not guarded_activation
        and not bool(getattr(host, "_session_restore_enriched", False))
        and not enrich_restored_session(host, document, session_file=session_file)
    ):
        host.stop(clear_session=False)
        return False, "Restored session identity could not be durably reconciled."
    if host.host_configuration.production_extensions_enabled:
        from application.production_session_extensions import restore_production_session_state
        rejection = restore_production_session_state(
            host, document, output_is_on=output_is_on, is_cv=is_cv, is_cc=is_cc,
        )
        if rejection is not None:
            return False, rejection
    return True, success_message



__all__ = ["finish_session_restore", "restore_final_safe_wait", "restore_recovery_safe_wait"]
