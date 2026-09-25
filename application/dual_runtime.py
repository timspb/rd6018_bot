"""Contract-only coexistence coordinator for V2 and V3 runtimes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .runtime_composition import RuntimeHealth, RuntimeLifecycle, V3RuntimeComposition


@dataclass(frozen=True)
class RuntimeHealthSnapshot:
    runtime: str
    alive: bool
    healthy: bool
    execution_owner: bool
    shadow_healthy: bool
    no_execution_authority: bool
    lifecycle: str
    persistence_namespace: str
    diagnostics_namespace: str


@dataclass(frozen=True)
class DualRuntimeHealth:
    v2: RuntimeHealthSnapshot
    v3: RuntimeHealthSnapshot
    duplicate_ownership: tuple[str, ...]
    isolated: bool


class DualRuntimeCoordinator:
    """Start/stop only the V3 shell while observing an external V2 owner."""

    def __init__(
        self,
        v3: V3RuntimeComposition,
        v2_health: Callable[[], RuntimeHealthSnapshot],
        *,
        v3_persistence_namespace: str = "v3-shadow",
        v3_diagnostics_namespace: str = "v3-shadow-diagnostics",
    ) -> None:
        self.v3 = v3
        self._v2_health = v2_health
        self._v3_persistence_namespace = v3_persistence_namespace
        self._v3_diagnostics_namespace = v3_diagnostics_namespace
        self._validate_namespaces()

    async def start(self) -> DualRuntimeHealth:
        """Require healthy V2 first, then start only the V3 shadow shell."""
        before = self._v2_health()
        self._validate_v2(before)
        await self.v3.start()
        return self.health()

    async def shutdown(self) -> DualRuntimeHealth:
        """Stop only V3; V2 lifecycle remains owned by its production root."""
        await self.v3.shutdown()
        return self.health()

    def health(self) -> DualRuntimeHealth:
        v2 = self._v2_health()
        v3_health = self.v3.health()
        v3 = self._v3_snapshot(v3_health)
        conflicts = self._ownership_conflicts(v2, v3)
        return DualRuntimeHealth(v2, v3, conflicts, not conflicts)

    def _validate_v2(self, snapshot: RuntimeHealthSnapshot) -> None:
        if not snapshot.alive or not snapshot.healthy:
            raise RuntimeError("V2 must be alive and healthy before V3 shadow startup")
        if not snapshot.execution_owner or snapshot.no_execution_authority:
            raise RuntimeError("V2 execution ownership is not positively established")

    def _validate_namespaces(self) -> None:
        if not self._v3_persistence_namespace or not self._v3_diagnostics_namespace:
            raise ValueError("V3 namespaces are required")
        if self._v3_persistence_namespace == self._v3_diagnostics_namespace:
            raise ValueError("V3 persistence and diagnostics namespaces must differ")

    def _v3_snapshot(self, health: RuntimeHealth) -> RuntimeHealthSnapshot:
        running = health.state is RuntimeLifecycle.RUNNING
        return RuntimeHealthSnapshot(
            runtime="V3",
            alive=health.state not in {RuntimeLifecycle.NEW, RuntimeLifecycle.STOPPED},
            healthy=running and health.dependencies_ready and health.diagnostics_ready,
            execution_owner=False,
            shadow_healthy=running and health.shadow_only,
            no_execution_authority=True,
            lifecycle=health.state.value,
            persistence_namespace=self._v3_persistence_namespace,
            diagnostics_namespace=self._v3_diagnostics_namespace,
        )

    @staticmethod
    def _ownership_conflicts(v2: RuntimeHealthSnapshot, v3: RuntimeHealthSnapshot) -> tuple[str, ...]:
        conflicts: list[str] = []
        if v3.execution_owner:
            conflicts.append("duplicate_execution_owner")
        if not v3.no_execution_authority:
            conflicts.append("v3_execution_authority_present")
        if v2.persistence_namespace == v3.persistence_namespace:
            conflicts.append("duplicate_persistence_namespace")
        if v2.diagnostics_namespace == v3.diagnostics_namespace:
            conflicts.append("duplicate_diagnostics_namespace")
        return tuple(conflicts)


__all__ = ["RuntimeHealthSnapshot", "DualRuntimeHealth", "DualRuntimeCoordinator"]
