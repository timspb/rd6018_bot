from __future__ import annotations

import json
import logging
import math
import os
import time
from typing import Any, Dict, Optional, Tuple

from runtime.charge.runtime.cooling_guard import validate_cooling_pause
from runtime.charge.strategy.main_targets import select_main_target
from runtime.charge.strategy.mix_variables import (
    AGM_MIX_MAX_ACTIVE_HOURS,
    CA_MIX_MAX_ACTIVE_HOURS,
    EFB_MIX_MAX_ACTIVE_HOURS,
)
from charge_controller import ManagedChargeController
from runtime.charge.persistence import SESSION_FILE
from cooling_runtime import CoolingAwareShadowRecoveryRuntime
from application.production_target_policy import bound_target, recipe_envelope
from application.production_session_extensions import (
    OPERATOR_REASON_TEXT,
    reset_continuous_tail_hold,
    restore_finish_state,
    restore_runtime_signal_snapshot,
    restore_runtime_signal_state,
    session_document_extensions,
    valid_finish_evidence,
)
from pb_domain import BatteryCondition, ChargeIntent


logger = logging.getLogger("rd6018.production_controller")


# Compatibility mapping for existing imports/UI tests. Canonical ownership is
# runtime.charge.strategy.mix_variables; do not add independent values here.
V2_MIX_MAX_HOURS = {
    "Ca/Ca": float(CA_MIX_MAX_ACTIVE_HOURS.default),
    "EFB": float(EFB_MIX_MAX_ACTIVE_HOURS.default),
    "AGM": float(AGM_MIX_MAX_ACTIVE_HOURS.default),
}

