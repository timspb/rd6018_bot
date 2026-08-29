from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, FrozenSet, Optional, Tuple

from battery_diagnostics import (
    DiagnosticHypothesis,
    DiagnosticLevel,
    SpecificGravityAssessment,
)


class DiagnosticAuthority(str, Enum):
    ALLOW = "allow"
    VERIFY_BEFORE_HV = "verify_before_hv"
    BLOCK_AUTOMATIC_HV = "block_automatic_hv"
    HARD_STOP = "hard_stop"


@dataclass(frozen=True)
class BatteryFaultContext:
    """Independent diagnostic evidence collected around one physical battery.

    The engine intentionally distinguishes observation context from values.  Rested OCV
    is only strong cell-fault evidence when the battery was known fully charged and
    isolated from external loads.  Specific-gravity imbalance alone is not a failed-cell
    verdict because corrective equalization may be the appropriate flooded-battery
    treatment; persistence after a corrective equalization is stronger evidence.
    """

    legacy_risk_score: int = 0
    legacy_risk_status: str = "stable"
    rested_ocv_v: Optional[float] = None
    fully_charged_before_rest: bool = False
    battery_isolated_during_rest: bool = False
    relaxation_drop_1h_v: Optional[float] = None
    relaxation_drop_12h_v: Optional[float] = None
    specific_gravity: Optional[SpecificGravityAssessment] = None
    sg_persisted_after_corrective_equalization: bool = False
    recovery_attempts: int = 0
    recovery_response_improved: Optional[bool] = None
    abnormal_thermal_response: bool = False
    external_failed_cell_confirmed: bool = False
    external_load_test_failed: bool = False
    dynamic_loop_worsened: bool = False
    charger_path_suspected: bool = False


@dataclass(frozen=True)
class HypothesisEvidence:
    hypothesis: DiagnosticHypothesis
    score: int
    level: DiagnosticLevel
    reasons: Tuple[str, ...]


@dataclass(frozen=True)
class BatteryFaultAssessment:
    hypotheses: Dict[DiagnosticHypothesis, HypothesisEvidence]
    authority: DiagnosticAuthority
    authority_reasons: Tuple[str, ...]
    independent_cell_fault_classes: FrozenSet[str]

    def evidence(self, hypothesis: DiagnosticHypothesis) -> HypothesisEvidence:
        return self.hypotheses[hypothesis]


LEVEL_THRESHOLDS = (
    (80, DiagnosticLevel.HIGH),
    (60, DiagnosticLevel.PROBABLE),
    (35, DiagnosticLevel.VERIFY),
    (15, DiagnosticLevel.WATCH),
)


def _level(score: int) -> DiagnosticLevel:
    for threshold, level in LEVEL_THRESHOLDS:
        if score >= threshold:
            return level
    return DiagnosticLevel.NORMAL


def _bounded(value: int) -> int:
    return max(0, min(100, int(value)))


