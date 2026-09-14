"""Configuration model for the staged operator Manual profile."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
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
    hold_hours: float
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
        if self.hold_hours < 0:
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
                hold_hours=_required_number(raw, "hold_hours"),
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


def load_manual_profile(path: str | Path, *, battery_id: str | None = None) -> ManualChargeProfile:
    with Path(path).open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if battery_id:
        root = data.get("manual", data)
        overrides = root.get("profiles", {}) if isinstance(root, Mapping) else {}
        selected = overrides.get(battery_id) if isinstance(overrides, Mapping) else None
        if isinstance(selected, Mapping):
            data = {"manual": selected}
    return ManualChargeProfile.from_mapping(data, profile_id=battery_id or "manual")


def has_manual_profile(path: str | Path, battery_id: str) -> bool:
    with Path(path).open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    root = data.get("manual", data)
    profiles = root.get("profiles", {}) if isinstance(root, Mapping) else {}
    return isinstance(profiles, Mapping) and isinstance(profiles.get(str(battery_id)), Mapping)


def save_manual_profile(profile: ManualChargeProfile, path: str | Path, *, battery_id: str | None = None) -> None:
    """Atomically persist operator-entered Manual values as configuration data."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    def stage_payload(stage: ManualStageProfile) -> dict[str, Any]:
        values = {
                "voltage_v": stage.voltage_v,
                "current_a": stage.current_a,
                "hold_hours": stage.hold_hours,
                "confirmation_count": stage.confirmation_count,
                "confirmation_interval_seconds": stage.confirmation_interval_seconds,
            }
        if stage.minimum_current_a is not None:
            values["minimum_current_a"] = stage.minimum_current_a
        if stage.delta_voltage_v is not None:
            values["delta_voltage_v"] = stage.delta_voltage_v
        if stage.delta_current_a is not None:
            values["delta_current_a"] = stage.delta_current_a
        return values

    profile_payload = {
        "main": stage_payload(profile.main),
        "mix": stage_payload(profile.mix),
    }
    existing: dict[str, Any] = {}
    if target.exists():
        with target.open(encoding="utf-8") as handle:
            loaded = yaml.safe_load(handle) or {}
        if isinstance(loaded, Mapping):
            existing = dict(loaded)
    manual = dict(existing.get("manual") or {})
    if battery_id:
        profiles = dict(manual.get("profiles") or {})
        profiles[str(battery_id)] = profile_payload
        manual["profiles"] = profiles
    else:
        manual.update(profile_payload)
    payload = {"manual": manual}
    temporary = target.with_suffix(target.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        handle.write("# Настройки ручного маршрута MAIN -> MIX; hold задаётся в часах.\n")
        handle.write("# Manual route configuration MAIN -> MIX; hold is in hours.\n")
        yaml.safe_dump(payload, handle, allow_unicode=True, sort_keys=False)
    os.replace(temporary, target)