class ProductionChargeController(ManagedChargeController):
    """Live controller with recipe envelopes and production pause semantics."""

    # Legacy sessions without persisted intent migrate conservatively to the
    # same defaults historically applied by this production restore boundary.
    RESTORE_TRACE_DEFAULT_INTENT = ChargeIntent.NORMAL
    RESTORE_TRACE_DEFAULT_CONDITION = BatteryCondition.UNKNOWN
    _OPERATOR_REASON_TEXT = OPERATOR_REASON_TEXT

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._v2_continuous_tail_since: Optional[float] = None
        self._v2_continuous_tail_stage_start: Optional[float] = None
        self._v2_cooling_pause: Optional[Dict[str, Any]] = None
        self._finish_evidence: Optional[Dict[str, Any]] = None

    def _new_runtime(self, *, started_at: float) -> CoolingAwareShadowRecoveryRuntime:
        battery_id = self._v2_battery_id or (
            f"session:{self.battery_type}:{self.ah_capacity}:{int(started_at)}"
        )
        runtime = CoolingAwareShadowRecoveryRuntime(
            battery_id=battery_id,
            started_at=started_at,
            intent=self._v2_intent,
            condition_before=self._v2_condition_before,
        )
        self._v2_runtime = runtime
        return runtime

    def _bound_recipe_target(self, target: Tuple[float, float], *, hv: bool) -> Tuple[float, float]:
        envelope = recipe_envelope(
            profile=self.battery_type,
            capacity_ah=self.ah_capacity,
            battery_id=self._v2_battery_id,
            intent=self._v2_intent,
            condition=self._v2_condition_before,
        )
        return bound_target(target, envelope, hv=hv)

    def _prep_target(self, temp_c: Optional[float] = None) -> Tuple[float, float]:
        return self._bound_recipe_target(super()._prep_target(temp_c), hv=False)

    def _main_target(self, temp_c: Optional[float] = None) -> Tuple[float, float]:
        if self.battery_type == self.PROFILE_CUSTOM:
            target = super()._main_target(temp_c)
        else:
            base = select_main_target(
                profile=self.battery_type,
                capacity_ah=float(self.ah_capacity),
                agm_stage_idx=int(self._agm_stage_idx),
            )
            target = (
                self._apply_temperature_compensation(base.voltage_v, temp_c),
                base.current_a,
            )
        return self._bound_recipe_target(target, hv=False)

    def _desulf_target(self, temp_c: Optional[float] = None) -> Tuple[float, float]:
        return self._bound_recipe_target(super()._desulf_target(temp_c), hv=True)

    def _mix_target(self, temp_c: Optional[float] = None) -> Tuple[float, float]:
        return self._bound_recipe_target(super()._mix_target(temp_c), hv=True)

    def _get_target_v_i(self, temp_c: Optional[float] = None) -> Tuple[float, float]:
        return self._bound_recipe_target(
            super()._get_target_v_i(temp_c),
            hv=self.current_stage in {self.STAGE_DESULFATION, self.STAGE_MIX},
        )


    def _session_document_extensions(self, document: Dict[str, Any]) -> Dict[str, Any]:
        return session_document_extensions(self, document)


    def try_restore_session(
        self,
        voltage: float,
        current: float,
        ah: float,
        output_is_on: Optional[Any] = None,
        is_cv: Optional[bool] = None,
        is_cc: Optional[bool] = None,
    ) -> Tuple[bool, Optional[str]]:
        """Restore V2 sessions without granting recovery authority to legacy files."""
        ok, message = super().try_restore_session(voltage, current, ah)
        if not ok:
            return ok, message
        document = dict(getattr(self, "_session_restore_document", {}))

        reset_continuous_tail_hold(self)

        # A persisted Guard is authority-bearing state. Restore it from the
        # exact canonical session identity before any caller can consider an
        # automatic continuation; never reconstruct a missing checkpoint.
        from runtime.charge.strategy.main_guard_session import GUARD_KEY, read_guard
        self._main_current_guard = None
        self._main_current_guard_revision = None
        if GUARD_KEY in document:
            guard, revision = read_guard(
                document,
                session_id=str(self._v2_trace_session_id or ""),
                battery_id=str(self._v2_battery_id or ""),
                now_s=float(time.time()),
            )
            self._main_current_guard = guard
            self._main_current_guard_revision = revision

        if not document.get("v2_intent"):
            self._v2_intent = ChargeIntent.NORMAL
            self._v2_condition_before = BatteryCondition.UNKNOWN
            self._initialize_shadow_session(started_at=self._v2_trace_started_at)

        if self.current_stage == self.STAGE_MIX:
            restore_finish_state(self, document)
            restore_runtime_signal_state(
                self,
                document,
                output_is_on=output_is_on,
                is_cv=is_cv,
                is_cc=is_cc,
            )

        if self._restored_target_v > 0 and self._restored_target_i > 0:
            bounded_v, bounded_i = bound_target(
                (self._restored_target_v, self._restored_target_i),
                recipe_envelope(
                    profile=self.battery_type,
                    capacity_ah=self.ah_capacity,
                    battery_id=self._v2_battery_id,
                    intent=self._v2_intent,
                    condition=self._v2_condition_before,
                ),
                hv=self.current_stage in {self.STAGE_DESULFATION, self.STAGE_MIX},
            )
            self._restored_target_v = bounded_v
            self._restored_target_i = bounded_i

        pause = document.get("v2_cooling_pause")
        if self.current_stage == self.STAGE_COOLING and isinstance(pause, dict):
            self._v2_cooling_pause = dict(pause)
            self._cooling_from_stage = str(pause.get("source_stage") or self.STAGE_MAIN)
            self._cooling_target_v = float(pause.get("target_v") or 0.0)
            self._cooling_target_i = float(pause.get("target_i") or 0.0)
            self.finish_timer_start = pause.get("finish_timer_start")
            self._delta_reported = bool(pause.get("delta_reported", False))
            self._delta_trigger_mode = pause.get("delta_trigger_mode")
            evidence = pause.get("finish_evidence")
            self._finish_evidence = (
                dict(evidence)
                if valid_finish_evidence(self, evidence, mode=self._delta_trigger_mode)
                else None
            )
            restore_runtime_signal_snapshot(self, dict(pause.get("runtime_signal") or {}))
            self._v2_target_voltage_v = self._cooling_target_v or self._v2_target_voltage_v

        if self.current_stage == self.STAGE_COOLING:
            valid, reason = validate_cooling_pause(self, self._v2_cooling_pause)
            if not valid:
                self.stop(clear_session=True)
                return (
                    False,
                    "Cooling session rejected: durable V2 pause state is missing/invalid "
                    f"({reason}); automatic resume is disabled and Output must remain OFF.",
                )

        return ok, message
