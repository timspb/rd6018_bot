"""Validated, non-runtime configuration model for Phase 6.4.

The adapters in this module only read legacy sources.  They are deliberately
not imported by the production bootstrap and never write configuration,
hardware, HA, ESPHome, persistence, or UI state.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import yaml

from .configuration_authority import (
    ConfigurationAuthority,
    ConfigurationParameter,
    ConfigurationSection,
)


class ConfigurationModelError(ValueError):
    """Base error for source, schema, and validation failures."""


class ConfigurationConflictError(ConfigurationModelError):
    """Raised when sources provide different values for one canonical key."""


class ConfigurationMissingError(ConfigurationModelError):
    """Raised when a required value has no source and no permitted default."""


class ConfigurationSource(str, Enum):
    YAML = "yaml"
    PYTHON = "python"
    ENV = "env"
    DEFAULT = "default"


@dataclass(frozen=True)
class ConfigurationValue:
    key: str
    value: Any
    source: str


class SourceMapping(dict[str, Any]):
    """Mapping carrying provenance without changing the source payload."""

    def __init__(self, source_name: str, values: Mapping[str, Any]) -> None:
        super().__init__(values)
        self.source_name = source_name


@dataclass(frozen=True)
class ConfigurationSectionConfig:
    section: ConfigurationSection
    values: Mapping[str, Any]

    def get(self, key: str, default: Any = None) -> Any:
        return self.values.get(key, default)


class ChargeConfig(ConfigurationSectionConfig):
    pass


class StrategyConfig(ConfigurationSectionConfig):
    pass


class SafetyConfig(ConfigurationSectionConfig):
    pass


class ContainmentConfig(ConfigurationSectionConfig):
    pass


class LeaseConfig(ConfigurationSectionConfig):
    pass


class ExecutionConfig(ConfigurationSectionConfig):
    pass


class TransportConfig(ConfigurationSectionConfig):
    pass


class UIConfig(ConfigurationSectionConfig):
    pass


class PersistenceConfig(ConfigurationSectionConfig):
    pass


_SECTION_TYPES = {
    ConfigurationSection.CHARGE: ChargeConfig,
    ConfigurationSection.STRATEGY: StrategyConfig,
    ConfigurationSection.SAFETY: SafetyConfig,
    ConfigurationSection.CONTAINMENT: ContainmentConfig,
    ConfigurationSection.LEASE: LeaseConfig,
    ConfigurationSection.EXECUTION: ExecutionConfig,
    ConfigurationSection.TRANSPORT: TransportConfig,
    ConfigurationSection.UI: UIConfig,
    ConfigurationSection.PERSISTENCE: PersistenceConfig,
}


class ConfigurationModel:
    """Immutable-by-convention resolved model with all nine authority sections."""

    def __init__(self, authority: ConfigurationAuthority, values: Mapping[str, ConfigurationValue]) -> None:
        self.authority = authority
        self._values = dict(values)
        grouped: dict[ConfigurationSection, dict[str, Any]] = {
            section: {} for section in ConfigurationSection
        }
        for key, resolved in self._values.items():
            parameter = authority.get(key)
            grouped[parameter.section][key] = resolved.value
        for section, config_type in _SECTION_TYPES.items():
            setattr(self, section.value, config_type(section, dict(grouped[section])))

    def get(self, key: str) -> Any:
        try:
            return self._values[key].value
        except KeyError as exc:
            raise KeyError(f"unknown configuration key: {key}") from exc

    def value(self, key: str) -> ConfigurationValue:
        return self._values[key]

    def keys(self) -> tuple[str, ...]:
        return tuple(sorted(self._values))

    @classmethod
    def resolve(
        cls,
        authority: ConfigurationAuthority,
        sources: Iterable[Mapping[str, Any]],
    ) -> "ConfigurationModel":
        collected: dict[str, list[tuple[str, Any]]] = {key: [] for key in authority.keys()}
        for source in sources:
            for key, raw_value in source.items():
                if key in collected:
                    collected[key].append((getattr(source, "source_name", "legacy"), raw_value))

        resolved: dict[str, ConfigurationValue] = {}
        for key in authority.keys():
            parameter = authority.get(key)
            candidates = collected[key]
            typed = [(name, _coerce(value, parameter.value_type)) for name, value in candidates]
            invalid = [name for name, value in typed if not parameter.validator(value)]
            if invalid:
                raise ConfigurationModelError(f"invalid value for {key} from {', '.join(invalid)}")
            distinct = {repr(value) for _, value in typed}
            if len(distinct) > 1:
                details = ", ".join(f"{name}={value!r}" for name, value in typed)
                raise ConfigurationConflictError(f"conflicting values for {key}: {details}")
            if typed:
                source_name, value = typed[0]
                resolved[key] = ConfigurationValue(key, value, source_name)
            elif parameter.required:
                raise ConfigurationMissingError(f"required configuration missing: {key}")
            else:
                resolved[key] = ConfigurationValue(key, parameter.default, "default")
        return cls(authority, resolved)


def _coerce(value: Any, value_type: type) -> Any:
    if value_type is bool and isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
        raise ConfigurationModelError(f"invalid boolean value: {value!r}")
    if value_type is str:
        return str(value)
    try:
        return value if isinstance(value, value_type) else value_type(value)
    except (TypeError, ValueError) as exc:
        raise ConfigurationModelError(f"cannot coerce {value!r} to {value_type.__name__}") from exc


class YamlSourceAdapter:
    """Read-only YAML adapter with explicit canonical-key mapping."""

    source_name = ConfigurationSource.YAML.value

    def __init__(self, key_map: Mapping[str, str] | None = None) -> None:
        self.key_map = dict(key_map or {})

    def read(self, path: Path | str) -> Mapping[str, Any]:
        with Path(path).open("r", encoding="utf-8") as handle:
            document = yaml.safe_load(handle) or {}
        if not isinstance(document, Mapping):
            raise ConfigurationModelError(f"YAML root must be a mapping: {path}")
        flattened = _flatten(document)
        return SourceMapping(self.source_name, {self.key_map.get(key, key): value for key, value in flattened.items()})


class PythonConstantsAdapter:
    """Read literal module assignments through AST; modules are never imported."""

    source_name = ConfigurationSource.PYTHON.value

    def __init__(self, key_map: Mapping[str, str] | None = None) -> None:
        self.key_map = dict(key_map or {})

    def read(self, path: Path | str) -> Mapping[str, Any]:
        tree = ast.parse(Path(path).read_text(encoding="utf-8"), filename=str(path))
        values: dict[str, Any] = {}
        for node in tree.body:
            if not isinstance(node, ast.Assign) or len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
                continue
            try:
                value = ast.literal_eval(node.value)
            except (ValueError, TypeError, SyntaxError):
                continue
            name = node.targets[0].id
            values[self.key_map.get(name, name)] = value
        return SourceMapping(self.source_name, values)


class EnvironmentSourceAdapter:
    """Read only explicitly mapped environment names; secrets are not logged."""

    source_name = ConfigurationSource.ENV.value

    def __init__(self, values: Mapping[str, str] | None = None) -> None:
        self.values = dict(values or {})

    def read(self, key_map: Mapping[str, str]) -> Mapping[str, Any]:
        return SourceMapping(self.source_name, {key: self.values[name] for key, name in key_map.items() if name in self.values})


def _flatten(value: Mapping[str, Any], prefix: str = "") -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, item in value.items():
        full_key = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(item, Mapping):
            result.update(_flatten(item, full_key))
        else:
            result[full_key] = item
    return result


def _positive(value: Any) -> bool:
    return value > 0


def _non_negative(value: Any) -> bool:
    return value >= 0


def default_configuration_authority() -> ConfigurationAuthority:
    """Build the Phase 6.4 schema from already documented values only."""
    specs = (
        ("charge.manual.main.voltage_v", ConfigurationSection.CHARGE, "Manual Profile Domain", float, 14.7, _positive, "config/charge/manual.yaml"),
        ("charge.manual.main.current_a", ConfigurationSection.CHARGE, "Manual Profile Domain", float, 5.0, _positive, "config/charge/manual.yaml"),
        ("charge.manual.mix.hold_hours", ConfigurationSection.CHARGE, "Manual Strategy Domain", float, 2.0, _non_negative, "config/charge/manual.yaml"),
        ("strategy.mix.finish_hold_s", ConfigurationSection.STRATEGY, "Strategy Domain", float, 7200.0, _positive, "charge_logic.py / rd_live_adoption.py"),
        ("safety.max_voltage_v", ConfigurationSection.SAFETY, "Safety Domain", float, 18.0, _positive, "config/charge/limits.yaml"),
        ("safety.max_current_a", ConfigurationSection.SAFETY, "Safety Domain", float, 18.0, _positive, "config/charge/limits.yaml"),
        ("safety.max_temperature_c", ConfigurationSection.SAFETY, "Safety Domain", float, 55.0, _positive, "config/safety/safety_limits.yaml"),
        ("safety.watchdog_timeout_s", ConfigurationSection.SAFETY, "Runtime Safety", float, 300.0, _positive, "charge_logic.py"),
        ("containment.off_confirmation_poll_s", ConfigurationSection.CONTAINMENT, "SafeOutput/Containment", float, 0.5, _positive, "runtime_safety.py"),
        ("containment.orphan_output_grace_s", ConfigurationSection.CONTAINMENT, "SafeOutput/Containment", float, 45.0, _positive, "runtime_safety.py"),
        ("lease.ttl_s", ConfigurationSection.LEASE, "Lease Authority", float, 900.0, _positive, "ESPHome contract"),
        ("execution.readback_timeout_s", ConfigurationSection.EXECUTION, "Execution Boundary", float, 15.0, _positive, "config/runtime/runtime.yaml"),
        ("transport.telemetry_interval_s", ConfigurationSection.TRANSPORT, "Transport Adapter", float, 5.0, _positive, "config/runtime/runtime.yaml"),
        ("transport.ha_timeout_s", ConfigurationSection.TRANSPORT, "HA Adapter", float, 15.0, _positive, "runtime/v2_runtime.py"),
        ("ui.dashboard_refresh_s", ConfigurationSection.UI, "UI Adapter", float, 5.0, _positive, "config/runtime/runtime.yaml"),
        ("persistence.session_file", ConfigurationSection.PERSISTENCE, "Session Persistence", str, "charge_session.json", lambda value: bool(value.strip()), "charge_logic.py"),
    )
    return ConfigurationAuthority({
        key: ConfigurationParameter(key, section, owner, value_type, default, validator, description, source)
        for key, section, owner, value_type, default, validator, source in specs
        for description in (f"Phase 6.4 canonical candidate for {key}",)
    })


__all__ = [
    "ChargeConfig", "StrategyConfig", "SafetyConfig", "ContainmentConfig",
    "LeaseConfig", "ExecutionConfig", "TransportConfig", "UIConfig",
    "PersistenceConfig", "ConfigurationModel", "ConfigurationSource",
    "ConfigurationValue", "ConfigurationModelError", "ConfigurationConflictError",
    "ConfigurationMissingError", "YamlSourceAdapter", "PythonConstantsAdapter",
    "EnvironmentSourceAdapter", "SourceMapping", "default_configuration_authority",
]