def assess_battery_fault(context: BatteryFaultContext) -> BatteryFaultAssessment:
    scores: Dict[DiagnosticHypothesis, int] = {h: 0 for h in DiagnosticHypothesis}
    reasons: Dict[DiagnosticHypothesis, list[str]] = {h: [] for h in DiagnosticHypothesis}
    cell_classes: set[str] = set()

    def add(hypothesis: DiagnosticHypothesis, points: int, reason: str) -> None:
        scores[hypothesis] = _bounded(scores[hypothesis] + points)
        reasons[hypothesis].append(reason)

    # Keep the old detector as weak generic evidence only.  It cannot prove a cell
    # failure and therefore never contributes an independent confirmation class.
    legacy = _bounded(context.legacy_risk_score)
    if legacy >= 70:
        add(DiagnosticHypothesis.CELL_FAULT, 10, "legacy_risk_high")
        add(DiagnosticHypothesis.CAPACITY_LOSS, 10, "legacy_risk_high")
    elif legacy >= 50:
        add(DiagnosticHypothesis.CELL_FAULT, 5, "legacy_risk_probable")
        add(DiagnosticHypothesis.CAPACITY_LOSS, 5, "legacy_risk_probable")

    # A roughly five-cell total-voltage pattern after a known complete charge/rest is
    # strong evidence only when external loads were absent.  Wide limits deliberately
    # avoid pretending RD6018 voltage is a laboratory cell analyzer.
    if (
        context.rested_ocv_v is not None
        and context.fully_charged_before_rest
        and context.battery_isolated_during_rest
    ):
        ocv = float(context.rested_ocv_v)
        if 9.8 <= ocv <= 11.4:
            add(DiagnosticHypothesis.CELL_FAULT, 65, "rested_isolated_ocv_five_cell_pattern")
            cell_classes.add("rested_ocv")
        elif ocv < 12.0:
            add(DiagnosticHypothesis.SELF_DISCHARGE, 30, "rested_isolated_ocv_low_after_full_charge")

    if context.relaxation_drop_1h_v is not None and context.battery_isolated_during_rest:
        drop = max(0.0, float(context.relaxation_drop_1h_v))
        if drop >= 0.50:
            add(DiagnosticHypothesis.SELF_DISCHARGE, 25, "rapid_isolated_1h_relaxation")
        elif drop >= 0.25:
            add(DiagnosticHypothesis.SELF_DISCHARGE, 10, "elevated_isolated_1h_relaxation")
    if context.relaxation_drop_12h_v is not None and context.battery_isolated_during_rest:
        drop = max(0.0, float(context.relaxation_drop_12h_v))
        if drop >= 0.75:
            add(DiagnosticHypothesis.SELF_DISCHARGE, 35, "large_isolated_12h_voltage_loss")
            cell_classes.add("self_discharge")
        elif drop >= 0.40:
            add(DiagnosticHypothesis.SELF_DISCHARGE, 20, "elevated_isolated_12h_voltage_loss")

    sg = context.specific_gravity
    if sg is not None:
        if sg.level is DiagnosticLevel.VERIFY:
            add(DiagnosticHypothesis.STRATIFICATION, 45, "specific_gravity_spread_requires_equalize_retest")
        if sg.low_outlier_cells:
            add(DiagnosticHypothesis.STRATIFICATION, 15, "specific_gravity_low_cell_outlier")
        if (
            context.sg_persisted_after_corrective_equalization
            and sg.spread is not None
            and sg.spread >= 0.030
            and sg.valid_cell_count == 6
        ):
            # Persistence after the manufacturer-recommended corrective/retest path is
            # qualitatively different from a first imbalance reading.
            add(DiagnosticHypothesis.CELL_FAULT, 35, "sg_imbalance_persists_after_corrective_equalization")
            cell_classes.add("persistent_sg")

    if context.recovery_attempts >= 3:
        if context.recovery_response_improved is False:
            add(DiagnosticHypothesis.SULFATION, 20, "three_recovery_attempts_without_response")
            add(DiagnosticHypothesis.CAPACITY_LOSS, 20, "three_recovery_attempts_without_response")
            cell_classes.add("recovery_nonresponse")
        elif context.recovery_response_improved is True:
            # Response to recovery is positive contradictory evidence for an irreversible
            # structural fault and stronger support for recoverable sulfation.
            add(DiagnosticHypothesis.SULFATION, 35, "recovery_response_improved")
            scores[DiagnosticHypothesis.CELL_FAULT] = max(
                0, scores[DiagnosticHypothesis.CELL_FAULT] - 20
            )
            reasons[DiagnosticHypothesis.CELL_FAULT].append("counterevidence_recovery_improved")

    if context.dynamic_loop_worsened:
        add(DiagnosticHypothesis.CAPACITY_LOSS, 15, "dynamic_loop_response_worsened")
        # Two-wire loop response also includes cables/contacts, so it simultaneously
        # raises path suspicion rather than pretending the change is battery-only.
        add(DiagnosticHypothesis.CHARGER_PATH, 15, "dynamic_loop_response_is_two_wire")

    if context.charger_path_suspected:
        add(DiagnosticHypothesis.CHARGER_PATH, 45, "charger_or_connection_path_suspected")
        # Do not punish the battery for evidence that points at the charger path.
        scores[DiagnosticHypothesis.CELL_FAULT] = max(
            0, scores[DiagnosticHypothesis.CELL_FAULT] - 15
        )
        reasons[DiagnosticHypothesis.CELL_FAULT].append("counterevidence_charger_path")

    if context.abnormal_thermal_response:
        add(DiagnosticHypothesis.THERMAL_ABNORMALITY, 60, "abnormal_battery_thermal_response")
        add(DiagnosticHypothesis.CELL_FAULT, 20, "thermal_behavior_supports_cell_fault")
        cell_classes.add("thermal")

    if context.external_load_test_failed:
        add(DiagnosticHypothesis.CAPACITY_LOSS, 60, "external_load_test_failed")
        add(DiagnosticHypothesis.CELL_FAULT, 25, "external_load_test_supports_fault")
        cell_classes.add("load_test")

    if context.external_failed_cell_confirmed:
        add(DiagnosticHypothesis.CELL_FAULT, 100, "external_failed_cell_confirmed")
        cell_classes.add("external_confirmation")

    hypothesis_map: Dict[DiagnosticHypothesis, HypothesisEvidence] = {}
    for hypothesis in DiagnosticHypothesis:
        score = _bounded(scores[hypothesis])
        hypothesis_map[hypothesis] = HypothesisEvidence(
            hypothesis=hypothesis,
            score=score,
            level=_level(score),
            reasons=tuple(reasons[hypothesis]),
        )

    cell = hypothesis_map[DiagnosticHypothesis.CELL_FAULT]
    authority = DiagnosticAuthority.ALLOW
    authority_reasons: list[str] = []

    if context.external_failed_cell_confirmed:
        authority = DiagnosticAuthority.BLOCK_AUTOMATIC_HV
        authority_reasons.append("failed_cell_confirmed_externally")
    elif (
        cell.score >= 80
        and len(cell_classes) >= 2
        and (
            "rested_ocv" in cell_classes
            or "persistent_sg" in cell_classes
            or "load_test" in cell_classes
        )
    ):
        authority = DiagnosticAuthority.BLOCK_AUTOMATIC_HV
        authority_reasons.append("multi_signal_cell_fault_high_confidence")
    elif (
        cell.level in {DiagnosticLevel.PROBABLE, DiagnosticLevel.HIGH}
        or (sg is not None and sg.level is DiagnosticLevel.VERIFY)
        or hypothesis_map[DiagnosticHypothesis.THERMAL_ABNORMALITY].level
        in {DiagnosticLevel.PROBABLE, DiagnosticLevel.HIGH}
    ):
        authority = DiagnosticAuthority.VERIFY_BEFORE_HV
        authority_reasons.append("fault_evidence_requires_verification_before_hv")

    # HARD_STOP is intentionally not produced from diagnostic inference. Immediate
    # unsafe U/I/T/protection conditions belong to the independent hard-safety layer.
    return BatteryFaultAssessment(
        hypotheses=hypothesis_map,
        authority=authority,
        authority_reasons=tuple(authority_reasons),
        independent_cell_fault_classes=frozenset(cell_classes),
    )
