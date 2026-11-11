"""Read-only states for HANDS_OFF, unknown Output ON and idle."""
from __future__ import annotations
from .hmi_state import HmiProcessState, HmiAuthority, OperatorHmiState

def unmanaged_hmi_state(
    *, hands_off: bool,
    output_on: bool, regulator: str, battery_v: float | None,
    current: float | None, power: float | None, temp_ext: float | None,
    temp_int: float | None, set_v: float | None, set_i: float | None,
    safety: str, attention: str,
) -> OperatorHmiState:
    if hands_off:
        return OperatorHmiState(
            process_state=HmiProcessState.HANDS_OFF,
            authority=HmiAuthority.EXTERNAL,
            title="RD6018 · РУЧНОЕ УПРАВЛЕНИЕ",
            output_on=output_on,
            regulator=regulator,
            battery_label="",
            battery_voltage_v=battery_v,
            current_a=current,
            power_w=power,
            battery_temp_c=temp_ext,
            psu_temp_c=temp_int,
            target_voltage_v=set_v,
            current_limit_a=set_i,
            progress=(
                "Внешняя сессия · автоматика не меняет Output и уставки"
                if output_on
                else "RD свободен от Pb-автоматики"
            ),
            safety=safety,
            attention=attention,
        )

    if output_on:
        return OperatorHmiState(
            process_state=HmiProcessState.CONTAINMENT,
            authority=HmiAuthority.CONTAINMENT,
            title="RD6018 · OUTPUT ВНЕ СЕССИИ",
            output_on=True,
            regulator=regulator,
            battery_label="",
            battery_voltage_v=battery_v,
            current_a=current,
            power_w=power,
            battery_temp_c=temp_ext,
            psu_temp_c=temp_int,
            target_voltage_v=set_v,
            current_limit_a=set_i,
            progress="Нет подтверждённой управляемой сессии",
            safety="⚠️ Требуется проверка ownership",
            attention="alarm",
        )

    return OperatorHmiState(
        process_state=HmiProcessState.IDLE,
        authority=HmiAuthority.NONE,
        title="RD6018 · ГОТОВ",
        output_on=False,
        regulator=regulator,
        battery_label="",
        battery_voltage_v=battery_v,
        current_a=current,
        power_w=power,
        battery_temp_c=temp_ext,
        psu_temp_c=temp_int,
        target_voltage_v=set_v,
        current_limit_a=set_i,
        progress="Готов к новой программе",
        safety=safety,
        attention=attention,
    )
