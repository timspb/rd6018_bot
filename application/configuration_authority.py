"""Data-only configuration authority contract for Phase 6.2."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Mapping


class ConfigurationSection(str, Enum):
    CHARGE = "charge"
    STRATEGY = "strategy"
    SAFETY = "safety"
    CONTAINMENT = "containment"
    LEASE = "lease"
    EXECUTION = "execution"
    TRANSPORT = "transport"
    UI = "ui"
    PERSISTENCE = "persistence"


Validator = Callable[[Any], bool]


@dataclass(frozen=True)
class ConfigurationParameter:
    """One typed, owned, validated configuration value definition."""

    key: str
    section: ConfigurationSection
    owner: str
    value_type: type
    default: Any
    validator: Validator
    description: str
    source: str = "configuration_authority"
    required: bool = False

    def __post_init__(self) -> None:
        if not self.key.strip() or not self.owner.strip() or not self.description.strip() or not self.source.strip():
            raise ValueError("configuration key, owner, source and description are required")
        if not isinstance(self.section, ConfigurationSection):
            raise TypeError("section must be ConfigurationSection")
        if not isinstance(self.value_type, type) or not callable(self.validator):
            raise TypeError("value_type and validator are required")
        if not isinstance(self.default, self.value_type) or not self.validator(self.default):
            raise ValueError(f"invalid default for configuration parameter: {self.key}")


class ConfigurationAuthority:
    """Registry contract; no file/env/database loading is performed here."""

    def __init__(self, parameters: Mapping[str, ConfigurationParameter] | None = None) -> None:
        self._parameters = dict(parameters or {})
        if len(self._parameters) != len(set(self._parameters)):
            raise ValueError("duplicate configuration keys")
        for key, parameter in self._parameters.items():
            if key != parameter.key:
                raise ValueError("registry key must match parameter key")

    def register(self, parameter: ConfigurationParameter) -> None:
        if parameter.key in self._parameters:
            raise ValueError(f"duplicate configuration key: {parameter.key}")
        self._parameters[parameter.key] = parameter

    def get(self, key: str) -> ConfigurationParameter:
        return self._parameters[key]

    def keys(self) -> tuple[str, ...]:
        return tuple(sorted(self._parameters))

    def sections(self) -> tuple[ConfigurationSection, ...]:
        return tuple(sorted({item.section for item in self._parameters.values()}, key=lambda value: value.value))


__all__ = ["ConfigurationSection", "ConfigurationParameter", "ConfigurationAuthority"]
