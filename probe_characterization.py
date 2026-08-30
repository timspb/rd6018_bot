from __future__ import annotations

import json
import math
import statistics
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence, Tuple


@dataclass(frozen=True)
class CharacterizationSample:
    timestamp_s: float
    phase: str
    battery_voltage_v: float
    current_a: float
    configured_current_a: Optional[float] = None
    output_voltage_v: Optional[float] = None
    temp_ext_c: Optional[float] = None
    regulation_mode: str = ""

    def __post_init__(self) -> None:
        if not math.isfinite(float(self.timestamp_s)):
            raise ValueError("timestamp_s must be finite")
        if not self.phase.strip():
            raise ValueError("phase is required")
        for name, value in (
            ("battery_voltage_v", self.battery_voltage_v),
            ("current_a", self.current_a),
        ):
            if not math.isfinite(float(value)):
                raise ValueError(f"{name} must be finite")
        for name, value in (
            ("configured_current_a", self.configured_current_a),
            ("output_voltage_v", self.output_voltage_v),
            ("temp_ext_c", self.temp_ext_c),
        ):
            if value is not None and not math.isfinite(float(value)):
                raise ValueError(f"{name} must be finite when present")


@dataclass(frozen=True)
class SignalStats:
    count: int
    minimum: float
    maximum: float
    median: float
    mean: float
    mad: float
    span: float
    observed_min_step: Optional[float]


@dataclass(frozen=True)
class PhaseCharacterization:
    phase: str
    count: int
    duration_s: float
    cadence_median_s: Optional[float]
    cadence_min_s: Optional[float]
    cadence_max_s: Optional[float]
    battery_voltage: SignalStats
    current: SignalStats
    configured_current: Optional[SignalStats]
    output_voltage: Optional[SignalStats]
    output_minus_battery_voltage: Optional[SignalStats]
    temp_ext: Optional[SignalStats]
    regulation_modes: Tuple[str, ...]


@dataclass(frozen=True)
class StepCharacterization:
    baseline_phase: str
    stepped_phase: str
    baseline_voltage_median_v: float
    baseline_current_median_a: float
    stepped_voltage_median_v: float
    stepped_current_median_a: float
    delta_voltage_v: float
    delta_current_a: float
    dynamic_loop_mohm: Optional[float]
    stepped_tail_voltage_median_v: float
    stepped_tail_current_median_a: float
    stepped_voltage_deviation_from_tail: Tuple[Tuple[float, float], ...]
    stepped_current_deviation_from_tail: Tuple[Tuple[float, float], ...]


@dataclass(frozen=True)
class ProbeCharacterizationReport:
    phases: Tuple[PhaseCharacterization, ...]
    step: Optional[StepCharacterization]
    warnings: Tuple[str, ...]


def _observed_min_step(values: Sequence[float]) -> Optional[float]:
    unique = sorted(set(float(value) for value in values))
    differences = [b - a for a, b in zip(unique, unique[1:]) if b - a > 0]
    if not differences:
        return None
    return min(differences)


def _signal_stats(values: Sequence[float]) -> SignalStats:
    if not values:
        raise ValueError("signal stats require at least one value")
    numeric = [float(value) for value in values]
    median = float(statistics.median(numeric))
    deviations = [abs(value - median) for value in numeric]
    return SignalStats(
        count=len(numeric),
        minimum=min(numeric),
        maximum=max(numeric),
        median=median,
        mean=float(statistics.fmean(numeric)),
        mad=float(statistics.median(deviations)),
        span=max(numeric) - min(numeric),
        observed_min_step=_observed_min_step(numeric),
    )


def _optional_stats(values: Sequence[Optional[float]]) -> Optional[SignalStats]:
    present = [float(value) for value in values if value is not None]
    return _signal_stats(present) if present else None


