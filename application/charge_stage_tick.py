"""Application routing for one automatic stage scaffold tick."""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional

from runtime.charge.runtime.main_scaffold import run_authoritative_main_scaffold
from runtime.charge.runtime.mix_scaffold import run_authoritative_mix_scaffold
from runtime.charge.runtime.recovery_scaffold import run_authoritative_recovery_scaffold
from runtime.charge.runtime.residual_scaffold import run_authoritative_residual_scaffold
from runtime.charge.runtime.stage_authority import apply_authoritative_stage_tick
from runtime.charge.diagnostics import diagnostic_assessment_snapshot
from runtime.charge.strategy.mix_variables import mix_max_active_seconds
from runtime.charge.strategy.safe_wait_variables import safe_wait_max_seconds


logger = logging.getLogger("rd6018.application.charge_stage_tick")


def apply_charge_stage_authority(host: Any, **kwargs: Any) -> Any:
    """Coordinate stage authority, diagnostic veto, and durable Mix clock projection."""
    stage_before = kwargs["stage_before"]
    timestamp_s = float(kwargs["timestamp_s"])
    diagnostic_update = getattr(host, "_update_live_diagnostic_evidence", None)
    if callable(diagnostic_update):
        diagnostic_update(
            timestamp_s=timestamp_s,
            voltage=float(kwargs["voltage"]),
            current=float(kwargs["current"]),
            temp=float(kwargs["temp"]),
            ah=float(kwargs["ah"]),
        )

    mix_authority = getattr(host, "_mix_active_authority", None)
    projected_mix = stage_before == host.STAGE_MIX and mix_authority is not None
    saved_stage_start = None
    session_id = None
    if projected_mix:
        session_id = host._mix_authority_session_id()
        snapshot = mix_authority._require(session_id)
        saved_stage_start = host.stage_start_time
        host.stage_start_time = timestamp_s - float(snapshot.elapsed_s)

    try:
        decision = apply_authoritative_stage_tick(
            host,
            **{key: value for key, value in kwargs.items() if key != "output_is_on"},
            output_is_on=kwargs.get("output_is_on"),
            decision_veto=getattr(host, "_diagnostic_hv_veto", None),
        )
    finally:
        if projected_mix and host.current_stage == stage_before:
            host.stage_start_time = saved_stage_start

    if (
        projected_mix and decision is not None
        and str(getattr(decision, "reason", "")) == "MIX_TIMEOUT"
    ):
        mix_authority.mark_terminal(session_id, "MIX_TIMEOUT")

    assessment = getattr(host, "battery_fault_assessment", None)
    if assessment is not None:
        kwargs["actions"]["battery_diagnostics"] = diagnostic_assessment_snapshot(assessment)
    return decision


async def run_charge_stage_tick(
    host: Any,
    *,
    stage_before: str,
    voltage: float,
    current: float,
    temp_ext: Optional[float],
    is_cv: bool,
    ah: float,
    output_is_on: Optional[Any],
    manual_off_active: bool,
    is_cc: Optional[bool],
    manual_active: bool,
) -> Dict[str, Any]:
    """Select the existing owner for each admitted stage; never own policy."""
    if host.battery_type == host.PROFILE_CUSTOM:
        if stage_before == host.STAGE_IDLE:
            return {}
        logger.error(
            "Active historical Custom controller state rejected stage=%s; forcing OFF",
            stage_before,
        )
        host.stop(clear_session=True)
        return {
            "turn_off": True,
            "log_event": "HISTORICAL_CUSTOM_RUNTIME_RETIRED",
            "notify": (
                "❌ Исторический Custom-контроллер отключён. "
                "Ручной режим запускается только через Manual."
            ),
        }

    if stage_before in {
        host.STAGE_PREP, host.STAGE_COOLING, host.STAGE_IDLE, host.STAGE_DONE,
    }:
        return await run_authoritative_residual_scaffold(
            host, stage_before=stage_before, voltage=voltage, current=current,
            temp_ext=temp_ext, is_cv=is_cv, ah=ah, output_is_on=output_is_on,
            manual_off_active=manual_off_active, is_cc=is_cc,
            manual_active=manual_active, now_s=time.time(),
        )

    if host.battery_type != host.PROFILE_CUSTOM and stage_before == host.STAGE_MAIN:
        return await run_authoritative_main_scaffold(
            host, voltage=voltage, current=current, temp_ext=temp_ext,
            is_cv=is_cv, ah=ah, output_is_on=output_is_on,
            manual_off_active=manual_off_active, is_cc=is_cc,
            manual_active=manual_active, now_s=time.time(),
        )

    recovery_safe_wait = (
        stage_before == host.STAGE_SAFE_WAIT
        and (
            host._recovery_safe_wait is not None
            or host._safe_wait_next_stage == host.STAGE_MAIN
        )
    )
    if host.battery_type != host.PROFILE_CUSTOM and (
        stage_before == host.STAGE_DESULFATION or recovery_safe_wait
    ):
        return await run_authoritative_recovery_scaffold(
            host, stage_before=stage_before, voltage=voltage, current=current,
            temp_ext=temp_ext, is_cv=is_cv, ah=ah, output_is_on=output_is_on,
            manual_off_active=manual_off_active, is_cc=is_cc,
            manual_active=manual_active, now_s=time.time(),
        )

    final_safe_wait = (
        stage_before == host.STAGE_SAFE_WAIT
        and (
            host._final_safe_wait is not None
            or host._safe_wait_next_stage == host.STAGE_DONE
        )
    )
    if host.battery_type != host.PROFILE_CUSTOM and (
        stage_before == host.STAGE_MIX or final_safe_wait
    ):
        return await run_authoritative_mix_scaffold(
            host, stage_before=stage_before, voltage=voltage, current=current,
            temp_ext=temp_ext, is_cv=is_cv, ah=ah, output_is_on=output_is_on,
            manual_off_active=manual_off_active, is_cc=is_cc,
            manual_active=manual_active,
            report_limit_s=(
                mix_max_active_seconds(host.battery_type)
                if stage_before == host.STAGE_MIX
                else safe_wait_max_seconds()
            ),
            now_s=time.time(),
        )

    reason = f"unsupported_modular_stage:{stage_before}"
    logger.error(
        "Unsupported modular stage; rejecting stage=%s profile=%s",
        stage_before,
        host.battery_type,
    )
    host.stop(clear_session=True)
    return {
        "turn_off": True,
        "log_event": "HISTORICAL_STAGE_RUNTIME_RETIRED",
        "notify": (
            "❌ Этап не принадлежит модульному runtime. "
            "Заряд остановлен до повторной авторизации."
        ),
        "recovery_shadow": {
            "status": "fail_closed",
            "reason": reason,
            "authority": "v2",
        },
    }


__all__ = ["run_charge_stage_tick"]
