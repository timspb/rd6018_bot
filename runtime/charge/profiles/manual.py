"""Configuration model for the staged operator Manual profile."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import yaml

from charge_logic import MAX_STAGE_CURRENT
from config import MAX_MANUAL_VOLTAGE


def _required_number(data: Mapping[str, Any], name: str, *, minimum: float = 0.0) -> float:
    value = data.get(name)
    if value is None:
        raise ValueError(f"manual profile field is required: {name}")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"manual profile field must be numeric: {name}") from exc
    if result < minimum:
        raise ValueError(f"manual profile field must be >= {minimum}: {name}")
    return result


@dataclass(frozen=True)
class ManualStageProfile:
    voltage_v: float
    current_a: float
    hold_seconds: float
    minimum_current_a: float | None = None
    delta_voltage_v: float | None = None
    delta_current_a: float | None = None
    confirmation_count: int = 1
    confirmation_interval_seconds: float = 0.0

    def __post_init__(self) -> None:
        if not 0.0 < self.voltage_v <= float(MAX_MANUAL_VOLTAGE):
            raise ValueError("manual stage voltage is outside the safety envelope")
        if not 0.0 < self.current_a <= float(MAX_STAGE_CURRENT):
            raise ValueError("manual stage current is outside the safety envelope")
        if self.hold_seconds < 0:
            raise ValueError("manual stage hold must not be negative")
        if self.confirmation_count < 1 or self.confirmation_interval_seconds < 0:
            raise ValueError("manual stage confirmation settings are invalid")
        if self.minimum_current_a is not None and not 0.0 <= self.minimum_current_a <= self.current_a:
            raise ValueError("manual MAIN minimum current is invalid")
        for name, value in (("delta_voltage_v", self.delta_voltage_v), ("delta_current_a", self.delta_current_a)):
            if value is not None and value <= 0:
                raise ValueError(f"manual {name} must be positive")


@dataclass(frozen=True)
class ManualChargeProfile:
    main: ManualStageProfile
    mix: ManualStageProfile
    profile_id: str = "manual"

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any], *, profile_id: str = "manual") -> "ManualChargeProfile":
        root = data.get("manual", data)
        if not isinstance(root, Mapping):
            raise ValueError("manual profile must be a mapping")
        main_raw = root.get("main")
        mix_raw = root.get("mix")
        if not isinstance(main_raw, Mapping) or not isinstance(mix_raw, Mapping):
            raise ValueError("manual profile requires separate main and mix sections")

        def stage(raw: Mapping[str, Any], *, is_main: bool) -> ManualStageProfile:
            return ManualStageProfile(
                voltage_v=_required_number(raw, "voltage_v", minimum=0.01),
                current_a=_required_number(raw, "current_a", minimum=0.01),
                hold_seconds=_required_number(raw, "hold_seconds"),
                minimum_current_a=_required_number(raw, "minimum_current_a") if is_main else None,
                delta_voltage_v=_required_number(raw, "delta_voltage_v", minimum=0.000001) if raw.get("delta_voltage_v") is not None else None,
                delta_current_a=_required_number(raw, "delta_current_a", minimum=0.000001) if raw.get("delta_current_a") is not None else None,
                confirmation_count=int(raw.get("confirmation_count", 1)),
                confirmation_interval_seconds=float(raw.get("confirmation_interval_seconds", 0.0)),
            )

        main_stage = stage(main_raw, is_main=True)
        mix_stage = stage(mix_raw, is_main=False)
        if main_stage.delta_voltage_v is not None or main_stage.delta_current_a is not None:
            raise ValueError("MAIN must not define delta values")
        if mix_stage.delta_voltage_v is None or mix_stage.delta_current_a is None:
            raise ValueError("MIX requires both delta_voltage_v and delta_current_a")
        return cls(main=main_stage, mix=mix_stage, profile_id=profile_id)


def load_manual_profile(path: str | Path) -> ManualChargeProfile:
    with Path(path).open(encoding="utf-8") as handle:
        return ManualChargeProfile.from_mapping(yaml.safe_load(handle) or {})
