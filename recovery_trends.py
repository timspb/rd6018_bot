from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Optional, Sequence, Tuple

from battery_registry import RecoveryCycleEvidence


class RecoveryStatus(str, Enum):
    INSUFFICIENT_DATA = "insufficient_data"
    IMPROVING = "improving"
    STABLE = "stable"
    REGRESSING = "regressing"


class RecoveryConfidence(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass(frozen=True)
class TrendMetric:
    name: str
    first: float
    last: float
    relative_change: Optional[float]
    score: int
    explanation: str


@dataclass(frozen=True)
class RecoveryTrend:
    status: RecoveryStatus
    confidence: RecoveryConfidence
    score: int
    metrics: Tuple[TrendMetric, ...]
    reasons: Tuple[str, ...]
    cycles_considered: int


def _relative_change(first: float, last: float) -> Optional[float]:
    if first == 0:
        return None
    return (last - first) / abs(first)


def _paired_values(
    cycles: Sequence[RecoveryCycleEvidence],
    attr: str,
) -> Optional[tuple[float, float]]:
    values = [
        float(value)
        for cycle in cycles
        if (value := getattr(cycle, attr)) is not None
    ]
    if len(values) < 2:
        return None
    return values[0], values[-1]


def _metric(
    *,
    name: str,
    pair: tuple[float, float],
    improve_when: str,
    threshold: float,
    weight: int,
    unit: str,
) -> TrendMetric:
    first, last = pair
    relative = _relative_change(first, last)
    score = 0
    direction = "без выраженного изменения"

    if relative is not None:
        improvement = relative if improve_when == "up" else -relative
        if improvement >= threshold:
            score = weight
            direction = "улучшение"
        elif improvement <= -threshold:
            score = -weight
            direction = "ухудшение"

    pct = f"{relative * 100:+.1f}%" if relative is not None else "n/a"
    explanation = (
        f"{name}: {first:.2f}{unit} → {last:.2f}{unit} "
        f"({pct}, {direction})"
    )
    return TrendMetric(
        name=name,
        first=first,
        last=last,
        relative_change=relative,
        score=score,
        explanation=explanation,
    )


def analyze_recovery_trend(
    cycles: Iterable[RecoveryCycleEvidence],
) -> RecoveryTrend:
    items = [cycle for cycle in cycles if cycle.completed_at is not None]
    items.sort(key=lambda c: (c.completed_at or c.started_at, c.started_at))

    if len(items) < 2:
        return RecoveryTrend(
            status=RecoveryStatus.INSUFFICIENT_DATA,
            confidence=RecoveryConfidence.LOW,
            score=0,
            metrics=(),
            reasons=("Нужно минимум два завершённых цикла с сопоставимыми измерениями.",),
            cycles_considered=len(items),
        )

    metrics: list[TrendMetric] = []

    capacity = _paired_values(items, "measured_capacity_ah")
    if capacity:
        metrics.append(
            _metric(
                name="Ёмкость",
                pair=capacity,
                improve_when="up",
                threshold=0.05,
                weight=3,
                unit="Ah",
            )
        )

    cca = _paired_values(items, "cca_a")
    if cca:
        metrics.append(
            _metric(
                name="CCA",
                pair=cca,
                improve_when="up",
                threshold=0.05,
                weight=2,
                unit="A",
            )
        )

    resistance = _paired_values(items, "internal_resistance_mohm")
    if resistance:
        metrics.append(
            _metric(
                name="Ri",
                pair=resistance,
                improve_when="down",
                threshold=0.05,
                weight=2,
                unit="mΩ",
            )
        )

    # Imin is trajectory evidence, not a standalone health metric. Its meaning
    # depends on recipe, wetting state and where the battery is in recovery.
    main_imin = _paired_values(items, "main_imin_a")
    if main_imin:
        first, last = main_imin
        metrics.append(
            TrendMetric(
                name="Main Imin",
                first=first,
                last=last,
                relative_change=_relative_change(first, last),
                score=0,
                explanation=(
                    f"Main Imin: {first:.3f}A → {last:.3f}A "
                    "(evidence only; направление не оценивается как здоровье)"
                ),
            )
        )

    hv_imin = _paired_values(items, "hv_imin_a")
    if hv_imin:
        first, last = hv_imin
        metrics.append(
            TrendMetric(
                name="HV Imin",
                first=first,
                last=last,
                relative_change=_relative_change(first, last),
                score=0,
                explanation=(
                    f"HV Imin: {first:.3f}A → {last:.3f}A "
                    "(evidence only; зависит от режима и гидратации)"
                ),
            )
        )

    score = sum(metric.score for metric in metrics)
    reasons = [metric.explanation for metric in metrics if metric.score != 0]

    latest = items[-1]
    if latest.temp_max_c is not None and latest.temp_max_c >= 40.0:
        score -= 3
        reasons.append(f"Последний цикл достиг {latest.temp_max_c:.1f}°C.")
    if (
        latest.max_dtemp_c_per_min is not None
        and latest.max_dtemp_c_per_min >= 0.20
    ):
        score -= 2
        reasons.append(
            "На последнем цикле зафиксирован быстрый рост температуры "
            f"{latest.max_dtemp_c_per_min:.2f}°C/min."
        )

    scored_metric_count = sum(
        1 for metric in metrics if metric.name in {"Ёмкость", "CCA", "Ri"}
    )
    if scored_metric_count >= 3 and len(items) >= 3:
        confidence = RecoveryConfidence.HIGH
    elif scored_metric_count >= 2:
        confidence = RecoveryConfidence.MEDIUM
    else:
        confidence = RecoveryConfidence.LOW

    if score >= 2:
        status = RecoveryStatus.IMPROVING
    elif score <= -2:
        status = RecoveryStatus.REGRESSING
    else:
        status = RecoveryStatus.STABLE

    if not reasons:
        reasons.append("Объективные метрики не вышли за порог значимого изменения ±5%.")

    return RecoveryTrend(
        status=status,
        confidence=confidence,
        score=score,
        metrics=tuple(metrics),
        reasons=tuple(reasons),
        cycles_considered=len(items),
    )
