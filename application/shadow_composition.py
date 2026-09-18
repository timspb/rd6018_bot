"""Phase 8.6 V3-only shadow composition root.

This graph is opt-in and has no production bootstrap entrypoint.  Its
transport readers are injected and default to empty in-memory readers; its
persistence provider is in-memory only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .charge_orchestration import ChargeApplicationService
from .configuration_model import ConfigurationModel, YamlSourceAdapter, default_configuration_authority
from .composition_contract import ApplicationComposition as LegacyCompositionContract
from .diagnostics_domain import DiagnosticsDomain
from .execution_boundary import ExecutionDispatcher
from .persistence_boundary import InMemoryPersistenceProvider
from .telemetry_authority import ESPDirectTelemetryAdapter, HATelemetryAdapter, TelemetryArbitrator
from .transport_adapters_shadow import ESPDirectExecutionAdapter, HAExecutionAdapter
from .ui_adapter import OperatorUIAdapter
from runtime.charge import ProfileRegistry, SessionManager


@dataclass(frozen=True)
class ShadowDomainComponents:
    profiles: ProfileRegistry
    sessions: SessionManager


@dataclass(frozen=True)
class ShadowTelemetryComponents:
    esp_direct: ESPDirectTelemetryAdapter
    ha: HATelemetryAdapter
    arbitrator: TelemetryArbitrator


@dataclass(frozen=True)
class ShadowTransportComponents:
    ha: HAExecutionAdapter
    esp_direct: ESPDirectExecutionAdapter


@dataclass(frozen=True)
class ApplicationComposition:
    """Complete V3 graph; every dependency is explicit and shadow-only."""

    ui: OperatorUIAdapter
    application: ChargeApplicationService
    domain: ShadowDomainComponents
    configuration: ConfigurationModel
    telemetry: ShadowTelemetryComponents
    execution: ExecutionDispatcher
    transport: ShadowTransportComponents
    persistence: InMemoryPersistenceProvider
    diagnostics: DiagnosticsDomain

    @classmethod
    def shadow(
        cls,
        *,
        esp_reader=None,
        ha_reader=None,
        config_root=None,
    ) -> "ApplicationComposition":
        root = config_root
        authority = default_configuration_authority()
        sources = []
        if root is not None:
            yaml_adapter = YamlSourceAdapter({
                "manual.main.voltage_v": "charge.manual.main.voltage_v",
                "manual.main.current_a": "charge.manual.main.current_a",
                "manual.mix.hold_hours": "charge.manual.mix.hold_hours",
                "max_voltage_v": "safety.max_voltage_v",
                "max_current_a": "safety.max_current_a",
            })
            sources.extend((
                yaml_adapter.read(root / "config" / "charge" / "manual.yaml"),
                yaml_adapter.read(root / "config" / "charge" / "limits.yaml"),
            ))
        configuration = ConfigurationModel.resolve(authority, sources)
        profiles = ProfileRegistry.with_defaults()
        sessions = SessionManager()
        domain = ShadowDomainComponents(profiles, sessions)
        telemetry = ShadowTelemetryComponents(
            ESPDirectTelemetryAdapter(esp_reader or (lambda: {})),
            HATelemetryAdapter(ha_reader or (lambda: {})),
            TelemetryArbitrator(),
        )
        return cls(
            ui=OperatorUIAdapter(),
            application=ChargeApplicationService(profiles, sessions),
            domain=domain,
            configuration=configuration,
            telemetry=telemetry,
            execution=ExecutionDispatcher(),
            transport=ShadowTransportComponents(HAExecutionAdapter(), ESPDirectExecutionAdapter()),
            persistence=InMemoryPersistenceProvider(),
            diagnostics=DiagnosticsDomain(),
        )


def legacy_contract_shape() -> type[LegacyCompositionContract]:
    """Expose the Phase 6 contract for static compatibility checks only."""
    return LegacyCompositionContract


__all__ = ["ApplicationComposition", "ShadowDomainComponents", "ShadowTelemetryComponents", "ShadowTransportComponents"]
