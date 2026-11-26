"""Post-tick charge-cycle journal effects.

This owner preserves the established production journal order and sinks. It
does not own charge decisions or a clock; callers pass the existing observer
timestamp and checkpoint value.
"""
from __future__ import annotations

from typing import Any, Callable, Mapping

from runtime.charge.evidence.mix_progress_journal import dispatch_mix_progress_journal


_event_log_last_at: dict[str, float] = {}


def _should_skip_noisy_log_event(stage: str, event: str, now_s: float) -> bool:
    """Retain the existing ten-minute suppression for unavailable events."""
    if (event or "").strip() != "EMERGENCY_UNAVAILABLE":
        return False
    key = f"{stage}:{event.strip()}"
    last = _event_log_last_at.get(key, 0.0)
    if now_s - last < 600:
        return True
    _event_log_last_at[key] = now_s
    return False


def record_charge_cycle_journal(
    *,
    previous_stage: str,
    current_stage: str,
    actions: Mapping[str, Any],
    charge_active: bool,
    last_checkpoint_time: float,
    now_s: float,
    voltage_v: float,
    current_a: float,
    temperature_c: float,
    ah: float,
    live: Mapping[str, Any],
    signal: Mapping[str, Any] | None,
    session_id: str | None,
    hold_started_at: float | None,
    mix_stage: str,
    max_age_s: float,
    log_event: Callable[..., Any],
    log_stage_end: Callable[..., Any],
    log_checkpoint: Callable[..., Any],
    warn: Callable[..., Any],
) -> float:
    """Dispatch the existing post-tick journal cluster and return checkpoint time."""
    if previous_stage != current_stage:
        log_event(
            current_stage, voltage_v, current_a, temperature_c, ah,
            f"STAGE_CHANGE | {previous_stage} -> {current_stage}",
        )

    end = actions.get("log_event_end")
    if end:
        log_stage_end(
            end["stage"], end["v"], end["i"], end["t"], end["ah"],
            end["time_sec"], end["ah_on_stage"], end["trigger"],
        )
    if actions.get("log_event_sub"):
        log_event(
            end["stage"] if end else current_stage,
            voltage_v, current_a, temperature_c, ah, actions["log_event_sub"],
        )
    if actions.get("log_event"):
        event_name = str(actions["log_event"])
        if not _should_skip_noisy_log_event(current_stage, event_name, now_s):
            log_event(current_stage, voltage_v, current_a, temperature_c, ah, event_name)

    if charge_active and now_s - last_checkpoint_time >= 600:
        log_checkpoint(current_stage, voltage_v, current_a, temperature_c, ah)
        if current_stage == mix_stage:
            dispatch_mix_progress_journal(
                live,
                signal,
                stage=mix_stage,
                session_id=session_id,
                now_s=now_s,
                max_age_s=max_age_s,
                hold_started_at=hold_started_at,
                voltage_v=voltage_v,
                current_a=current_a,
                temperature_c=temperature_c,
                ah=ah,
                journal=log_event,
                warn=warn,
            )
        last_checkpoint_time = now_s
    return last_checkpoint_time
