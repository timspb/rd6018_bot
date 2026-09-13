"""Validation boundary for factory recipes and user overrides."""

from __future__ import annotations

from dataclasses import fields

from .recipe import RecipeDTO, ValidatedChargeRecipe


class RecipeValidationError(ValueError):
    pass


class ChargeRecipeValidator:
    REQUIRED = {"chemistry", "overrides"}

    def validate_dto(self, dto: RecipeDTO) -> None:
        if not dto.chemistry.strip():
            raise RecipeValidationError("chemistry is required")
        if not isinstance(dto.overrides, dict):
            raise RecipeValidationError("overrides must be a mapping")
        if dto.chemistry.strip().upper() == "CUSTOM" and not dto.overrides:
            raise RecipeValidationError("CUSTOM requires explicit recipe overrides")

    def validate(self, recipe: ValidatedChargeRecipe) -> ValidatedChargeRecipe:
        if not recipe.chemistry:
            raise RecipeValidationError("chemistry is required")
        if recipe.recipe.main.config.target_voltage <= 0:
            raise RecipeValidationError("main target voltage must be positive")
        return recipe
