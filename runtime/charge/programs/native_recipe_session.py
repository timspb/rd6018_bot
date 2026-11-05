"""Snapshot a versioned native recipe for one AUTO charging session.

Read-only selection. This does not apply dynamic settings to stage owners or
authorize START. Snapshot values are immutable across later library edits.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Any

from .native_recipe_catalog import get_native_recipe
from .native_recipe_draft import NativeRecipeDraft, validate_native_draft
from .native_recipe_draft_library import NativeRecipeDraftLibrary


@dataclass(frozen=True)
class NativeRecipeSessionSelection:
    name: str
    version: int
    base_recipe_id: str
    profile: str
    intent: str
    overrides: tuple[tuple[str, float | int], ...]
    content_sha256: str

    def to_document(self) -> dict:
        return {"name": self.name, "version": self.version,
                "base_recipe_id": self.base_recipe_id, "profile": self.profile,
                "intent": self.intent, "overrides": dict(self.overrides),
                "content_sha256": self.content_sha256}

    def _payload(self) -> dict:
        return {"base_recipe_id": self.base_recipe_id,
                "name": self.name, "version": self.version,
                "overrides": dict(self.overrides)}

    @staticmethod
    def from_document(document: dict) -> "NativeRecipeSessionSelection":
        if not isinstance(document, dict) or set(document) != {
            "name", "version", "base_recipe_id", "profile", "intent",
            "overrides", "content_sha256",
        }:
            raise ValueError("invalid pinned native recipe session")
        if (not isinstance(document["name"], str)
                or type(document["version"]) is not int
                or document["version"] < 1):
            raise ValueError("invalid pinned native recipe identity")
        draft = validate_native_draft({
            "schema": 1, "execution_kind": "native_authority",
            "base_recipe_id": document["base_recipe_id"],
            "overrides": document["overrides"],
        })
        require_supported_native_execution(draft)
        entry = get_native_recipe(draft.base_recipe_id)
        if entry.profile != document["profile"] or entry.intent != document["intent"]:
            raise ValueError("native recipe profile/intent mismatch")
        selection = NativeRecipeSessionSelection(
            name=document["name"], version=document["version"],
            base_recipe_id=entry.recipe_id, profile=entry.profile,
            intent=entry.intent, overrides=draft.overrides,
            content_sha256=document["content_sha256"],
        )
        if selection.content_sha256 != _digest(selection._payload()):
            raise ValueError("native recipe pinned content was changed")
        return selection


def _digest(payload: dict) -> str:
    return sha256(json.dumps(payload, sort_keys=True, allow_nan=False,
                             separators=(",", ":")).encode("utf-8")).hexdigest()


def require_supported_native_execution(draft: NativeRecipeDraft) -> None:
    """Never accept saved options that the current stage owners would ignore."""
    entry = get_native_recipe(draft.base_recipe_id)
    allowed = {"charge.main.current_c_rate", "charge.mix.current_c_rate"}
    if entry.intent != "diagnostic":
        allowed.update({
            "charge.safe_wait.maximum_hours",
            "charge.safe_wait.target_margin_v",
            "charge.mix.finish_hold_hours",
            "charge.desulfation.duration_hours",
            "charge.desulfation.base_voltage_v",
            "charge.desulfation.current_c_rate",
        })
    voltage_keys = {
        "Ca/Ca": ("charge.main.ca_voltage_v", "charge.mix.ca_voltage_v"),
        "EFB": ("charge.main.efb_voltage_v", "charge.mix.efb_voltage_v"),
        "AGM": (None, "charge.mix.agm_voltage_v"),
    }[entry.profile]
    allowed.update(key for key in voltage_keys if key is not None)
    if entry.intent == "diagnostic":
        allowed = {key for key in allowed if not key.startswith("charge.mix.")}
    allowed.update({"charge.main.fallback_hours"})
    if entry.profile == "AGM":
        allowed.update({
            "charge.main.agm_tail_hold_hours",
            "charge.main.agm_max_recovery_attempts",
            "charge.main.agm_timeout_tail_current_a",
        })
    else:
        allowed.update({
            "charge.main.standard_tail_hold_hours",
            "charge.main.standard_max_recovery_attempts",
        })
    if entry.profile == "EFB" and entry.intent in {"recovery", "conditioning"}:
        from runtime.charge.evidence.recovery_plateau_variables import ALL
        allowed.update(spec.key for spec in ALL)
    overrides = dict(draft.overrides)
    if "charge.recovery_plateau.enabled" in overrides:
        if overrides["charge.recovery_plateau.enabled"] == 1:
            from runtime.charge.evidence.recovery_plateau_variables import (
                MIN_WINDOW_MINUTES, MAX_WINDOW_MINUTES, STRONG_DROP_A,
                WEAK_DROP_A, END_SEGMENT_MINUTES,
            )
            from runtime.charge.evidence.recovery_plateau_policy import PlateauRecipe
            PlateauRecipe(
                min_window_minutes=overrides.get(MIN_WINDOW_MINUTES.key, MIN_WINDOW_MINUTES.default),
                max_window_minutes=overrides.get(MAX_WINDOW_MINUTES.key, MAX_WINDOW_MINUTES.default),
                end_segment_minutes=overrides.get(END_SEGMENT_MINUTES.key, END_SEGMENT_MINUTES.default),
                strong_plateau_drop_a=overrides.get(STRONG_DROP_A.key, STRONG_DROP_A.default),
                weak_plateau_drop_a=overrides.get(WEAK_DROP_A.key, WEAK_DROP_A.default),
            )
    unsupported = set(overrides) - allowed
    if unsupported:
        raise ValueError(
            "native recipe parameters are not yet wired to production: "
            + ", ".join(sorted(unsupported))
        )
    if overrides.get("charge.main.current_c_rate", 0.0) > 0.10:
        raise ValueError("native MAIN current must not exceed 0.1C")


def select_native_recipe_version(
    library: NativeRecipeDraftLibrary,
    name: str, version: int, *, profile: str, intent: Any,
) -> NativeRecipeSessionSelection:
    draft: NativeRecipeDraft = library.load(name, version)
    require_supported_native_execution(draft)
    entry = get_native_recipe(draft.base_recipe_id)
    intent_name = str(getattr(intent, "value", intent)).lower()
    if profile != entry.profile or intent_name != entry.intent:
        raise ValueError("selected recipe does not match requested charge profile/intent")
    payload = {"name": name, "version": version,
               "base_recipe_id": entry.recipe_id,
               "overrides": dict(draft.overrides)}
    return NativeRecipeSessionSelection(
        name=name, version=version, base_recipe_id=entry.recipe_id,
        profile=entry.profile, intent=entry.intent, overrides=draft.overrides,
        content_sha256=_digest(payload),
    )


# The canonical session document has a single optional native recipe binding.
# It never stores an activation grant or authorizes a hardware command.
SESSION_KEY = "native_recipe_selection_v1"


def native_selection_for_session(host: Any, *, profile: str, intent: Any):
    """Ensure the pinned copy can only belong to the current profile/intent."""
    selection = getattr(host, "_native_recipe_session_selection", None)
    if selection is None:
        return None
    if not isinstance(selection, NativeRecipeSessionSelection):
        raise ValueError("invalid native recipe session selection")
    checked = NativeRecipeSessionSelection.from_document(selection.to_document())
    intent_name = str(getattr(intent, "value", intent)).lower()
    if checked.profile != profile or checked.intent != intent_name:
        raise ValueError("native recipe selection belongs to a different session")
    return checked


def restore_native_selection(document: dict, *, profile: str, intent: Any):
    """Validate optional persisted binding before restoring controller state."""
    if SESSION_KEY not in document:
        return None
    selection = NativeRecipeSessionSelection.from_document(document[SESSION_KEY])
    intent_name = str(getattr(intent, "value", intent)).lower()
    if selection.profile != profile or selection.intent != intent_name:
        raise ValueError("native recipe persisted session mismatch")
    return selection


def native_target_parameters(host: Any, stage: str) -> dict[str, float]:
    """Return optional pinned MAIN/MIX target inputs for canonical owners.

    The immutable library snapshot is validated against the active session at
    each use. Other stage parameters remain at their established defaults.
    Target compensation, Guard ratchet and safety envelope are not bypassed.
    """
    selection = native_selection_for_session(
        host, profile=getattr(host, "battery_type", None),
        intent=getattr(host, "_v2_intent", None),
    )
    if selection is None:
        return {}
    values = dict(selection.overrides)
    profile = selection.profile
    if stage == "SAFE_WAIT":
        return {
            argument: float(values[key])
            for key, argument in (
                ("charge.safe_wait.maximum_hours", "max_hours"),
                ("charge.safe_wait.target_margin_v", "target_margin_v"),
            )
            if key in values
        }
    if stage == "DESULFATION":
        return {
            argument: float(values[key])
            for key, argument in (
                ("charge.desulfation.base_voltage_v", "base_voltage_v"),
                ("charge.desulfation.current_c_rate", "current_c_rate"),
                ("charge.desulfation.duration_hours", "duration_hours"),
            )
            if key in values
        }
    if stage == "MAIN_POLICY":
        tail = ("charge.main.agm_tail_hold_hours" if profile == "AGM"
                else "charge.main.standard_tail_hold_hours")
        budget = ("charge.main.agm_max_recovery_attempts" if profile == "AGM"
                  else "charge.main.standard_max_recovery_attempts")
        result = {}
        for key, field in (
            ("charge.main.fallback_hours", "fallback_hours"),
            (tail, "tail_hold_hours"),
            (budget, "max_recovery_attempts"),
        ):
            if key in values:
                result[field] = int(values[key]) if field == "max_recovery_attempts" else float(values[key])
        if profile == "AGM" and "charge.main.agm_timeout_tail_current_a" in values:
            result["agm_timeout_tail_current_a"] = float(
                values["charge.main.agm_timeout_tail_current_a"]
            )
        if profile == "EFB" and selection.intent in {"recovery", "conditioning"}:
            for key, field in (
                ("charge.recovery_plateau.enabled", "adaptive_plateau_enabled"),
                ("charge.recovery_plateau.min_window_minutes", "min_window_minutes"),
                ("charge.recovery_plateau.max_window_minutes", "max_window_minutes"),
                ("charge.recovery_plateau.strong_plateau_drop_a", "strong_plateau_drop_a"),
                ("charge.recovery_plateau.weak_plateau_drop_a", "weak_plateau_drop_a"),
                ("charge.recovery_plateau.end_segment_minutes", "end_segment_minutes"),
            ):
                if key in values:
                    result[field] = values[key]
        return result
    if stage == "MAIN":
        name = {"Ca/Ca": "charge.main.ca_voltage_v",
                "EFB": "charge.main.efb_voltage_v"}.get(profile)
        result = {}
        if name and name in values:
            result["base_voltage_v"] = float(values[name])
        if "charge.main.current_c_rate" in values:
            result["current_c_rate"] = float(values["charge.main.current_c_rate"])
        return result
    if stage == "MIX_POLICY":
        key = "charge.mix.finish_hold_hours"
        return {"finish_hold_hours": float(values[key])} if key in values else {}
    if stage == "MIX":
        name = {"Ca/Ca": "charge.mix.ca_voltage_v",
                "EFB": "charge.mix.efb_voltage_v",
                "AGM": "charge.mix.agm_voltage_v"}[profile]
        result = {}
        if name in values:
            result["base_voltage_v"] = float(values[name])
        if "charge.mix.current_c_rate" in values:
            result["current_c_rate"] = float(values["charge.mix.current_c_rate"])
        return result
    raise ValueError("unsupported native target stage")
