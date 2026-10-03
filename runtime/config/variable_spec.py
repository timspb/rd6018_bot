"""Metadata contract for module-owned configurable values.

This module defines only the metadata shape. It must never become a central bag
of charge/safety/UI values; those live in each owning module's variables.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from numbers import Real
from typing import Generic, TypeVar


T = TypeVar("T")


class OverridePolicy(str, Enum):
    """How a value may be changed."""

    CODE_DEFAULT_ONLY = "code_default_only"
    CONFIG_FILE = "config_file"
    ENVIRONMENT = "environment"
    DEPLOYMENT_ONLY = "deployment_only"


class ChangeEffect(str, Enum):
    """When a changed value may take effect."""

    RUNTIME_SAFE = "runtime_safe"
    RESTART_REQUIRED = "restart_required"
    DEPLOY_REQUIRED = "deploy_required"


@dataclass(frozen=True)
class VariableSpec(Generic[T]):
    """Self-describing module-owned configuration declaration."""

    key: str
    default: T
    value_type: type
    unit: str
    description: str
    owner: str
    provenance: str
    override_policy: OverridePolicy
    change_effect: ChangeEffect
    minimum: Real | None = None
    maximum: Real | None = None
    allowed_values: tuple[T, ...] = ()

    def __post_init__(self) -> None:
        required = {
            "key": self.key,
            "unit": self.unit,
            "description": self.description,
            "owner": self.owner,
            "provenance": self.provenance,
        }
        missing = [name for name, value in required.items() if not str(value).strip()]
        if missing:
            raise ValueError(f"variable metadata is incomplete: {', '.join(missing)}")
        if not isinstance(self.default, self.value_type):
            raise TypeError(
                f"{self.key}: default {self.default!r} is not {self.value_type.__name__}"
            )
        if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
            raise ValueError(f"{self.key}: minimum exceeds maximum")
        if isinstance(self.default, Real) and not isinstance(self.default, bool):
            if self.minimum is not None and self.default < self.minimum:
                raise ValueError(f"{self.key}: default is below minimum")
            if self.maximum is not None and self.default > self.maximum:
                raise ValueError(f"{self.key}: default is above maximum")
        if self.allowed_values and self.default not in self.allowed_values:
            raise ValueError(f"{self.key}: default is not in allowed_values")


__all__ = ["ChangeEffect", "OverridePolicy", "VariableSpec"]
