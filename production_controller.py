from __future__ import annotations

import time
from typing import Any, Optional, Tuple

from runtime.charge.strategy.mix_variables import (
    AGM_MIX_MAX_ACTIVE_HOURS,
    CA_MIX_MAX_ACTIVE_HOURS,
    EFB_MIX_MAX_ACTIVE_HOURS,
)
from charge_controller import ManagedChargeController
from runtime.charge.persistence import SESSION_FILE
from application.production_session_extensions import (
    OPERATOR_REASON_TEXT,
    restore_production_session_state,
)
from pb_domain import BatteryCondition, ChargeIntent


# Compatibility mapping for existing imports/UI tests. Canonical ownership is
# runtime.charge.strategy.mix_variables; do not add independent values here.
V2_MIX_MAX_HOURS = {
    "Ca/Ca": float(CA_MIX_MAX_ACTIVE_HOURS.default),
    "EFB": float(EFB_MIX_MAX_ACTIVE_HOURS.default),
    "AGM": float(AGM_MIX_MAX_ACTIVE_HOURS.default),
}

class ProductionChargeController(ManagedChargeController):
    """Live controller with recipe envelopes and production pause semantics."""
    PRODUCTION_EXTENSION_HOST = True

    # Legacy sessions without persisted intent migrate conservatively to the
    # same defaults historically applied by this production restore boundary.
    RESTORE_TRACE_DEFAULT_INTENT = ChargeIntent.NORMAL
    RESTORE_TRACE_DEFAULT_CONDITION = BatteryCondition.UNKNOWN
    _OPERATOR_REASON_TEXT = OPERATOR_REASON_TEXT

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
        rejection = restore_production_session_state(
            self,
            document,
            output_is_on=output_is_on,
            is_cv=is_cv,
            is_cc=is_cc,
        )
        if rejection is not None:
            return False, rejection

        return ok, message
