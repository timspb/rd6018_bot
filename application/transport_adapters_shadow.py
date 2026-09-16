"""Shadow RD execution adapters with no transport or physical side effects."""

from __future__ import annotations

from datetime import datetime, timezone

from .actuator_intent import ActuatorIntent
from .execution_boundary import ExecutionRequest, ExecutionResult
from .containment_result import ContainmentVerificationState
from .rd_transport import ControlProvider, RDReadback, RDTelemetry, TelemetryProvider


class _ShadowExecutionAdapter(TelemetryProvider, ControlProvider):
    """Common semantic implementation; subclasses only identify the source."""

    source_name = "shadow"

    def dispatch(self, request: ExecutionRequest) -> ExecutionResult:
        if not isinstance(request, ExecutionRequest):
            return ExecutionResult(False, True, False, ContainmentVerificationState.UNKNOWN, "invalid_execution_request")
        operation = str(request.correlation.get("operation", ""))
        if not operation and request.intent is not None:
            operation = request.intent.requested_operation.value
        if operation not in {
            "read_telemetry", "read_output_state", "read_readback",
            "set_voltage", "set_current", "output_on", "output_off",
        }:
            return ExecutionResult(False, True, False, ContainmentVerificationState.UNKNOWN, "unsupported_shadow_operation")
        return ExecutionResult(
            True,
            False,
            True,
            ContainmentVerificationState.NOT_REQUESTED,
            f"{self.source_name}:{operation}:shadow_deferred",
            request,
        )

    async def read_telemetry(self) -> RDTelemetry:
        return RDTelemetry(None, None, None, None, datetime.now(timezone.utc))

    async def read_output_state(self) -> bool | None:
        return None

    async def read_readback(self) -> RDReadback:
        return RDReadback(None, None, None, datetime.now(timezone.utc))

    async def set_voltage(self, value: float) -> None:
        return None

    async def set_current(self, value: float) -> None:
        return None

    async def output_on(self) -> None:
        return None

    async def output_off(self) -> None:
        return None


class HAExecutionAdapter(_ShadowExecutionAdapter):
    """HA-shaped shadow adapter; it creates no HA client or request."""

    source_name = "ha-shadow"


class ESPDirectExecutionAdapter(_ShadowExecutionAdapter):
    """ESP-direct-shaped shadow adapter; it creates no ESP client or request."""

    source_name = "esp-direct-shadow"


__all__ = ["HAExecutionAdapter", "ESPDirectExecutionAdapter"]