def characterize_phase(phase: str, samples: Sequence[CharacterizationSample]) -> PhaseCharacterization:
    ordered = sorted(samples, key=lambda sample: sample.timestamp_s)
    if not ordered:
        raise ValueError(f"phase {phase!r} has no samples")
    timestamps = [sample.timestamp_s for sample in ordered]
    gaps = [later - earlier for earlier, later in zip(timestamps, timestamps[1:]) if later >= earlier]
    output_minus_battery = [
        None if sample.output_voltage_v is None else sample.output_voltage_v - sample.battery_voltage_v
        for sample in ordered
    ]
    return PhaseCharacterization(
        phase=phase,
        count=len(ordered),
        duration_s=max(0.0, timestamps[-1] - timestamps[0]),
        cadence_median_s=(float(statistics.median(gaps)) if gaps else None),
        cadence_min_s=(min(gaps) if gaps else None),
        cadence_max_s=(max(gaps) if gaps else None),
        battery_voltage=_signal_stats([sample.battery_voltage_v for sample in ordered]),
        current=_signal_stats([sample.current_a for sample in ordered]),
        configured_current=_optional_stats([sample.configured_current_a for sample in ordered]),
        output_voltage=_optional_stats([sample.output_voltage_v for sample in ordered]),
        output_minus_battery_voltage=_optional_stats(output_minus_battery),
        temp_ext=_optional_stats([sample.temp_ext_c for sample in ordered]),
        regulation_modes=tuple(sorted({sample.regulation_mode.strip().lower() for sample in ordered if sample.regulation_mode.strip()})),
    )


def characterize_step(
    baseline_samples: Sequence[CharacterizationSample],
    stepped_samples: Sequence[CharacterizationSample],
    *,
    tail_count: int = 3,
) -> StepCharacterization:
    if not baseline_samples or not stepped_samples:
        raise ValueError("baseline and stepped samples are required")
    if tail_count < 1:
        raise ValueError("tail_count must be >=1")
    baseline = sorted(baseline_samples, key=lambda sample: sample.timestamp_s)
    stepped = sorted(stepped_samples, key=lambda sample: sample.timestamp_s)
    baseline_v = float(statistics.median(sample.battery_voltage_v for sample in baseline))
    baseline_i = float(statistics.median(sample.current_a for sample in baseline))
    stepped_v = float(statistics.median(sample.battery_voltage_v for sample in stepped))
    stepped_i = float(statistics.median(sample.current_a for sample in stepped))
    delta_v = stepped_v - baseline_v
    delta_i = stepped_i - baseline_i
    dynamic_loop_mohm = None if abs(delta_i) < 1e-12 else (delta_v / delta_i) * 1000.0

    tail = stepped[-min(len(stepped), int(tail_count)):]
    tail_v = float(statistics.median(sample.battery_voltage_v for sample in tail))
    tail_i = float(statistics.median(sample.current_a for sample in tail))
    t0 = stepped[0].timestamp_s
    return StepCharacterization(
        baseline_phase=baseline[0].phase,
        stepped_phase=stepped[0].phase,
        baseline_voltage_median_v=baseline_v,
        baseline_current_median_a=baseline_i,
        stepped_voltage_median_v=stepped_v,
        stepped_current_median_a=stepped_i,
        delta_voltage_v=delta_v,
        delta_current_a=delta_i,
        dynamic_loop_mohm=dynamic_loop_mohm,
        stepped_tail_voltage_median_v=tail_v,
        stepped_tail_current_median_a=tail_i,
        stepped_voltage_deviation_from_tail=tuple(
            (sample.timestamp_s - t0, sample.battery_voltage_v - tail_v) for sample in stepped
        ),
        stepped_current_deviation_from_tail=tuple(
            (sample.timestamp_s - t0, sample.current_a - tail_i) for sample in stepped
        ),
    )


def characterize_probe_samples(
    samples: Iterable[CharacterizationSample],
    *,
    baseline_phase: str = "baseline",
    stepped_phase: str = "stepped",
    tail_count: int = 3,
) -> ProbeCharacterizationReport:
    sample_list = list(samples)
    if not sample_list:
        raise ValueError("at least one characterization sample is required")
    by_phase: Dict[str, list[CharacterizationSample]] = {}
    for sample in sample_list:
        by_phase.setdefault(sample.phase, []).append(sample)
    phases = tuple(
        characterize_phase(phase, by_phase[phase])
        for phase in sorted(by_phase)
    )

    warnings = []
    step: Optional[StepCharacterization] = None
    if baseline_phase in by_phase and stepped_phase in by_phase:
        step = characterize_step(
            by_phase[baseline_phase],
            by_phase[stepped_phase],
            tail_count=tail_count,
        )
        if step.delta_current_a >= 0:
            warnings.append("step_did_not_reduce_measured_current")
    else:
        warnings.append("baseline_or_stepped_phase_missing")

    # V_OUT-V_BAT is deliberately descriptive only. The RD6018 internal red/green
    # topology is not proven well enough to assign cable/contact resistance meaning.
    if any(phase.output_minus_battery_voltage is not None for phase in phases):
        warnings.append("output_minus_battery_voltage_is_descriptive_not_resistance")

    return ProbeCharacterizationReport(
        phases=phases,
        step=step,
        warnings=tuple(warnings),
    )


