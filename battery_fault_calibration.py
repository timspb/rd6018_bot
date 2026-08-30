from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Mapping, Optional, Tuple

from battery_diagnostics import (
    DiagnosticHypothesis,
    DiagnosticLevel,
    SpecificGravityAssessment,
)
from battery_fault_engine import (
    BatteryFaultAssessment,
    BatteryFaultContext,
    DiagnosticAuthority,
    assess_battery_fault,
)


@dataclass(frozen=True)
class FaultCalibrationExpectation:
    authority: Optional[DiagnosticAuthority] = None
    hypothesis_levels: Tuple[Tuple[DiagnosticHypothesis, DiagnosticLevel], ...] = ()

    def level_map(self) -> Dict[DiagnosticHypothesis, DiagnosticLevel]:
        return dict(self.hypothesis_levels)


@dataclass(frozen=True)
class FaultCalibrationCase:
    case_id: str
    context: BatteryFaultContext
    expected: FaultCalibrationExpectation = FaultCalibrationExpectation()
    notes: str = ""


@dataclass(frozen=True)
class FaultCalibrationResult:
    case_id: str
    assessment: BatteryFaultAssessment
    authority_match: Optional[bool]
    unexpected_hv_block: bool
    missed_hv_block: bool
    hypothesis_mismatches: Tuple[str, ...]


@dataclass(frozen=True)
class FaultCalibrationSummary:
    total_cases: int
    authority_labeled_cases: int
    authority_matches: int
    unexpected_hv_blocks: int
    missed_hv_blocks: int
    hypothesis_labeled_checks: int
    hypothesis_level_mismatches: int
    results: Tuple[FaultCalibrationResult, ...]

    @property
    def authority_accuracy(self) -> Optional[float]:
        if self.authority_labeled_cases <= 0:
            return None
        return self.authority_matches / self.authority_labeled_cases

    @property
    def hypothesis_level_accuracy(self) -> Optional[float]:
        if self.hypothesis_labeled_checks <= 0:
            return None
        return 1.0 - self.hypothesis_level_mismatches / self.hypothesis_labeled_checks


def evaluate_fault_case(case: FaultCalibrationCase) -> FaultCalibrationResult:
    assessment = assess_battery_fault(case.context)
    expected_authority = case.expected.authority
    authority_match = (
        None if expected_authority is None else assessment.authority is expected_authority
    )
    unexpected_block = bool(
        expected_authority is not None
        and expected_authority is not DiagnosticAuthority.BLOCK_AUTOMATIC_HV
        and assessment.authority is DiagnosticAuthority.BLOCK_AUTOMATIC_HV
    )
    missed_block = bool(
        expected_authority is DiagnosticAuthority.BLOCK_AUTOMATIC_HV
        and assessment.authority is not DiagnosticAuthority.BLOCK_AUTOMATIC_HV
    )

    mismatches = []
    for hypothesis, expected_level in case.expected.level_map().items():
        actual = assessment.evidence(hypothesis).level
        if actual is not expected_level:
            mismatches.append(
                f"{hypothesis.value}:expected={expected_level.value}:actual={actual.value}"
            )

    return FaultCalibrationResult(
        case_id=case.case_id,
        assessment=assessment,
        authority_match=authority_match,
        unexpected_hv_block=unexpected_block,
        missed_hv_block=missed_block,
        hypothesis_mismatches=tuple(mismatches),
    )


def evaluate_fault_cases(cases: Iterable[FaultCalibrationCase]) -> FaultCalibrationSummary:
    case_list = list(cases)
    results = tuple(evaluate_fault_case(case) for case in case_list)
    authority_labeled = sum(case.expected.authority is not None for case in case_list)
    authority_matches = sum(result.authority_match is True for result in results)
    hypothesis_checks = sum(len(case.expected.hypothesis_levels) for case in case_list)
    mismatch_count = sum(len(result.hypothesis_mismatches) for result in results)
    return FaultCalibrationSummary(
        total_cases=len(case_list),
        authority_labeled_cases=authority_labeled,
        authority_matches=authority_matches,
        unexpected_hv_blocks=sum(result.unexpected_hv_block for result in results),
        missed_hv_blocks=sum(result.missed_hv_block for result in results),
        hypothesis_labeled_checks=hypothesis_checks,
        hypothesis_level_mismatches=mismatch_count,
        results=results,
    )


