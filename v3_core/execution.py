"""V3 execution boundary with a non-physical shadow adapter."""

from __future__ import annotations

from typing import Protocol

from .contracts import ActuatorIntent, ExecutionResult


class V3Adapter(Protocol):
    def submit(self, intent: ActuatorIntent) -> ExecutionResult: ...


class ShadowV3Adapter:
    """Records intent semantics and never performs a physical operation."""

    def submit(self, intent: ActuatorIntent) -> ExecutionResult:
        return ExecutionResult(True, False, intent.operation, "shadow_deferred", intent.trace_id)


class ExecutionDispatcher:
    def __init__(self, adapter: V3Adapter | None = None) -> None:
        self.adapter = adapter or ShadowV3Adapter()

    def dispatch(self, intent: ActuatorIntent) -> ExecutionResult:
        if not isinstance(intent, ActuatorIntent):
            raise TypeError("V3 ActuatorIntent required")
        return self.adapter.submit(intent)


__all__ = ["V3Adapter", "ShadowV3Adapter", "ExecutionDispatcher"]