def sample_from_mapping(payload: Mapping[str, Any]) -> CharacterizationSample:
    return CharacterizationSample(
        timestamp_s=float(payload["timestamp_s"]),
        phase=str(payload["phase"]),
        battery_voltage_v=float(payload["battery_voltage_v"]),
        current_a=float(payload["current_a"]),
        configured_current_a=(
            None if payload.get("configured_current_a") is None else float(payload["configured_current_a"])
        ),
        output_voltage_v=(
            None if payload.get("output_voltage_v") is None else float(payload["output_voltage_v"])
        ),
        temp_ext_c=(None if payload.get("temp_ext_c") is None else float(payload["temp_ext_c"])),
        regulation_mode=str(payload.get("regulation_mode") or ""),
    )


def load_characterization_jsonl(text: str) -> Tuple[CharacterizationSample, ...]:
    samples = []
    for line_number, raw_line in enumerate(str(text).splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"line {line_number}: invalid JSON: {exc}") from exc
        if not isinstance(payload, Mapping):
            raise ValueError(f"line {line_number}: sample must be a JSON object")
        try:
            samples.append(sample_from_mapping(payload))
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"line {line_number}: invalid sample: {exc}") from exc
    return tuple(samples)


def _signal_to_mapping(stats: Optional[SignalStats]) -> Optional[Dict[str, Any]]:
    if stats is None:
        return None
    return {
        "count": stats.count,
        "minimum": stats.minimum,
        "maximum": stats.maximum,
        "median": stats.median,
        "mean": stats.mean,
        "mad": stats.mad,
        "span": stats.span,
        "observed_min_step": stats.observed_min_step,
    }


def characterization_to_mapping(report: ProbeCharacterizationReport) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "warnings": list(report.warnings),
        "phases": [],
        "step": None,
    }
    for phase in report.phases:
        result["phases"].append(
            {
                "phase": phase.phase,
                "count": phase.count,
                "duration_s": phase.duration_s,
                "cadence_median_s": phase.cadence_median_s,
                "cadence_min_s": phase.cadence_min_s,
                "cadence_max_s": phase.cadence_max_s,
                "battery_voltage": _signal_to_mapping(phase.battery_voltage),
                "current": _signal_to_mapping(phase.current),
                "configured_current": _signal_to_mapping(phase.configured_current),
                "output_voltage": _signal_to_mapping(phase.output_voltage),
                "output_minus_battery_voltage": _signal_to_mapping(phase.output_minus_battery_voltage),
                "temp_ext": _signal_to_mapping(phase.temp_ext),
                "regulation_modes": list(phase.regulation_modes),
            }
        )
    if report.step is not None:
        step = report.step
        result["step"] = {
            "baseline_phase": step.baseline_phase,
            "stepped_phase": step.stepped_phase,
            "baseline_voltage_median_v": step.baseline_voltage_median_v,
            "baseline_current_median_a": step.baseline_current_median_a,
            "stepped_voltage_median_v": step.stepped_voltage_median_v,
            "stepped_current_median_a": step.stepped_current_median_a,
            "delta_voltage_v": step.delta_voltage_v,
            "delta_current_a": step.delta_current_a,
            "dynamic_loop_mohm": step.dynamic_loop_mohm,
            "stepped_tail_voltage_median_v": step.stepped_tail_voltage_median_v,
            "stepped_tail_current_median_a": step.stepped_tail_current_median_a,
            "stepped_voltage_deviation_from_tail": [list(item) for item in step.stepped_voltage_deviation_from_tail],
            "stepped_current_deviation_from_tail": [list(item) for item in step.stepped_current_deviation_from_tail],
        }
    return result
