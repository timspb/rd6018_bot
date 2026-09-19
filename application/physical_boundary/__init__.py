"""Transport-agnostic physical execution boundary contracts."""

from .contracts import (
    PhysicalExecutionRequest,
    PhysicalExecutionResult,
    PhysicalExecutionStatus,
    PhysicalFailure,
)
from .mapper import PhysicalExecutionBoundary
from .approval import (
    ApprovalGateResult,
    ApprovalStatus,
    ExecutionApproval,
    ExecutionApprovalGate,
    ExecutionMode,
    REQUIRED_EVIDENCE,
)

__all__ = [
    "PhysicalExecutionRequest", "PhysicalExecutionResult",
    "PhysicalExecutionStatus", "PhysicalFailure", "PhysicalExecutionBoundary",
    "ApprovalGateResult", "ApprovalStatus", "ExecutionApproval",
    "ExecutionApprovalGate", "ExecutionMode", "REQUIRED_EVIDENCE",
]
