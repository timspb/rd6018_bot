"""Canonical production host configuration and constructor."""

from __future__ import annotations

from typing import Any, Callable, Optional

from charge_controller import ManagedChargeController
from runtime.charge.host_configuration import (
    ManagedChargeHostConfiguration,
    PRODUCTION_CHARGE_HOST_CONFIGURATION,
)
from runtime.charge.strategy.mix_variables import (
    AGM_MIX_MAX_ACTIVE_HOURS,
    CA_MIX_MAX_ACTIVE_HOURS,
    EFB_MIX_MAX_ACTIVE_HOURS,
)


V2_MIX_MAX_HOURS = {
    "Ca/Ca": float(CA_MIX_MAX_ACTIVE_HOURS.default),
    "EFB": float(EFB_MIX_MAX_ACTIVE_HOURS.default),
    "AGM": float(AGM_MIX_MAX_ACTIVE_HOURS.default),
}


def create_production_charge_host(
    hass: Any,
    notify_cb: Optional[Callable[[str], Any]] = None,
    *,
    battery_id: Optional[str] = None,
) -> ManagedChargeController:
    """Create the sole controller class with explicit production policy."""
    return ManagedChargeController(
        hass,
        notify_cb=notify_cb,
        battery_id=battery_id,
        host_configuration=PRODUCTION_CHARGE_HOST_CONFIGURATION,
    )


def configure_production_charge_host(host: ManagedChargeController) -> ManagedChargeController:
    """Apply production policy to the same canonical host, preserving identity."""
    if type(host) is not ManagedChargeController:
        raise TypeError("production host must be the canonical ManagedChargeController")
    if host.host_configuration == PRODUCTION_CHARGE_HOST_CONFIGURATION:
        return host
    was_production_configured = host.host_configuration.production_extensions_enabled
    host.host_configuration = PRODUCTION_CHARGE_HOST_CONFIGURATION
    if was_production_configured:
        return host
    from application.production_session_extensions import initialize_production_session_state
    from runtime.charge.diagnostics import initialize_battery_fault_state
    initialize_production_session_state(host)
    initialize_battery_fault_state(host)
    return host
