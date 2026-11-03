"""Validated draft settings for a native dynamic charge recipe.

A draft never grants charging authority and never alters the production
VariableSpec defaults. Activation belongs to the existing session owner.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Mapping

from runtime.config.variable_spec import OverridePolicy
from .native_recipe_catalog import get_native_recipe
from .native_recipe_parameters import native_recipe_parameters


@dataclass(frozen=True)
class NativeRecipeDraft:
    base_recipe_id: str
    overrides: tuple[tuple[str, float | int], ...]
    schema: int = 1

    def as_document(self) -> dict:
        return {
            "schema": self.schema,
            "base_recipe_id": self.base_recipe_id,
            "overrides": dict(self.overrides),
            "execution_kind": "native_authority",
        }


def validate_native_draft(document: Mapping[str, object]) -> NativeRecipeDraft:
    if not isinstance(document, Mapping):
        raise ValueError("native recipe document must be an object")
    if set(document) != {"schema", "base_recipe_id", "execution_kind", "overrides"}:
        raise ValueError("unknown or missing native recipe document fields")
    if type(document["schema"]) is not int or document["schema"] != 1:
        raise ValueError("unsupported native recipe draft schema")
    if document["execution_kind"] != "native_authority":
        raise ValueError("invalid native recipe execution kind")
    recipe_id = document["base_recipe_id"]
    if not isinstance(recipe_id, str):
        raise ValueError("invalid native recipe id")
    get_native_recipe(recipe_id)
    raw = document["overrides"]
    if not isinstance(raw, Mapping):
        raise ValueError("overrides must be a mapping")
    allowed = {spec.key: spec for spec in native_recipe_parameters(recipe_id)
               if spec.override_policy == OverridePolicy.CONFIG_FILE}
    normalized = []
    for key, value in raw.items():
        if key not in allowed:
            raise ValueError(f"unknown or non-editable native parameter: {key}")
        spec = allowed[key]
        if type(value) is not spec.value_type:
            raise ValueError(f"{key}: expected {spec.value_type.__name__}")
        if not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"{key}: value must be finite")
        if (spec.minimum is not None and value < spec.minimum or
                spec.maximum is not None and value > spec.maximum):
            raise ValueError(f"{key}: outside declared range")
        normalized.append((key, value))
    return NativeRecipeDraft(recipe_id, tuple(sorted(normalized)))
