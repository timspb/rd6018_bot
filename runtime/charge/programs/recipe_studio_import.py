"""Offline Recipe Studio admission: reuse canonical recipe library and preflight.

This module never starts a session, imports a device port, or modifies hardware.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .recipe_library import RecipeLibrary
from .recipe_preflight import inspect_recipe
from .recipe_schema import Recipe, parse_recipe


@dataclass(frozen=True)
class StudioAdmission:
    recipe: Recipe
    warnings: tuple[str, ...]
    start_eligible: bool


def inspect_step_document(document: Mapping[str, Any], *,
                          max_voltage_v: float, max_current_a: float) -> StudioAdmission:
    """Revalidate the untrusted PC-exported document with production owners."""
    if not isinstance(document, Mapping) or set(document) != {"id", "version", "steps"}:
        raise ValueError("expected only id, version, steps; visual/native drafts are not executable")
    recipe = parse_recipe(document, max_voltage_v=max_voltage_v,
                          max_current_a=max_current_a)
    report = inspect_recipe(recipe)
    if not report.admissible_structure:
        raise ValueError("; ".join(report.problems))
    return StudioAdmission(
        recipe=recipe,
        warnings=report.warnings,
        # Production START also requires first action SET; OFF-first may still be a draft.
        start_eligible=recipe.steps[0]["action"] == "set",
    )


def publish_step_document(library: RecipeLibrary, document: Mapping[str, Any]) -> StudioAdmission:
    """Save immutable next revision; disallow stale, skipped, or archived versions."""
    admission = inspect_step_document(
        document,
        max_voltage_v=library.max_voltage_v,
        max_current_a=library.max_current_a,
    )
    recipe = admission.recipe
    versions = library.versions(recipe.recipe_id)
    if recipe.version != (versions[-1] + 1 if versions else 1):
        raise ValueError("stale/skipped recipe version; reopen latest and retry")
    if (library.root / recipe.recipe_id / ".archived").exists():
        raise ValueError("recipe is archived; it cannot receive new versions")
    # Keep exact existing RecipeLibrary atomic, fsync + no-overwrite save contract.
    saved = library.save({
        "id": recipe.recipe_id,
        "version": recipe.version,
        "steps": list(recipe.steps),
    })
    return StudioAdmission(saved, admission.warnings, admission.start_eligible)

@dataclass(frozen=True)
class NativeStudioAdmission:
    name: str
    version: int
    draft: "NativeRecipeDraft"


def inspect_native_document(document: Mapping[str, Any]) -> NativeStudioAdmission:
    """Validate native draft against typed parameters and supported runtime subset."""
    from .native_recipe_draft import validate_native_draft
    from .native_recipe_session import require_supported_native_execution
    from .native_recipe_draft_library import _valid_id
    if not isinstance(document, Mapping) or set(document) != {"name", "version", "draft"}:
        raise ValueError("expected only name, version, draft for native recipe")
    name, version = document["name"], document["version"]
    if not _valid_id(name) or type(version) is not int or version < 1:
        raise ValueError("invalid native draft name or version")
    draft = validate_native_draft(document["draft"])
    require_supported_native_execution(draft)
    return NativeStudioAdmission(name, version, draft)


def publish_native_document(library: "NativeRecipeDraftLibrary",
                            document: Mapping[str, Any]) -> NativeStudioAdmission:
    """Reuse immutable native draft library; never activate a charge session."""
    admission = inspect_native_document(document)
    saved = library.save(admission.name, admission.version, admission.draft.as_document())
    return NativeStudioAdmission(admission.name, admission.version, saved)
