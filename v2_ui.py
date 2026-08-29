from __future__ import annotations

import html
from dataclasses import dataclass
from typing import Any, Mapping, Optional

from battery_registry import BatteryRecord
from pb_domain import (
    BatteryChemistry,
    BatteryCondition,
    BatteryIdentity,
    ChargeContext,
    ChargeIntent,
)
from recipe_engine import select_recipe_envelope


INTENT_LABELS = {
    ChargeIntent.NORMAL: "Обычный заряд",
    ChargeIntent.RECOVERY: "Восстановление",
    ChargeIntent.CONDITIONING: "Кондиционирование",
    ChargeIntent.DIAGNOSTIC: "Диагностика",
}

CONDITION_LABELS = {
    BatteryCondition.UNKNOWN: "не определено",
    BatteryCondition.HEALTHY: "исправная",
    BatteryCondition.SULFATED_SUSPECTED: "подозрение на сульфатацию",
    BatteryCondition.DRY_SUSPECTED: "подозрение на высыхание",
    BatteryCondition.REHYDRATED: "после доливки / rehydrated",
    BatteryCondition.OVERWET_SUSPECTED: "возможный перелив",
    BatteryCondition.STRATIFIED_SUSPECTED: "подозрение на стратификацию",
    BatteryCondition.DEGRADED: "деградированная",
}

CHEMISTRY_LABELS = {
    BatteryChemistry.AGM: "AGM",
    BatteryChemistry.EFB: "EFB",
    BatteryChemistry.CA_CA: "Ca/Ca",
    BatteryChemistry.FLOODED: "Flooded",
    BatteryChemistry.CUSTOM: "Custom",
}

PROFILE_TO_CHEMISTRY = {
    "AGM": BatteryChemistry.AGM,
    "EFB": BatteryChemistry.EFB,
    "Ca/Ca": BatteryChemistry.CA_CA,
}

CHEMISTRY_TO_PROFILE = {
    BatteryChemistry.AGM: "AGM",
    BatteryChemistry.EFB: "EFB",
    BatteryChemistry.CA_CA: "Ca/Ca",
    BatteryChemistry.FLOODED: "Ca/Ca",
}

MIX_TARGETS_V = {
    BatteryChemistry.AGM: 16.3,
    BatteryChemistry.EFB: 16.5,
    BatteryChemistry.CA_CA: 16.5,
    BatteryChemistry.FLOODED: 16.5,
}

MIX_LIMIT_HOURS = {
    BatteryChemistry.AGM: 10,
    BatteryChemistry.EFB: 24,
    BatteryChemistry.CA_CA: 20,
    BatteryChemistry.FLOODED: 20,
}


@dataclass(frozen=True)
class ProgramPreview:
    profile: str
    intent: ChargeIntent
    condition: BatteryCondition
    capacity_ah: float
    text: str


def profile_for_chemistry(chemistry: BatteryChemistry) -> Optional[str]:
    return CHEMISTRY_TO_PROFILE.get(chemistry)


def chemistry_for_profile(profile: str) -> BatteryChemistry:
    try:
        return PROFILE_TO_CHEMISTRY[str(profile)]
    except KeyError as exc:
        raise ValueError(f"unsupported V2 profile: {profile}") from exc


def intent_label(intent: ChargeIntent) -> str:
    return INTENT_LABELS[intent]


def condition_label(condition: BatteryCondition) -> str:
    return CONDITION_LABELS[condition]


def battery_button_label(record: BatteryRecord) -> str:
    identity = record.identity
    name = " ".join(part for part in (identity.manufacturer, identity.model) if part).strip()
    if not name:
        name = identity.battery_id
    chem = CHEMISTRY_LABELS[identity.chemistry]
    return f"🔋 {name} · {chem} {identity.nominal_capacity_ah:g} Ah"[:60]


def format_battery_card(record: BatteryRecord) -> str:
    identity = record.identity
    lifecycle = record.lifecycle
    title = " ".join(part for part in (identity.manufacturer, identity.model) if part).strip()
    if not title:
        title = identity.battery_id
    lines = [
        f"<b>{html.escape(title)}</b>",
        f"<code>{html.escape(identity.battery_id)}</code> · "
        f"{CHEMISTRY_LABELS[identity.chemistry]} · {identity.nominal_capacity_ah:g} Ah",
        f"Состояние: <b>{html.escape(condition_label(lifecycle.condition))}</b>",
    ]
    if lifecycle.cycles_since_refill is not None:
        lines.append(f"Циклов после доливки: <b>{lifecycle.cycles_since_refill}</b>")
    if lifecycle.water_added_total_ml > 0:
        lines.append(f"Долито воды: <b>{lifecycle.water_added_total_ml:g} мл</b>")
    metrics = []
    if lifecycle.measured_capacity_ah is not None:
        metrics.append(f"Ёмкость {lifecycle.measured_capacity_ah:g} Ah")
    if lifecycle.cca_a is not None:
        metrics.append(f"CCA {lifecycle.cca_a:g} A")
    if lifecycle.internal_resistance_mohm is not None:
        metrics.append(f"Ri {lifecycle.internal_resistance_mohm:g} mΩ")
    if metrics:
        lines.append(" · ".join(metrics))
    return "\n".join(lines)


