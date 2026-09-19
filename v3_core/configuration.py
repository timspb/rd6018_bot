"""Standalone V3 configuration authority contract."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping


@dataclass(frozen=True)
class ConfigurationParameter:
    name: str
    section: str
    value_type: type
    default: Any
    validator: Callable[[Any], bool]
    provenance: str


class ConfigurationAuthority:
    def __init__(self, parameters: Mapping[str, ConfigurationParameter]) -> None:
        if not parameters or len(parameters) != len(set(parameters)):
            raise ValueError("configuration registry must be non-empty and unique")
        for name, parameter in parameters.items():
            if name != parameter.name or not parameter.provenance.strip():
                raise ValueError("configuration identity/provenance is invalid")
            if not isinstance(parameter.default, parameter.value_type) or not parameter.validator(parameter.default):
                raise ValueError(f"invalid default: {name}")
        self._parameters = dict(parameters)

    def resolve(self, values: Mapping[str, Any]) -> Mapping[str, Any]:
        unknown = set(values) - set(self._parameters)
        if unknown:
            raise ValueError("unknown configuration: " + ", ".join(sorted(unknown)))
        resolved = {}
        for name, parameter in self._parameters.items():
            value = values.get(name, parameter.default)
            if not isinstance(value, parameter.value_type) or not parameter.validator(value):
                raise ValueError(f"invalid configuration: {name}")
            resolved[name] = value
        return resolved

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._parameters))


def minimal_v3_authority() -> ConfigurationAuthority:
    """Schema only; production values remain supplied by a future migration."""
    positive = lambda value: value > 0
    return ConfigurationAuthority({
        "execution.command_timeout_s": ConfigurationParameter("execution.command_timeout_s", "execution", float, 5.0, positive, "V3 physical adapter bench contract"),
        "execution.readback_timeout_s": ConfigurationParameter("execution.readback_timeout_s", "execution", float, 15.0, positive, "V3 execution contract"),
        "execution.readback_tolerance": ConfigurationParameter("execution.readback_tolerance", "execution", float, 0.05, positive, "V3 physical adapter bench contract"),
        "safety.max_voltage_v": ConfigurationParameter("safety.max_voltage_v", "safety", float, 18.0, positive, "V3 safety contract"),
        "safety.max_current_a": ConfigurationParameter("safety.max_current_a", "safety", float, 18.0, positive, "V3 safety contract"),
    })


__all__ = ["ConfigurationParameter", "ConfigurationAuthority", "minimal_v3_authority"]
