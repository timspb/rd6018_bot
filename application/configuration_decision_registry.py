"""Explicit unresolved configuration decisions; no values are selected."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ConfigurationDecisionStatus(str, Enum):
    RESOLVED = "RESOLVED"
    UNRESOLVED = "UNRESOLVED"
    MIGRATION_REQUIRED = "MIGRATION_REQUIRED"


@dataclass(frozen=True)
class ConfigurationDecision:
    key: str
    section: str
    sources: tuple[str, ...]
    candidates: tuple[str, ...]
    owner: str
    status: ConfigurationDecisionStatus = ConfigurationDecisionStatus.UNRESOLVED

    def __post_init__(self) -> None:
        if not self.key.strip() or not self.section.strip() or not self.owner.strip():
            raise ValueError("configuration decision identity is required")
        if not self.sources or not self.candidates:
            raise ValueError("sources and candidates are required")


UNRESOLVED_CONFIGURATION_DECISIONS = (
    ConfigurationDecision("telemetry.cross_source_tolerance_v", "transport", ("config/runtime/runtime.yaml",), ("0.06 V",), "Telemetry Authority", ConfigurationDecisionStatus.RESOLVED),
    ConfigurationDecision("charge.manual.main.voltage_v", "charge", ("config/charge/manual.yaml", "legacy manual path"), ("YAML candidate", "legacy runtime candidate"), "Profile Domain", ConfigurationDecisionStatus.MIGRATION_REQUIRED),
    ConfigurationDecision("strategy.mix.max_age", "strategy", ("charge_logic.py", "docs/assistant/CHARGE_STRATEGY.md"), ("EFB 20 h", "EFB 24 h"), "Strategy Domain"),
    ConfigurationDecision("safety.watchdog_timeout_s", "safety", ("runtime/v2_runtime.py", "charge_logic.py"), ("180 s", "300 s"), "Safety Decision Authority"),
    ConfigurationDecision("execution.readback_timeout_s", "execution", ("runtime/output/bridge/executor.py", "rd6018_telemetry.py", "runtime_safety_strict.py"), ("5 s", "10 s", "15 s"), "Execution Verification Boundary"),
    ConfigurationDecision("safety.temperature_thresholds", "safety", ("charge_logic.py", "config/safety/safety_limits.yaml"), ("legacy staged thresholds", "outer device limit only"), "Safety Decision Authority"),
    ConfigurationDecision("transport.default_priority", "transport", ("config/physical/transports.yaml", "config/physical/connectors.yaml"), ("HA default", "ESP Direct default"), "Transport Authority"),
    ConfigurationDecision("lease.renewal_interval", "lease", ("edge lease modules", "deployment environment"), ("runtime-derived", "deployment-specific"), "Lease Authority"),
    ConfigurationDecision("profile.flooded", "charge", ("config/charge/recipes.yaml", "profile registry"), ("complete recipe", "unavailable until defined"), "Profile Domain"),
    ConfigurationDecision("profile.custom.schema", "charge", ("V2 custom path", "V3 profile contract"), ("legacy custom", "typed V3 custom"), "Profile Domain"),
)


def unresolved_configuration_decisions() -> tuple[ConfigurationDecision, ...]:
    return UNRESOLVED_CONFIGURATION_DECISIONS


__all__ = ["ConfigurationDecisionStatus", "ConfigurationDecision", "UNRESOLVED_CONFIGURATION_DECISIONS", "unresolved_configuration_decisions"]
