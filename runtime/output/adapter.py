"""Output adapter boundary without a physical implementation."""

from __future__ import annotations

from abc import ABC, abstractmethod

from .decision import OutputDecision
from .intent import SafeOutputIntent


class OutputAdapter(ABC):
    """Consumes only safety-approved output intents."""

    @abstractmethod
    async def apply(self, intent: SafeOutputIntent) -> OutputDecision:
        raise NotImplementedError


class MockOutputAdapter(OutputAdapter):
    """Test-only adapter; records values and performs no I/O."""

    def __init__(self) -> None:
        self.applied: list[SafeOutputIntent] = []

    async def apply(self, intent: SafeOutputIntent) -> OutputDecision:
        if not isinstance(intent, SafeOutputIntent):
            raise TypeError("OutputAdapter accepts SafeOutputIntent only")
        self.applied.append(intent)
        return OutputDecision(True, "MOCK_ACCEPTED")
