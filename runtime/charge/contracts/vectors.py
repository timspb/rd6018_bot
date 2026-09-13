"""Fixed representative vectors for native Manual and Minimum programs."""

from ..battery import BatteryProfile
from ..chemistry import ChemistryProfile
from ..intent import ChargeIntent
from ..measurements import Measurements
from ..state import ChargeState
from .cases import ChargeDecisionCase


_MANUAL_BATTERY = BatteryProfile(ChemistryProfile.AGM, 80.0)
_MINIMUM_BATTERY = BatteryProfile(ChemistryProfile.EFB, 72.0)

manual_cases = (
    ChargeDecisionCase(
        case_id="manual-basic",
        battery_profile=_MANUAL_BATTERY,
        measurements=Measurements(12.6, 0.0, 25.0, 1.0),
        charge_state=ChargeState(program="manual", stage="manual"),
        input_config={"program": "manual", "voltage": 14.7, "current": 5.0},
        expected_intent=ChargeIntent(14.7, 5.0, "manual", False, "MANUAL_START"),
    ),
)

minimum_cases = (
    ChargeDecisionCase(
        case_id="minimum-active",
        battery_profile=_MINIMUM_BATTERY,
        measurements=Measurements(14.0, 2.0, 25.0, 1.0),
        charge_state=ChargeState(program="minimum", stage="main"),
        input_config={"program": "minimum", "target_voltage": 14.4, "target_current": 5.0, "completion_current": 0.3, "completion_voltage": 14.2},
        expected_intent=ChargeIntent(14.4, 5.0, "minimum", False, "MINIMUM_ACTIVE"),
    ),
    ChargeDecisionCase(
        case_id="minimum-complete",
        battery_profile=_MINIMUM_BATTERY,
        measurements=Measurements(14.3, 0.2, 25.0, 2.0),
        charge_state=ChargeState(program="minimum", stage="main"),
        input_config={"program": "minimum", "target_voltage": 14.4, "target_current": 5.0, "completion_current": 0.3, "completion_voltage": 14.2},
        expected_intent=ChargeIntent(14.4, 5.0, "delta", True, "MINIMUM_COMPLETE"),
    ),
)
