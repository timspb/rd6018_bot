"""Staged V3 configuration ownership coordinator for Phase 11.1."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping

from .configuration_model import ConfigurationModel


class ConfigurationOwnershipState(str, Enum):
    V3_CANONICAL = "V3_CANONICAL"
    V2_ROLLBACK = "V2_ROLLBACK"


class ConfigurationParityState(str, Enum):
    EQUAL = "equal"
    DIFFERENT = "different"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ConfigurationParity:
    state: ConfigurationParityState
    differences: Mapping[str, Mapping[str, Any]]

    def __post_init__(self) -> None:
        object.__setattr__(self, "differences", MappingProxyType(dict(self.differences)))


@dataclass(frozen=True)
class ConfigurationOwnershipView:
    trace_id: str
    state: ConfigurationOwnershipState
    canonical: Mapping[str, Any]
    v2_effective: Mapping[str, Any]
    provenance: Mapping[str, str]
    parity: ConfigurationParity
    observed_at: datetime

    def __post_init__(self) -> None:
        if not self.trace_id.strip():
            raise ValueError("trace_id is required")
        object.__setattr__(self, "canonical", MappingProxyType(dict(self.canonical)))
        object.__setattr__(self, "v2_effective", MappingProxyType(dict(self.v2_effective)))
        object.__setattr__(self, "provenance", MappingProxyType(dict(self.provenance)))


class ConfigurationOwnershipCoordinator:
    """Publish V3 config view while retaining explicit V2 rollback."""

    def __init__(self) -> None:
        self.state = ConfigurationOwnershipState.V3_CANONICAL
        self._v2_view: Mapping[str, Any] = {}
        self._canonical: Mapping[str, Any] = {}
        self._provenance: Mapping[str, str] = {}
        self._shadow_evidence: list[ConfigurationOwnershipView] = []

    @property
    def shadow_evidence(self) -> tuple[ConfigurationOwnershipView, ...]:
        return tuple(self._shadow_evidence)

    def publish(
        self,
        *,
        trace_id: str,
        model: ConfigurationModel,
        v2_effective: Mapping[str, Any],
        now: datetime | None = None,
    ) -> ConfigurationOwnershipView:
        if not trace_id.strip():
            raise ValueError("trace_id is required")
        if not isinstance(model, ConfigurationModel):
            raise TypeError("validated ConfigurationModel is required")
        current = now or datetime.now(timezone.utc)
        canonical = {key: model.get(key) for key in model.keys()}
        provenance = {key: model.value(key).source for key in model.keys()}
        parity = self._compare(canonical, v2_effective)
        self._canonical = canonical
        self._v2_view = dict(v2_effective)
        self._provenance = provenance
        self.state = ConfigurationOwnershipState.V3_CANONICAL
        view = ConfigurationOwnershipView(trace_id, self.state, canonical, v2_effective, provenance, parity, current)
        self._shadow_evidence.append(view)
        return view

    def canonical_view(self) -> Mapping[str, Any]:
        return self._v2_view if self.state is ConfigurationOwnershipState.V2_ROLLBACK else self._canonical

    def rollback_to_v2(self, *, trace_id: str, now: datetime | None = None) -> ConfigurationOwnershipView:
        if not trace_id.strip():
            raise ValueError("trace_id is required")
        current = now or datetime.now(timezone.utc)
        self.state = ConfigurationOwnershipState.V2_ROLLBACK
        parity = self._compare(self._v2_view, self._v2_view)
        view = ConfigurationOwnershipView(trace_id, self.state, self._v2_view, self._v2_view, {}, parity, current)
        self._shadow_evidence.append(view)
        return view

    @staticmethod
    def _compare(canonical: Mapping[str, Any], v2: Mapping[str, Any]) -> ConfigurationParity:
        if not canonical and not v2:
            return ConfigurationParity(ConfigurationParityState.UNKNOWN, {})
        differences = {
            key: {"canonical": canonical.get(key), "v2": v2.get(key)}
            for key in sorted(set(canonical) | set(v2))
            if canonical.get(key) != v2.get(key)
        }
        return ConfigurationParity(ConfigurationParityState.EQUAL if not differences else ConfigurationParityState.DIFFERENT, differences)


__all__ = ["ConfigurationOwnershipState", "ConfigurationParityState", "ConfigurationParity", "ConfigurationOwnershipView", "ConfigurationOwnershipCoordinator"]
