"""Immutable configuration for the single managed charge host."""

from __future__ import annotations

from dataclasses import dataclass

@dataclass(frozen=True)
class ManagedChargeHostConfiguration:
    """Construction policy only; owns no session, FSM, or mutable runtime state."""

    production_extensions_enabled: bool = False
    restore_trace_default_intent: str = "recovery"
    restore_trace_default_condition: str = "unknown"


PRODUCTION_CHARGE_HOST_CONFIGURATION = ManagedChargeHostConfiguration(
    production_extensions_enabled=True,
    restore_trace_default_intent="normal",
    restore_trace_default_condition="unknown",
)
