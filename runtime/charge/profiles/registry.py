"""Factory/custom recipe registry."""

from __future__ import annotations

from typing import Mapping, Any

from .inheritance import apply_recipe_override
from .recipe import RecipeDTO, ValidatedChargeRecipe, factory_recipe
from .validation import ChargeRecipeValidator


class RecipeRegistry:
    def __init__(self, validator: ChargeRecipeValidator | None = None) -> None:
        self.validator = validator or ChargeRecipeValidator()

    def get_factory_recipe(self, chemistry: str) -> ValidatedChargeRecipe:
        return self.validator.validate(factory_recipe(chemistry))

    def create_custom_profile(self, dto: RecipeDTO) -> ValidatedChargeRecipe:
        self.validator.validate_dto(dto)
        return self.validator.validate(apply_recipe_override(self.get_factory_recipe(dto.chemistry), dto.overrides))

    def resolve_profile(self, chemistry: str, overrides: Mapping[str, Any] | None = None) -> ValidatedChargeRecipe:
        base = self.get_factory_recipe(chemistry)
        return self.validator.validate(apply_recipe_override(base, overrides or {}))

    def list_profiles(self) -> tuple[str, ...]:
        return ("AGM", "EFB", "CA_CA", "FLOODED", "CUSTOM")
