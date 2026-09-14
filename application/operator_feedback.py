"""Operator feedback boundary for the preserved V2 START owner."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Protocol

from .v2_start_event_context import V2StartEventContext


class OperatorFeedbackPort(Protocol):
    """Transport-neutral output for operator-facing status feedback."""

    async def publish(self, *, trace_id: str, status: str, message: str, metadata: Mapping[str, Any]) -> None:
        ...

    async def update(self, *, trace_id: str, status: str, message: str, metadata: Mapping[str, Any]) -> None:
        ...


class LegacyFeedbackStatus(str, Enum):
    STARTED = "STARTED"
    DENIED = "DENIED"
    FAILED = "FAILED"
    CONTAINED = "CONTAINED"


@dataclass(frozen=True)
class LegacyOperatorFeedbackBridge:
    """Adapt legacy ``message.answer`` semantics to a feedback port only."""

    port: OperatorFeedbackPort
    context: V2StartEventContext

    async def answer(self, text: str, **kwargs: Any) -> None:
        metadata = dict(self.context.correlation_metadata)
        metadata.update({"source": self.context.source, "actor": self.context.actor})
        if kwargs:
            metadata["message_options"] = dict(kwargs)
        await self.port.publish(
            trace_id=self.context.trace_id,
            status=LegacyFeedbackStatus.FAILED.value,
            message=str(text),
            metadata=metadata,
        )

    async def update(self, text: str, **kwargs: Any) -> None:
        """Normalize legacy message edits through the same feedback port."""
        await self.answer(text, **kwargs)

    async def publish_status(self, status: LegacyFeedbackStatus | str, message: str) -> None:
        await self.port.publish(
            trace_id=self.context.trace_id,
            status=status.value if isinstance(status, LegacyFeedbackStatus) else str(status),
            message=str(message),
            metadata=dict(self.context.correlation_metadata),
        )


def build_legacy_feedback_bridge(
    context: V2StartEventContext,
    port: OperatorFeedbackPort,
) -> LegacyOperatorFeedbackBridge:
    """Create the bridge without adding transport objects to V3 context."""
    return LegacyOperatorFeedbackBridge(port=port, context=context)
