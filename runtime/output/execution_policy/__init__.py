"""Pre-execution checks; this package has no physical executor."""

from .policy import ExecutionPolicy, ExecutionPolicyContext, ExecutionPolicyDecision

__all__ = [
    "ExecutionPolicy", "ExecutionPolicyContext", "ExecutionPolicyDecision",
]
