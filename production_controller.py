from __future__ import annotations

from typing import Optional, Tuple

from charge_controller_v2 import ChargeControllerV2
from legacy_recipe_adapter import chemistry_for_legacy_profile
from pb_domain import BatteryIdentity, ChargeContext
from recipe_engine import RecipeEnvelope, select_recipe_envelope


class ProductionChargeControllerV2(ChargeControllerV2):
    """Live controller with recipe envelopes enforced at target generation.

    ChargeControllerV2 owns evidence-driven transitions. This final production layer
    makes the selected chemistry + intent + condition envelope authoritative for every
    generated target, including temperature-compensated targets and restore-derived
    stage transitions. The absolute RD6018 safety layer still sits below this class.

    Expert EFB conditioning is intentionally *not* enabled here automatically. An
    explicit expert workflow can opt into that envelope later; the standard Telegram
    V2 path is bounded by the normal/recovery ceiling selected by the intent.
    """

    def _recipe_envelope(self) -> Optional[RecipeEnvelope]:
        if self.battery_type == self.PROFILE_CUSTOM:
            return None
        chemistry = chemistry_for_legacy_profile(self.battery_type)
        identity = BatteryIdentity(
            battery_id=self._v2_battery_id or f"runtime:{self.battery_type}",
            chemistry=chemistry,
            nominal_capacity_ah=float(max(1, self.ah_capacity)),
        )
        return select_recipe_envelope(
            ChargeContext(
                identity=identity,
                intent=self._v2_intent,
                condition=self._v2_condition_before,
            ),
            expert_high_voltage=False,
        )

    @staticmethod
    def _bound_target(
        target: Tuple[float, float],
        envelope: Optional[RecipeEnvelope],
        *,
        hv: bool,
    ) -> Tuple[float, float]:
        if envelope is None:
            return target
        voltage_v, current_a = float(target[0]), float(target[1])
        current_limit = (
            envelope.hv_current_limit_a if hv else envelope.main_current_limit_a
        )
        return (
            min(voltage_v, float(envelope.voltage_ceiling_v)),
            min(current_a, float(current_limit)),
        )

    def _prep_target(self, temp_c: Optional[float] = None) -> Tuple[float, float]:
        return self._bound_target(
            super()._prep_target(temp_c),
            self._recipe_envelope(),
            hv=False,
        )

    def _main_target(self, temp_c: Optional[float] = None) -> Tuple[float, float]:
        return self._bound_target(
            super()._main_target(temp_c),
            self._recipe_envelope(),
            hv=False,
        )

    def _desulf_target(self, temp_c: Optional[float] = None) -> Tuple[float, float]:
        return self._bound_target(
            super()._desulf_target(temp_c),
            self._recipe_envelope(),
            hv=True,
        )

    def _mix_target(self, temp_c: Optional[float] = None) -> Tuple[float, float]:
        return self._bound_target(
            super()._mix_target(temp_c),
            self._recipe_envelope(),
            hv=True,
        )