def build_program_preview(
    *,
    profile: str,
    capacity_ah: float,
    intent: ChargeIntent,
    condition: BatteryCondition = BatteryCondition.UNKNOWN,
    battery_id: str = "preview",
    expert_high_voltage: bool = False,
) -> ProgramPreview:
    chemistry = chemistry_for_profile(profile)
    identity = BatteryIdentity(
        battery_id=battery_id or "preview",
        chemistry=chemistry,
        nominal_capacity_ah=float(capacity_ah),
    )
    context = ChargeContext(identity=identity, intent=intent, condition=condition)
    envelope = select_recipe_envelope(
        context,
        expert_high_voltage=expert_high_voltage,
    )

    lines = [
        f"<b>Программа заряда · {html.escape(profile)} {capacity_ah:g} Ah</b>",
        f"Цель: <b>{html.escape(intent_label(intent))}</b>",
        f"Состояние АКБ: {html.escape(condition_label(condition))}",
        "",
        "<b>Основной этап</b>",
        f"Напряжение: {MAIN_TARGETS[chemistry]}",
        f"Ограничение тока: до {envelope.main_current_limit_a:g} A",
    ]

    if intent in {ChargeIntent.NORMAL, ChargeIntent.RECOVERY, ChargeIntent.CONDITIONING}:
        mix_v = MIX_TARGETS_V[chemistry]
        qualifier = (
            "Штатная автоматическая цепочка V1-compatible: recovery/Mix включаются только по критериям."
            if intent == ChargeIntent.NORMAL
            else "Высоковольтный этап разрешается только по подтверждённым критериям программы."
        )
        lines.extend(
            [
                "",
                "<b>Высоковольтный этап</b>",
                qualifier,
                f"Mix: до <b>{mix_v:.1f} V</b> · до {envelope.hv_current_limit_a:g} A · контрольное окно {MIX_LIMIT_HOURS[chemistry]} ч",
                "Финиш в CV: Imin → ΔI",
                "Финиш в CC: Vmax → ΔV",
                "После подтверждения Δ: финальная выдержка 2 ч → безопасное ожидание.",
            ]
        )
    else:
        lines.extend(
            [
                "",
                "<b>Высоковольтный этап: запрещён</b>",
                "Diagnostic наблюдает/проверяет состояние без автоматического Recovery/Mix.",
            ]
        )

    lines.extend(
        [
            "",
            f"Ограничение профиля: <b>{envelope.voltage_ceiling_v:.2f} V</b>",
            "Рабочее напряжение корректируется по температуре АКБ только внутри разрешённого диапазона.",
        ]
    )
    return ProgramPreview(
        profile=profile,
        intent=intent,
        condition=condition,
        capacity_ah=float(capacity_ah),
        text="\n".join(lines),
    )


def _fmt(value: Any, digits: int = 2, suffix: str = "") -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "—"
    return f"{number:.{digits}f}{suffix}"


def _duration(seconds: Any) -> str:
    try:
        total = max(0, int(float(seconds)))
    except (TypeError, ValueError):
        return "—"
    hours, rem = divmod(total, 3600)
    minutes = rem // 60
    return f"{hours}ч {minutes:02d}м" if hours else f"{minutes}м"


def format_active_evidence(
    snapshot: Mapping[str, Any],
    *,
    voltage_v: Optional[float] = None,
    current_a: Optional[float] = None,
    temp_c: Optional[float] = None,
) -> str:
    """Detailed controller evidence for the secondary controller-status screen."""

    metrics = dict(snapshot.get("metrics") or {})
    is_cv = bool(snapshot.get("is_cv"))
    is_cc = bool(snapshot.get("is_cc"))
    lines = []

    authority = "V2" if snapshot.get("authoritative") else "резервная legacy-логика"
    intent_raw = str(snapshot.get("intent") or ChargeIntent.RECOVERY.value)
    try:
        intent = ChargeIntent(intent_raw)
        intent_text = INTENT_LABELS[intent]
    except ValueError:
        intent_text = intent_raw
    lines.append(f"Контур: <b>{html.escape(authority)}</b> · {html.escape(intent_text)}")

    if is_cv:
        imin = metrics.get("current_min_a")
        delta = metrics.get("delta_current_from_min_a")
        threshold = metrics.get("reversal_threshold_a")
        age = metrics.get("seconds_since_current_min")
        lines.append("<b>CV · анализ по току</b>")
        lines.append(
            f"Imin {_fmt(imin, 3, ' A')} · ΔI {_fmt(delta, 3, ' A')} / {_fmt(threshold, 3, ' A')} · после Imin {_duration(age)}"
        )
    elif is_cc:
        vmax = metrics.get("voltage_max_v")
        delta_v = metrics.get("delta_voltage_from_max_v")
        threshold_v = metrics.get("voltage_reversal_threshold_v")
        age = metrics.get("seconds_since_voltage_max")
        lines.append("<b>CC · анализ по напряжению</b>")
        lines.append(
            f"Vmax {_fmt(vmax, 3, ' V')} · ΔV {_fmt(delta_v, 3, ' V')} / {_fmt(threshold_v, 3, ' V')} · после Vmax {_duration(age)}"
        )
    else:
        lines.append("Режим регулятора пока не подтверждён")

    trend = metrics.get("d_temp_c_per_min")
    decision = str(snapshot.get("decision") or "continue")
    lines.append(
        f"Температурный тренд {_fmt(trend, 3, ' °C/мин')} · решение <code>{html.escape(decision)}</code>"
    )
    if snapshot.get("finish_hold_started_at") is not None:
        lines.append("Δ подтверждена · <b>финальная выдержка 2 ч</b>")
    if voltage_v is not None or current_a is not None or temp_c is not None:
        lines.append(
            f"Факт: {_fmt(voltage_v, 2, ' V')} · {_fmt(current_a, 2, ' A')} · {_fmt(temp_c, 1, ' °C')}"
        )
    return "\n".join(lines)
