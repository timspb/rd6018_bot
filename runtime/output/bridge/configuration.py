"""Explicit configuration for the opt-in physical bridge."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PhysicalExecutionConfig:
    enabled: bool = False
    require_manual_arm: bool = True
    allow_runtime_activation: bool = False

    def __post_init__(self) -> None:
        if self.allow_runtime_activation:
            raise ValueError("runtime activation is forbidden for the manual bench bridge")

