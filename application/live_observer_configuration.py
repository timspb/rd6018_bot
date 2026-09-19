"""Secret-presence checks for a read-only live observer run.

Only presence and source labels are retained. Secret values are never returned,
logged or persisted.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Mapping


@dataclass(frozen=True)
class SecretAvailability:
    name: str
    status: str
    source: str


@dataclass(frozen=True)
class LiveObserverConfigurationResult:
    status: str
    execution_host: str
    secret_checks: tuple[SecretAvailability, ...]
    reader_mode: str
    writes_allowed: bool = False


class LiveObserverConfigurationCheck:
    """Check deployment boundary without inspecting or exposing secret values."""

    REQUIRED = ("HA_TOKEN", "ESPHOME_API_KEY")

    def check(self, environment: Mapping[str, str] | None = None) -> LiveObserverConfigurationResult:
        environment = os.environ if environment is None else environment
        checks = tuple(
            SecretAvailability(name, "AVAILABLE" if bool(environment.get(name)) else "MISSING", "deployment service environment")
            for name in self.REQUIRED
        )
        status = "LIVE_OBSERVER_CONFIGURATION_READY" if all(item.status == "AVAILABLE" for item in checks) else "BLOCKED"
        return LiveObserverConfigurationResult(status, "deployment host / V2 service environment", checks, "read-only", False)

    @staticmethod
    def safe_start_allowed(result: LiveObserverConfigurationResult) -> bool:
        return result.status == "LIVE_OBSERVER_CONFIGURATION_READY" and result.reader_mode == "read-only" and not result.writes_allowed


__all__ = ["SecretAvailability", "LiveObserverConfigurationResult", "LiveObserverConfigurationCheck"]
