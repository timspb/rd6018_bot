"""Execution record contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from runtime.output.intent import SafeOutputIntent


@dataclass(frozen=True)
class ExecutionRecord:
    timestamp: float
    intent: SafeOutputIntent
    validation_result: Any
    simulated_actions: tuple[str, ...] = ()
    verification_result: Any = None
    errors: tuple[str, ...] = ()
    simulated: bool = True
