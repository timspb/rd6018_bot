"""Minimal V3 RuntimeApp composition boundary."""

from __future__ import annotations

from .dependencies import RuntimeDependencies
from .charge import ChargeService, DecisionValidationResult, ProgramRegistry
from .charge.contracts import ChargeDecisionCase
from .lifecycle import LifecycleManager, LifecycleState


class RuntimeApp:
    """Passive application container for the staged V3 migration.

    No production object is created here.  Infrastructure is supplied through
    ``RuntimeDependencies``; this module has no Telegram, controller, RD,
    lease, output, or safety integration.
    """

    def __init__(self, dependencies: RuntimeDependencies | None = None) -> None:
        self.dependencies = dependencies or RuntimeDependencies()
        self.lifecycle = LifecycleManager()
        registry = self.dependencies.program_registry or ProgramRegistry.with_defaults()
        self.charge_service = ChargeService(registry, self.dependencies.clock)

    @property
    def state(self) -> LifecycleState:
        return self.lifecycle.state

    async def start(self) -> None:
        await self.lifecycle.start()

    async def stop(self) -> None:
        await self.lifecycle.stop()

    def shadow_tick(self, case: ChargeDecisionCase, program_config: object):
        """Evaluate a native case and compare it with its expected intent."""
        snapshot = self.charge_service.evaluate(
            case.battery_profile,
            case.input_config["program"],
            program_config,
            case.charge_state,
            case.measurements,
        )
        return snapshot, DecisionValidationResult.compare(case, snapshot.intent)
