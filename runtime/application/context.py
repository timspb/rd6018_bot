"""Explicit service references for the V3 orchestrator."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RuntimeContext:
    telemetry_provider: Any
    charge_service: Any
    diagnostics_engine: Any
    safety_engine: Any
    execution_policy: Any
    journal_recorder: Any
    ui_snapshot_builder: Any
