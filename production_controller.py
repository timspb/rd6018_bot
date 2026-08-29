from __future__ import annotations

import time
from typing import Optional, Tuple

from charge_controller_v2 import ChargeControllerV2
from legacy_recipe_adapter import chemistry_for_legacy_profile
from pb_domain import BatteryCondition, BatteryIdentity, ChargeContext, ChargeIntent
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

    def _current_stage_is_hv(self) -> bool:
        return self.current_stage in {self.STAGE_DESULFATION, self.STAGE_MIX}

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

    def _get_target_v_i(self, temp_c: Optional[float] = None) -> Tuple[float, float]:
        """Bound restored/device targets by the current recipe as well as new targets."""
        return self._bound_target(
            super()._get_target_v_i(temp_c),
            self._recipe_envelope(),
            hv=self._current_stage_is_hv(),
        )

    async def tick(self, *args, **kwargs):
        """Run managed V2 without legacy hourly Telegram chatter.

        The legacy scaffold still owns safety/mechanics, but its generic hourly
        ``Прошло Nч из ...`` report duplicates the terminal dashboard and, for Main,
        can display an undefined stage limit. Keep it for Custom/legacy operation only.
        """
        if self.is_active and self.battery_type != self.PROFILE_CUSTOM:
            self._last_hourly_report = time.time()
        return await super().tick(*args, **kwargs)

    def try_restore_session(
        self,
        voltage: float,
        current: float,
        ah: float,
    ) -> Tuple[bool, Optional[str]]:
        """Restore V2 sessions without granting recovery authority to legacy files.

        ChargeControllerV2 already persists battery/intent/condition in new session
        files. A pre-V2 session has no such intent. Treat that absence as NORMAL,
        never as the constructor's historical RECOVERY default, then rebuild the V2
        analyzer runtime with the conservative context. `_get_target_v_i()` also
        applies the resulting recipe envelope to any restored V/I pair.
        """
        document = self._read_legacy_session_document()
        ok, message = super().try_restore_session(voltage, current, ah)
        if not ok:
            return ok, message

        if not document.get("v2_intent"):
            self._v2_intent = ChargeIntent.NORMAL
            self._v2_condition_before = BatteryCondition.UNKNOWN
            self._initialize_shadow_session(started_at=self._v2_trace_started_at)
            self._write_trace_identity_to_session_file()

        # Keep cached restored values inside the same envelope as every subsequent
        # use. This also makes diagnostics/session snapshots show the bounded target.
        if self._restored_target_v > 0 and self._restored_target_i > 0:
            bounded_v, bounded_i = self._bound_target(
                (self._restored_target_v, self._restored_target_i),
                self._recipe_envelope(),
                hv=self._current_stage_is_hv(),
            )
            self._restored_target_v = bounded_v
            self._restored_target_i = bounded_i

        return ok, message
