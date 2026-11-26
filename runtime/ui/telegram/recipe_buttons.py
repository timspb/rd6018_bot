"""Read-only inline keyboard browser for user recipes."""
from __future__ import annotations

from runtime.charge.programs.recipe_catalog import RecipeCatalog
from runtime.charge.programs.native_recipe_draft_library import NativeRecipeDraftLibrary
from runtime.ui.telegram.native_draft_buttons import install_native_draft_buttons
from runtime.ui.telegram.native_recipe_catalog_buttons import install_native_recipe_catalog_buttons
from runtime.ui.telegram.user_recipe_browser_buttons import install_user_recipe_browser_buttons
from runtime.ui.telegram.step_recipe_editor_buttons import (
    editor_page, install_step_recipe_editor_buttons,
)
from runtime.ui.telegram.recipe_menu_view import (
    catalog_markup, native_recipe_markup, recipe_history_markup, recipe_markup,
)
from runtime.ui.telegram.start_recipe_selection_buttons import (
    _preview_keyboard,
    _recipe_preview_keyboard,
    install_start_recipe_selection_routes,
)


def install_recipe_buttons(app, *, catalog: RecipeCatalog,
                           native_drafts: NativeRecipeDraftLibrary | None = None) -> None:
    if getattr(app, "_recipe_buttons_installed", False):
        return
    if native_drafts is None:
        native_drafts = NativeRecipeDraftLibrary(catalog.library.root.parent / "native_recipe_drafts")

    install_native_draft_buttons(app, native_drafts)

    install_native_recipe_catalog_buttons(app)

    install_user_recipe_browser_buttons(app, catalog)

    install_step_recipe_editor_buttons(app, catalog)

    app._recipe_buttons_installed = True
