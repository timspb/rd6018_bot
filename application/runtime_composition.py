"""V3 runtime shell for shadow-only composition.

The shell owns lifecycle and health reporting only.  It creates the existing
shadow graph, accepts optional observation workers, and never owns control or
physical execution.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import Enum
from typing import Awaitable, Callable, Iterable, Any

from .charge_orchestration import TelemetrySnapshot
from .diagnostics_domain import DiagnosticCategory, DiagnosticSeverity, TraceCorrelation
from .shadow_composition import ApplicationComposition


class RuntimeLifecycle(str, Enum):
    NEW = "new"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"


@dataclass(frozen=True)
class RuntimeHealth:
    state: RuntimeLifecycle
    dependencies_ready: bool
    workers_running: int
    shadow_only: bool
    physical_execution_enabled: bool
    diagnostics_ready: bool
    shadow_observer_connected: bool
    last_error: str | None = None


Worker = Callable[["V3RuntimeComposition"], Awaitable[None] | None]


class V3RuntimeComposition:
    """Lifecycle shell around the V3 shadow composition graph."""

    def __init__(
        self,
        *,
        composition: ApplicationComposition | None = None,
        shadow_observer: object | None = None,
        workers: Iterable[Worker] = (),
    ) -> None:
        self.composition = composition
        self.shadow_observer = shadow_observer
        self._worker_factories = tuple(workers)
        self._tasks: list[asyncio.Task[Any]] = []
        self._state = RuntimeLifecycle.NEW
        self._last_error: str | None = None

    @property
    def state(self) -> RuntimeLifecycle:
        return self._state

    async def start(self) -> RuntimeHealth:
        if self._state is RuntimeLifecycle.RUNNING:
            return self.health()
        if self._state in {RuntimeLifecycle.STARTING, RuntimeLifecycle.STOPPING}:
            raise RuntimeError(f"runtime lifecycle is {self._state.value}")
        self._state = RuntimeLifecycle.STARTING
        self._last_error = None
        try:
            if self.composition is None:
                self.composition = ApplicationComposition.shadow()
            self._validate_dependencies()
            self._state = RuntimeLifecycle.RUNNING
            self._emit("runtime_started", {"workers": len(self._worker_factories)})
            for worker in self._worker_factories:
                result = worker(self)
                if asyncio.iscoroutine(result) or isinstance(result, asyncio.Future):
                    self._tasks.append(asyncio.create_task(result))
            return self.health()
        except Exception as exc:
            self._last_error = f"{type(exc).__name__}: {exc}"
            self._state = RuntimeLifecycle.FAILED
            self._emit("runtime_start_failed", {"error": self._last_error}, severity=DiagnosticSeverity.ERROR)
            await self._cancel_workers()
            raise

    async def shutdown(self) -> RuntimeHealth:
        if self._state in {RuntimeLifecycle.NEW, RuntimeLifecycle.STOPPED}:
            self._state = RuntimeLifecycle.STOPPED
            return self.health()
        self._state = RuntimeLifecycle.STOPPING
        await self._cancel_workers()
        self._emit("runtime_stopped", {})
        self._state = RuntimeLifecycle.STOPPED
        return self.health()

    async def process_shadow(self, command: str, *, user: str, trace_id: str | None = None):
        """Process one operator command through domain shadow only."""
        if self._state is not RuntimeLifecycle.RUNNING or self.composition is None:
            raise RuntimeError("V3 runtime is not running")
        ui_result = self.composition.ui.parse(command, user=user, trace_id=trace_id)
        if not ui_result.accepted or ui_result.intent is None:
            return ui_result
        esp = await self.composition.telemetry.esp_direct.read()
        ha = await self.composition.telemetry.ha.read()
        selected = self.composition.telemetry.arbitrator.select(esp_direct=esp, ha=ha)
        telemetry = TelemetrySnapshot(
            selected.voltage,
            selected.current,
            selected.temperature,
            selected.output_state,
            selected.received_at,
        )
        decision = self.composition.application.handle(ui_result.intent, telemetry)
        self._emit("shadow_processed", {"trace_id": ui_result.trace_id, "accepted": decision.accepted})
        return decision

    def health(self) -> RuntimeHealth:
        return RuntimeHealth(
            state=self._state,
            dependencies_ready=self.composition is not None,
            workers_running=sum(not task.done() for task in self._tasks),
            shadow_only=True,
            physical_execution_enabled=False,
            diagnostics_ready=self.composition is not None and self.composition.diagnostics is not None,
            shadow_observer_connected=self.shadow_observer is not None,
            last_error=self._last_error,
        )

    def _validate_dependencies(self) -> None:
        if self.composition is None:
            raise RuntimeError("composition is not initialized")
        required = ("ui", "application", "domain", "configuration", "telemetry", "execution", "transport", "persistence", "diagnostics")
        missing = tuple(name for name in required if getattr(self.composition, name, None) is None)
        if missing:
            raise RuntimeError("missing composition dependencies: " + ", ".join(missing))

    async def _cancel_workers(self) -> None:
        tasks, self._tasks = self._tasks, []
        for task in tasks:
            if not task.done():
                task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def _emit(self, event_type: str, payload: dict[str, Any], *, severity: DiagnosticSeverity = DiagnosticSeverity.INFO) -> None:
        if self.composition is None:
            return
        self.composition.diagnostics.event(
            category=DiagnosticCategory.INFRASTRUCTURE,
            event_type=event_type,
            severity=severity,
            correlation=TraceCorrelation("v3-runtime", event_type),
            source="v3-runtime-composition",
            payload=payload,
        )


__all__ = ["RuntimeLifecycle", "RuntimeHealth", "V3RuntimeComposition"]
