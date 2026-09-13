from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from runtime.output.bridge import HardwareCapability, HardwareSnapshot


class IndependentPhysicalConnector(ABC):
    """One independently managed path to the RD6018; read-only in this phase."""

    name: str

    @abstractmethod
    async def discover(self) -> Any: ...

    @abstractmethod
    async def health_check(self) -> dict[str, Any]: ...

    @abstractmethod
    async def get_snapshot(self) -> HardwareSnapshot: ...

    @abstractmethod
    async def get_capabilities(self) -> HardwareCapability: ...

    @abstractmethod
    async def close(self) -> None: ...

    @abstractmethod
    async def disable_output(self) -> None: ...

    @abstractmethod
    async def read_snapshot(self) -> HardwareSnapshot: ...

    @abstractmethod
    async def set_voltage(self, value: float) -> None: ...

    @abstractmethod
    async def set_current(self, value: float) -> None: ...

    @abstractmethod
    async def set_ovp(self, value: float) -> None: ...

    @abstractmethod
    async def set_ocp(self, value: float) -> None: ...

    @abstractmethod
    async def enable_output(self) -> None: ...
