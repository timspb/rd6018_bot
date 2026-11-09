"""D137's narrow, read-only final SAFE_WAIT continuation check.

This validates the existing canonical continuation; it does not own charge
transitions, create an admission token, or enable a physical output.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from runtime.charge.strategy.final_safe_wait import (
    FinalSafeWaitContinuation,
    validate_final_continuation,
)

FINAL_WAIT_STAGE = "Безопасное ожидание"
FINAL_DONE_STAGE = "Done"
MAIN_STAGE = "Main Charge"
MIX_STAGE = "Mix Mode"


def valid_guarded_final_wait(document: Mapping[str, Any]) -> bool:
    """Require an exact session-bound MIX→SAFE_WAIT→Done continuation."""
    raw = document.get("v2_final_safe_wait")
    history = document.get("stage_history")
    if (document.get("stage") != FINAL_WAIT_STAGE
            or type(raw) is not dict
            or raw.get("version") != 2
            or type(history) is not list
            or document.get("safe_wait_next_stage") != FINAL_DONE_STAGE
            or document.get("completion_kind") is not None
            or document.get("output_intent") is not None
            or document.get("terminal_session_id") is not None
            or not any(
                type(edge) is dict
                and edge.get("from") == MAIN_STAGE and edge.get("to") == MIX_STAGE
                for edge in history
            )
            or not any(
                type(edge) is dict
                and edge.get("from") == MIX_STAGE and edge.get("to") == FINAL_WAIT_STAGE
                for edge in history
            )):
        return False

    try:
        candidate = FinalSafeWaitContinuation(
            source_stage=raw["source_stage"],
            next_stage=raw["next_stage"],
            target_voltage_v=float(raw["target_voltage_v"]),
            target_current_a=float(raw["target_current_a"]),
            started_at=float(raw["started_at"]),
            session_id=raw["session_id"],
            completion_reason=raw["completion_reason"],
            session_generation=float(raw["session_generation"]),
        )
        return (
            validate_final_continuation(
                candidate,
                session_id=document.get("v2_trace_session_id"),
                session_generation=document.get("v2_trace_started_at"),
                expected_next_stage=FINAL_DONE_STAGE,
                allowed_source_stages={MIX_STAGE},
            )
            and float(document["safe_wait_target_v"]) == candidate.target_voltage_v
            and float(document["safe_wait_target_i"]) == candidate.target_current_a
            and float(document["safe_wait_start"]) == candidate.started_at
        )
    except (TypeError, KeyError, ValueError, OverflowError, AttributeError):
        return False
