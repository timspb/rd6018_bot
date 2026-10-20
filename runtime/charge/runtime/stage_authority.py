"""Route one analyzed tick to the existing stage authority owners."""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from runtime.charge.decisions import AuthorityDecision
from runtime.charge.evidence.first_stage import FirstStageAssessment


def is_authoritative_charge_stage(host: Any, stage: str) -> bool:
    """Return whether this modular stage has an admitted authority owner."""
    return (
        host.battery_type != host.PROFILE_CUSTOM
        and (
            stage in {host.STAGE_MAIN, host.STAGE_DESULFATION, host.STAGE_MIX}
            or (
                stage == host.STAGE_SAFE_WAIT
                and (
                    host._recovery_safe_wait is not None
                    or host._final_safe_wait is not None
                    or host._safe_wait_next_stage == host.STAGE_MAIN
                    or host._safe_wait_next_stage == host.STAGE_DONE
                )
            )
        )
    )


def apply_authoritative_stage_tick(
    host: Any,
    *,
    record: Any,
    first_stage: Optional[FirstStageAssessment],
    stage_before: str,
    timestamp_s: float,
    voltage: float,
    current: float,
    temp: float,
    ah: float,
    is_cv: bool,
    is_cc: bool,
    actions: Dict[str, Any],
    output_is_on: Optional[Any] = None,
    decision_veto: Optional[Callable[[AuthorityDecision], Optional[AuthorityDecision]]] = None,
) -> Optional[AuthorityDecision]:
    """Dispatch an admitted stage tick without owning stage policy or hardware."""
    if not is_authoritative_charge_stage(host, stage_before) or host.current_stage != stage_before:
        return None

    if stage_before == host.STAGE_DESULFATION:
        from runtime.charge.runtime.recovery_scaffold import apply_desulfation_authority_tick

        return apply_desulfation_authority_tick(
            host, timestamp_s=timestamp_s, voltage=voltage,
            current=current, temp=temp, ah=ah, actions=actions,
        )

    if (
        stage_before == host.STAGE_SAFE_WAIT
        and (
            host._recovery_safe_wait is not None
            or host._safe_wait_next_stage == host.STAGE_MAIN
        )
    ):
        from runtime.charge.runtime.recovery_scaffold import apply_recovery_safe_wait_authority

        return apply_recovery_safe_wait_authority(
            host, now=timestamp_s, voltage=voltage, current=current,
            temp=temp, ah=ah, actions=actions, output_is_on=output_is_on,
        )

    if (
        stage_before == host.STAGE_SAFE_WAIT
        and (
            host._final_safe_wait is not None
            or host._safe_wait_next_stage == host.STAGE_DONE
        )
    ):
        from runtime.charge.runtime.final_safe_wait_authority import apply_final_safe_wait_authority

        return apply_final_safe_wait_authority(
            host, now=timestamp_s, voltage=voltage, current=current,
            temp=temp, ah=ah, actions=actions, output_is_on=output_is_on,
        )

    if stage_before == host.STAGE_MAIN:
        from runtime.charge.runtime.main_scaffold import apply_main_authority_tick

        return apply_main_authority_tick(
            host, record=record, first_stage=first_stage,
            timestamp_s=timestamp_s, voltage=voltage, current=current,
            temp=temp, ah=ah, is_cv=is_cv, actions=actions,
            decision_veto=decision_veto,
        )

    if stage_before == host.STAGE_MIX:
        from runtime.charge.runtime.mix_scaffold import apply_mix_authority_tick

        return apply_mix_authority_tick(
            host, record=record, timestamp_s=timestamp_s,
            voltage=voltage, current=current, temp=temp, ah=ah,
            is_cv=is_cv, is_cc=is_cc, actions=actions,
        )

    return None


__all__ = ["apply_authoritative_stage_tick", "is_authoritative_charge_stage"]
