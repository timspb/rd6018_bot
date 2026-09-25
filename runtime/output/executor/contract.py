"""Contracts for a future physical executor; no transport dependencies."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from runtime.output.intent import SafeOutputIntent
from runtime.output.execution_policy import ExecutionPolicyDecision


@dataclass(frozen=True)
class ReadbackRequirement:
    fields: tuple[str, ...]
    compare_required: bool = True
    output_must_be_off_before_enable: bool = True

    def __post_init__(self) -> None:
        if not self.fields:
            raise ValueError("readback fields are required")
        if len(set(self.fields)) != len(self.fields):
            raise ValueError("readback fields must be unique")


@dataclass(frozen=True)
class ExecutionLeaseState:
    owner: str | None
    generation: int
    timestamp: float
    status: str

    def __post_init__(self) -> None:
        if self.generation < 0 or not self.status.strip():
            raise ValueError("lease generation/status are invalid")


class PhysicalExecutor(ABC):
    @abstractmethod
    def prepare(self, intent: SafeOutputIntent) -> ExecutionPolicyDecision:
        raise NotImplementedError

    @abstractmethod
    def validate(self, intent: SafeOutputIntent) -> ExecutionPolicyDecision:
        raise NotImplementedError

    @abstractmethod
    def execute(self, intent: SafeOutputIntent):
        raise NotImplementedError

    @abstractmethod
    def verify(self, intent: SafeOutputIntent):
        raise NotImplementedError

    @abstractmethod
    def rollback(self, intent: SafeOutputIntent):
        raise NotImplementedError
