"""Single-owner lifecycle for the V3 application service."""

from __future__ import annotations

from enum import Enum


class RuntimeLifecycleState(str, Enum):
    CREATED = "created"
    INITIALIZED = "initialized"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"


class RuntimeLifecycle:
    def __init__(self) -> None:
        self.state = RuntimeLifecycleState.CREATED

    def initialize(self) -> None:
        if self.state is not RuntimeLifecycleState.CREATED:
            raise RuntimeError("runtime can only initialize from created")
        self.state = RuntimeLifecycleState.INITIALIZED

    def start(self) -> None:
        if self.state is RuntimeLifecycleState.CREATED:
            self.initialize()
        if self.state is RuntimeLifecycleState.RUNNING:
            return
        if self.state not in {RuntimeLifecycleState.INITIALIZED, RuntimeLifecycleState.STOPPED}:
            raise RuntimeError(f"runtime cannot start from {self.state.value}")
        self.state = RuntimeLifecycleState.RUNNING

    def stop(self) -> None:
        if self.state is RuntimeLifecycleState.STOPPED:
            return
        if self.state not in {RuntimeLifecycleState.RUNNING, RuntimeLifecycleState.INITIALIZED}:
            raise RuntimeError(f"runtime cannot stop from {self.state.value}")
        self.state = RuntimeLifecycleState.STOPPING
        self.state = RuntimeLifecycleState.STOPPED
