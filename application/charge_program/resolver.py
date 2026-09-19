"""Pure program selection boundary: Battery + Mode + Input -> ChargeProgram."""

from __future__ import annotations

from .catalog import SafetyDefaults, build_auto_program, build_manual_program
from .models import BatteryProfile, ChargeProgram, Chemistry, ManualProgramInput, Mode

SafetyPolicy = SafetyDefaults


class ChargeProgramResolver:
    """Select a catalog/provider result without owning recipe or phase logic."""

    def __init__(self, safety_policy: SafetyDefaults | None = None) -> None:
        self.safety_policy = safety_policy or SafetyDefaults()

    def resolve(self, battery: BatteryProfile, mode: Mode | str, manual: ManualProgramInput | None = None) -> ChargeProgram:
        if not isinstance(battery.chemistry, Chemistry):
            raise TypeError("BatteryProfile must contain canonical chemistry; resolve external names before constructing it")
        selected = Mode(str(mode).strip().upper()) if not isinstance(mode, Mode) else mode
        if selected is Mode.AUTO:
            if manual is not None:
                raise ValueError("AUTO program cannot accept Manual parameters")
            return build_auto_program(battery, self.safety_policy)
        if manual is None:
            raise ValueError("MANUAL program requires explicit Manual parameters")
        return build_manual_program(battery, manual, self.safety_policy)


def resolve_charge_program(battery: BatteryProfile, mode: Mode | str, manual: ManualProgramInput | None = None, *, safety_policy: SafetyDefaults | None = None) -> ChargeProgram:
    return ChargeProgramResolver(safety_policy).resolve(battery, mode, manual)


__all__ = ["ChargeProgramResolver", "SafetyPolicy", "resolve_charge_program"]
