"""Complete configuration inventory; unresolved entries never choose values."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .configuration_authority import ConfigurationSection
from .configuration_decision_registry import unresolved_configuration_decisions
from .configuration_model import default_configuration_authority


@dataclass(frozen=True)
class ConfigurationRegistryEntry:
    name: str
    section: str
    owner: str
    value_type: str
    default: Any
    validator: Callable[[Any], bool]
    provenance: tuple[str, ...]
    migration_status: str


def canonical_configuration_registry() -> tuple[ConfigurationRegistryEntry, ...]:
    authority = default_configuration_authority()
    entries = [
        ConfigurationRegistryEntry(
            key, parameter.section.value, parameter.owner, parameter.value_type.__name__,
            parameter.default, parameter.validator, (parameter.source,), "CANONICAL_CANDIDATE",
        )
        for key in authority.keys()
        for parameter in (authority.get(key),)
    ]
    known = {entry.name for entry in entries}
    for decision in unresolved_configuration_decisions():
        if decision.key in known:
            continue
        entries.append(ConfigurationRegistryEntry(
            decision.key, decision.section, decision.owner, "UNRESOLVED", None,
            lambda value: value is not None, decision.sources, decision.status.value,
        ))
    return tuple(sorted(entries, key=lambda entry: entry.name))


def configuration_drift_entries() -> tuple[ConfigurationRegistryEntry, ...]:
    return tuple(entry for entry in canonical_configuration_registry() if entry.migration_status != "CANONICAL_CANDIDATE")


__all__ = ["ConfigurationRegistryEntry", "canonical_configuration_registry", "configuration_drift_entries"]
