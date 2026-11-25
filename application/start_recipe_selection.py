"""Resolve validated recipe selections for the existing START transaction.

This module selects immutable recipe data only. Physical START authority and
recipe execution remain with the existing transaction and execution owners.
"""
from __future__ import annotations

from typing import Any


def resolve_user_step_recipe(app: Any, pending: Any) -> Any | None:
    """Load and preflight a user recipe, preserving START's first-SET rule."""
    if getattr(pending, "recipe_id", None) is None:
        return None
    catalog = app._user_recipe_catalog
    selected = catalog.library.load(
        str(pending.recipe_id), int(pending.recipe_version)
    )
    from runtime.charge.programs.recipe_preflight import inspect_recipe
    report = inspect_recipe(selected)
    if not report.admissible_structure:
        raise ValueError("; ".join(report.problems))
    if selected.steps[0]["action"] != "set":
        raise ValueError(
            "Для START первый шаг пользовательского рецепта должен быть SET. "
            "Черновик OFF не запускается и не включает Output."
        )
    return selected


def resolve_native_recipe_copy(
    app: Any, pending: Any, selected_recipe: Any | None,
) -> Any | None:
    """Select the immutable native copy, excluding simultaneous step recipes."""
    selected_native = None
    native_name = getattr(pending, "native_recipe_name", None)
    if native_name is not None:
        if selected_recipe is not None:
            raise ValueError("native and user step recipes are mutually exclusive")
        from runtime.charge.programs.native_recipe_draft_library import NativeRecipeDraftLibrary
        from runtime.charge.programs.native_recipe_session import select_native_recipe_version
        catalog = app._user_recipe_catalog
        library = NativeRecipeDraftLibrary(
            catalog.library.root.parent / "native_recipe_drafts")
        selected_native = select_native_recipe_version(
            library, str(native_name),
            int(getattr(pending, "native_recipe_version")),
            profile=pending.profile, intent=pending.intent,
        )

    return selected_native
