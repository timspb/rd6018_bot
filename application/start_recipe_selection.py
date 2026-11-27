"""Resolve a user recipe for the existing transactional START owner.

Selection is read-only and deterministic for the requested immutable version.
It does not create a runner, persist session state, or authorize physical START.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


@dataclass(frozen=True)
class StartRecipeSelections:
    """The immutable user/native choices admitted for one profile START."""

    selected_recipe: Any = None
    selected_native: Any = None


@dataclass(frozen=True)
class StartRecipeSelectionFailure:
    """Expected selection rejection, retaining its existing response variant."""

    kind: Literal["user", "native"]
    error: Exception


def resolve_start_recipe_selections(*, app: Any, pending: Any
                                    ) -> StartRecipeSelections | StartRecipeSelectionFailure:
    """Resolve both pinned choices in their established order, before START."""
    selected_recipe = None
    if getattr(pending, "recipe_id", None) is not None:
        try:
            catalog = app._user_recipe_catalog
            selected_recipe = select_user_recipe_for_start(
                catalog=catalog, recipe_id=str(pending.recipe_id),
                version=int(pending.recipe_version),
            )
        except (AttributeError, TypeError, ValueError, OSError) as exc:
            return StartRecipeSelectionFailure("user", exc)

    selected_native = None
    native_name = getattr(pending, "native_recipe_name", None)
    if native_name is not None:
        try:
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
        except (AttributeError, TypeError, ValueError, KeyError, OSError) as exc:
            return StartRecipeSelectionFailure("native", exc)

    return StartRecipeSelections(selected_recipe, selected_native)

def select_user_recipe_for_start(*, catalog: Any, recipe_id: str,
                                 version: int) -> Any:
    """Load and validate the selected immutable recipe before START.

    Profile START enables Output using the first SET transactionally, so a
    user recipe selected for that route must begin with SET. OFF/WAIT-first
    recipes remain available to their existing non-START workflows.
    """
    recipe = catalog.library.load(str(recipe_id), int(version))
    from runtime.charge.programs.recipe_preflight import inspect_recipe
    report = inspect_recipe(recipe)
    if not report.admissible_structure:
        raise ValueError("; ".join(report.problems))
    if recipe.steps[0]["action"] != "set":
        raise ValueError(
            "Для START первый шаг пользовательского рецепта должен быть SET. "
            "Черновик OFF не запускается и не включает Output."
        )
    return recipe


__all__ = [
    "StartRecipeSelectionFailure", "StartRecipeSelections",
    "resolve_start_recipe_selections", "select_user_recipe_for_start",
]
