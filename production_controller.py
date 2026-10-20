from __future__ import annotations

import time  # stable patch point retained for restore contract tests

from runtime.charge.strategy.mix_variables import (
    AGM_MIX_MAX_ACTIVE_HOURS,
    CA_MIX_MAX_ACTIVE_HOURS,
    EFB_MIX_MAX_ACTIVE_HOURS,
)
from charge_controller import ManagedChargeController
from runtime.charge.persistence import SESSION_FILE
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
