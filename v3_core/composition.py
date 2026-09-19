"""Standalone V3 composition root; construction has no I/O or startup."""

from __future__ import annotations

from dataclasses import dataclass

from .configuration import ConfigurationAuthority, minimal_v3_authority
from .domain import ChargeDomain
from .execution import ExecutionDispatcher
from .safety import SafetyDomain


@dataclass(frozen=True)
class V3Composition:
    configuration: ConfigurationAuthority
    safety: SafetyDomain
    domain: ChargeDomain
    execution: ExecutionDispatcher

    @classmethod
    def standalone(cls) -> "V3Composition":
        safety = SafetyDomain()
        return cls(minimal_v3_authority(), safety, ChargeDomain(safety), ExecutionDispatcher())


__all__ = ["V3Composition"]
