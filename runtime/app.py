"""Minimal V3 RuntimeApp composition boundary."""

from __future__ import annotations

from .dependencies import RuntimeDependencies
from .lifecycle import LifecycleManager, LifecycleState


class RuntimeApp:
    """Passive application container for the staged V3 migration.

    No production object is created here.  In particular, this module has no
    Telegram, HA, controller, RD, lease, or safety integration.
    """

    def __init__(self, dependencies: RuntimeDependencies | None = None) -> None:
        self.dependencies = dependencies or RuntimeDependencies()
        self.lifecycle = LifecycleManager()

    @property
    def state(self) -> LifecycleState:
        return self.lifecycle.state

    async def start(self) -> None:
        await self.lifecycle.start()

    async def stop(self) -> None:
        await self.lifecycle.stop()
