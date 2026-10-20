"""Application use case for executing one controller action batch.

The controller proposes data-only actions. The existing ExecutionPort owns
physical ordering/readback; this use case coordinates only the verified stage
commit and its operator-facing effects.
"""

from __future__ import annotations

import time
from typing import Any, Callable, Mapping, Optional


async def execute_controller_action_batch(
    actions: Mapping[str, Any],
    live: Mapping[str, Any],
    *,
    execution_port: Any,
    controller: Any,
    battery_v: float,
    current: float,
    temp: float,
    ah: float,
    max_stage_current_a: float,
    ocp_offset_a: float,
    idle_safe_ocp_a: float,
    stabilize_delay_s: float,
    recipe_voltage_ceiling_v: float,
    has_ovp: bool,
    has_ocp: bool,
    notify: Callable[..., Any],
    log_event: Callable[..., Any],
    logger: Any,
    now: Callable[[], float] = time.time,
) -> Optional[bool]:
    """Run physical action batch, then commit only its verified transition."""
    execution = await execution_port.execute_controller_actions(
        actions,
        live,
        max_stage_current_a=float(max_stage_current_a),
        ocp_offset_a=float(ocp_offset_a),
        idle_safe_ocp_a=float(idle_safe_ocp_a),
        stabilize_delay_s=float(stabilize_delay_s),
        recipe_voltage_ceiling_v=float(recipe_voltage_ceiling_v),
        has_ovp=bool(has_ovp),
        has_ocp=bool(has_ocp),
    )
    enabled = execution.enabled

    if actions.get("turn_on") and not enabled:
        logger.warning("Controller Output ON request was not verified; stage commit withheld")
    if execution.final_targets_missing:
        logger.error("Final startup protection verification lacks V/I/OVP target")
    elif execution.final_verification_failed:
        logger.error("Final OVP/OCP/V/I verification failed after startup settle; forcing OFF")

    transition = actions.get("verified_enable_transition")
    if isinstance(transition, dict):
        commit = None
        if enabled:
            commit_fn = getattr(controller, "commit_verified_enable_transition", None)
            if callable(commit_fn):
                commit = commit_fn(
                    transition,
                    now=now(),
                    voltage=float(battery_v),
                    current=float(current),
                    ah=float(ah),
                )
        if not enabled or not isinstance(commit, dict):
            if enabled:
                logger.error("Verified Output ON could not be bound to controller transition; forcing OFF")
                await execution_port.request_verified_off()
                enabled = False
            logger.warning("Verified-enable stage transition remains pending in SAFE_WAIT")
        else:
            controller._last_known_output_on = True
            event_name = str(commit.get("log_event") or "").strip()
            if event_name:
                log_event(controller.current_stage, battery_v, current, temp, ah, event_name)
            message = str(commit.get("notify") or "").strip()
            if message:
                notify(message, critical=False)
    return enabled


__all__ = ["execute_controller_action_batch"]
