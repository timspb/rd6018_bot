"""Immutable, non-runtime context passed across the preserved V2 START boundary."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping


@dataclass(frozen=True)
class V2StartEventContext:
    """Data-only context; it is not a Telegram event or a runtime handle."""

    trace_id: str
    actor: str
    source: str
    intent_metadata: Mapping[str, Any] = field(default_factory=dict)
    profile: str = ""
    capacity_ah: float = 0.0
    condition: Any = None
    correlation_metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.trace_id.strip():
            raise ValueError("trace_id is required")
        object.__setattr__(self, "intent_metadata", MappingProxyType(dict(self.intent_metadata)))
        object.__setattr__(self, "correlation_metadata", MappingProxyType(dict(self.correlation_metadata)))