def _parse_specific_gravity(payload: Optional[Mapping[str, Any]]) -> Optional[SpecificGravityAssessment]:
    if payload is None:
        return None
    return SpecificGravityAssessment(
        valid_cell_count=int(payload.get("valid_cell_count", 0)),
        minimum=(None if payload.get("minimum") is None else float(payload["minimum"])),
        maximum=(None if payload.get("maximum") is None else float(payload["maximum"])),
        median=(None if payload.get("median") is None else float(payload["median"])),
        spread=(None if payload.get("spread") is None else float(payload["spread"])),
        low_outlier_cells=tuple(int(value) for value in payload.get("low_outlier_cells", ())),
        high_outlier_cells=tuple(int(value) for value in payload.get("high_outlier_cells", ())),
        level=DiagnosticLevel(str(payload.get("level", DiagnosticLevel.NORMAL.value))),
        reason=str(payload.get("reason", "calibration_case")),
    )


def context_from_mapping(payload: Mapping[str, Any]) -> BatteryFaultContext:
    values = dict(payload)
    values["specific_gravity"] = _parse_specific_gravity(values.get("specific_gravity"))
    return BatteryFaultContext(**values)


def calibration_case_from_mapping(payload: Mapping[str, Any]) -> FaultCalibrationCase:
    case_id = str(payload.get("case_id") or "").strip()
    if not case_id:
        raise ValueError("case_id is required")
    context_payload = payload.get("context")
    if not isinstance(context_payload, Mapping):
        raise ValueError(f"{case_id}: context object is required")

    expected_payload = payload.get("expected") or {}
    if not isinstance(expected_payload, Mapping):
        raise ValueError(f"{case_id}: expected must be an object")
    authority_raw = expected_payload.get("authority")
    authority = None if authority_raw in {None, ""} else DiagnosticAuthority(str(authority_raw))

    levels_raw = expected_payload.get("hypothesis_levels") or {}
    if not isinstance(levels_raw, Mapping):
        raise ValueError(f"{case_id}: expected.hypothesis_levels must be an object")
    levels = tuple(
        (DiagnosticHypothesis(str(hypothesis)), DiagnosticLevel(str(level)))
        for hypothesis, level in sorted(levels_raw.items(), key=lambda item: str(item[0]))
    )
    return FaultCalibrationCase(
        case_id=case_id,
        context=context_from_mapping(context_payload),
        expected=FaultCalibrationExpectation(authority=authority, hypothesis_levels=levels),
        notes=str(payload.get("notes") or ""),
    )


def load_calibration_jsonl(text: str) -> Tuple[FaultCalibrationCase, ...]:
    cases = []
    for line_number, raw_line in enumerate(str(text).splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"line {line_number}: invalid JSON: {exc}") from exc
        if not isinstance(payload, Mapping):
            raise ValueError(f"line {line_number}: case must be a JSON object")
        cases.append(calibration_case_from_mapping(payload))
    return tuple(cases)


def calibration_summary_to_mapping(summary: FaultCalibrationSummary) -> Dict[str, Any]:
    return {
        "total_cases": summary.total_cases,
        "authority_labeled_cases": summary.authority_labeled_cases,
        "authority_matches": summary.authority_matches,
        "authority_accuracy": summary.authority_accuracy,
        "unexpected_hv_blocks": summary.unexpected_hv_blocks,
        "missed_hv_blocks": summary.missed_hv_blocks,
        "hypothesis_labeled_checks": summary.hypothesis_labeled_checks,
        "hypothesis_level_mismatches": summary.hypothesis_level_mismatches,
        "hypothesis_level_accuracy": summary.hypothesis_level_accuracy,
        "results": [
            {
                "case_id": result.case_id,
                "authority": result.assessment.authority.value,
                "authority_reasons": list(result.assessment.authority_reasons),
                "unexpected_hv_block": result.unexpected_hv_block,
                "missed_hv_block": result.missed_hv_block,
                "hypothesis_mismatches": list(result.hypothesis_mismatches),
                "hypotheses": {
                    hypothesis.value: {
                        "score": evidence.score,
                        "level": evidence.level.value,
                        "reasons": list(evidence.reasons),
                    }
                    for hypothesis, evidence in result.assessment.hypotheses.items()
                },
            }
            for result in summary.results
        ],
    }
