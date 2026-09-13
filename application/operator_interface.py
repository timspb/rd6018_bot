"""Stable application boundary for operator-facing clients."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable, Iterable

from runtime.ui.commands.models import CommandResult, CommandStatus, UserCommand
from runtime.ui.models import DiagnosticsView

from .intents import OperatorIntent
from .operator_snapshot import OperatorSnapshot


class OperatorInterface(ABC):
    @abstractmethod
    async def get_operator_snapshot(self) -> OperatorSnapshot: ...

    @abstractmethod
    async def get_diagnostics(self) -> DiagnosticsView: ...

    @abstractmethod
    async def get_journal(self, limit: int = 20) -> tuple[str, ...]: ...

    @abstractmethod
    async def submit_intent(self, intent: OperatorIntent | UserCommand) -> CommandResult: ...


class CallbackOperatorInterface(OperatorInterface):
    """Small composition adapter; providers are injected by the composition root."""

    def __init__(
        self,
        snapshot_provider: Callable[[], OperatorSnapshot],
        diagnostics_provider: Callable[[], DiagnosticsView],
        journal_provider: Callable[[int], Iterable[str]],
        intent_handler: Callable[[OperatorIntent | UserCommand], CommandResult] | None = None,
    ) -> None:
        self._snapshot_provider = snapshot_provider
        self._diagnostics_provider = diagnostics_provider
        self._journal_provider = journal_provider
        self._intent_handler = intent_handler

    async def get_operator_snapshot(self) -> OperatorSnapshot:
        return self._snapshot_provider()

    async def get_diagnostics(self) -> DiagnosticsView:
        return self._diagnostics_provider()

    async def get_journal(self, limit: int = 20) -> tuple[str, ...]:
        if limit < 0:
            raise ValueError("limit must not be negative")
        return tuple(self._journal_provider(limit))

    async def submit_intent(self, intent: OperatorIntent | UserCommand) -> CommandResult:
        if self._intent_handler is None:
            return CommandResult(CommandStatus.REJECTED, "operator_intent_not_wired")
        return self._intent_handler(intent)
