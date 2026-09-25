"""Lifecycle boundary for the isolated V3 runtime skeleton."""

from __future__ import annotations

from enum import Enum


class LifecycleState(str, Enum):
    CREATED = "created"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"


class LifecycleManager:
    """Owns only lifecycle state in Phase 3A.

    Startup and shutdown are deliberately no-op sequences.  Integrations and
    background tasks are not wired until a later migration phase.
    """

    def __init__(self) -> None:
        self.state = LifecycleState.CREATED

    async def start(self) -> None:
        if self.state is LifecycleState.RUNNING:
            return
        if self.state not in {LifecycleState.CREATED, LifecycleState.STOPPED}:
            raise RuntimeError(f"cannot start from lifecycle state {self.state.value}")
        self.state = LifecycleState.STARTING
        self.state = LifecycleState.RUNNING

    async def stop(self) -> None:
        if self.state is LifecycleState.STOPPED:
            return
        if self.state is not LifecycleState.RUNNING:
            raise RuntimeError(f"cannot stop from lifecycle state {self.state.value}")
        self.state = LifecycleState.STOPPING
        self.state = LifecycleState.STOPPED
