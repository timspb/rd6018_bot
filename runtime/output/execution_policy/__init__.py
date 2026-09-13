"""Pre-execution checks; this package has no physical executor."""

from .policy import ExecutionPolicy, ExecutionPolicyContext, ExecutionPolicyDecision
from .parity import ExecutionParityResult, LegacyExecutionPolicyAdapter

__all__ = [
    "ExecutionPolicy", "ExecutionPolicyContext", "ExecutionPolicyDecision",
    "ExecutionParityResult", "LegacyExecutionPolicyAdapter",
]
