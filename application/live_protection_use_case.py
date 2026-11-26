"""Dispatch the existing live protection decision through application effects."""
from __future__ import annotations

from typing import Any, Mapping, Optional

from config import TEMP_INT_PRECRITICAL
from runtime.safety.live_protection import evaluate_live_protection


async def dispatch_live_protection(
    *,
    app: Any,
    live: Mapping[str, Any],
    charge_active: bool,
    output_on: bool,
    internal_temperature_c: Optional[float],
    battery_voltage_v: float,
    current_a: float,
    external_temperature_c: float,
    amp_hours: float,
) -> None:
    """Evaluate once and perform the established ordered log/notify/stop effects.

    ``app`` is the existing production composition context: this use case owns
    no logger, notification transport, controller, or actuator instance.
    """
    decision = evaluate_live_protection(
        live=live,
        charge_active=charge_active,
        output_on=output_on,
        internal_temperature_c=internal_temperature_c,
        precritical_temperature_c=TEMP_INT_PRECRITICAL,
    )
    if "OPP_TRIGGERED" in decision.triggers:
        app.log_event(
            app.charge_controller.current_stage,
            battery_voltage_v, current_a, external_temperature_c,
            amp_hours, "OPP_TRIGGERED",
        )
        app._charge_notify("🛑 Сработала аппаратная защита мощности. Выход выключен.")
    if "OPP_TRIGGERED" in decision.triggers:
        await app._hard_stop_charge()

    if "TEMP_INT_PRECRITICAL" in decision.triggers:
        app.log_event(
            app.charge_controller.current_stage,
            battery_voltage_v, current_a, external_temperature_c,
            amp_hours, f"TEMP_INT_PRECRITICAL_{internal_temperature_c:.0f}C",
        )
        app._charge_notify(
            f"🌡 Температура блока {internal_temperature_c:.0f}°C ≥ "
            f"{TEMP_INT_PRECRITICAL:.0f}°C. Выход выключен для защиты БП."
        )
        await app._hard_stop_charge()


__all__ = ["dispatch_live_protection"]
