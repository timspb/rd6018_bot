"""Read-only inline keyboard browser for user recipes."""
from __future__ import annotations

from dataclasses import replace
from aiogram import F
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from runtime.charge.programs.recipe_catalog import RecipeCatalog
from runtime.charge.programs.native_recipe_draft_library import NativeRecipeDraftLibrary
from runtime.charge.programs.native_recipe_session import require_supported_native_execution
from runtime.ui.telegram.native_draft_buttons import install_native_draft_buttons
from runtime.ui.telegram.native_recipe_catalog_buttons import install_native_recipe_catalog_buttons
from runtime.ui.telegram.user_recipe_browser_buttons import install_user_recipe_browser_buttons
from runtime.ui.telegram.step_recipe_editor_buttons import (
    editor_page, install_step_recipe_editor_buttons,
)
from runtime.ui.telegram.recipe_menu_view import (
    catalog_markup, native_recipe_markup, recipe_history_markup, recipe_markup,
)
from runtime.charge.programs.recipe_preflight import inspect_recipe
from runtime.ui.telegram.charge import CHARGE_CALLBACK_DATA


def _preview_keyboard(start_callback: str) -> InlineKeyboardMarkup:
    """Build the existing two-row START preview keyboard."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="▶️ Запустить", callback_data=start_callback)],
        [InlineKeyboardButton(text="⬅️ Режимы", callback_data=CHARGE_CALLBACK_DATA)],
    ])


def _recipe_preview_keyboard(app, start_callback: str) -> InlineKeyboardMarkup:
    """Add the selectable user/native recipe choices to the START preview."""
    original = _preview_keyboard(start_callback)
    catalog = getattr(app, "_user_recipe_catalog", None)
    if catalog is None:
        return original
    rows = list(original.inline_keyboard)
    choices = []
    for name in catalog.active_recipes():
        versions = catalog.library.versions(name)
        if not versions:
            continue
        version = versions[-1]
        data = f"v2_recipe_pick:{name}:{version}"
        if len(data.encode("utf-8")) <= 64:
            choices.append(InlineKeyboardButton(
                text=f"Рецепт {name} v{version}", callback_data=data,
            ))
    # Saved native recipe copies reuse the same pending START transaction.
    native_store = NativeRecipeDraftLibrary(
        catalog.library.root.parent / "native_recipe_drafts"
    )
    for name in native_store.list_drafts():
        versions = native_store.versions(name)
        if not versions:
            continue
        version = versions[-1]
        data = f"v2_native_pick:{name}:{version}"
        if len(data.encode("utf-8")) <= 64:
            choices.append(InlineKeyboardButton(
                text=f"Штатная копия {name} v{version}", callback_data=data,
            ))
    if choices:
        rows[1:1] = [[choice] for choice in choices[:24]]
    else:
        rows.insert(1, [InlineKeyboardButton(
            text="Создать рецепт", callback_data="recipes:create",
        )])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def install_start_recipe_selection_routes(
    app,
    *,
    pending_start,
    acknowledge,
    answer,
    preview_keyboard,
) -> None:
    """Register existing recipe choices on the shared pending START state."""

    @app.router.callback_query(F.data.startswith("v2_native_pick:"))
    async def pick_native_recipe_handler(call):
        if not await app._check_chat_and_respond(call):
            return
        user_id = call.from_user.id if call.from_user else 0
        pending = pending_start.get(user_id)
        catalog = getattr(app, "_user_recipe_catalog", None)
        if pending is None or catalog is None:
            await acknowledge(call, "Нет ожидающего START", show_alert=True)
            return
        try:
            _, name, version_text = str(call.data).split(":")
            version = int(version_text)
            library = NativeRecipeDraftLibrary(
                catalog.library.root.parent / "native_recipe_drafts"
            )
            from runtime.charge.programs.native_recipe_session import select_native_recipe_version
            selected = select_native_recipe_version(
                library, name, version, profile=pending.profile, intent=pending.intent,
            )
        except (ValueError, KeyError, OSError, FileNotFoundError) as exc:
            await acknowledge(call, str(exc)[:180], show_alert=True)
            return
        pending_start[user_id] = replace(
            pending, recipe_id=None, recipe_version=None,
            native_recipe_name=name, native_recipe_version=version,
        )
        await acknowledge(call)
        await answer(
            call, f"Выбрана копия {name} v{version} ({selected.profile} · {selected.intent}). "
                  "START применит закреплённую версию.",
            reply_markup=preview_keyboard("v2_battery_start"),
        )

    @app.router.callback_query(F.data.startswith("v2_recipe_pick:"))
    async def pick_recipe_handler(call):
        if not await app._check_chat_and_respond(call):
            return
        user_id = call.from_user.id if call.from_user else 0
        pending = pending_start.get(user_id)
        catalog = getattr(app, "_user_recipe_catalog", None)
        if pending is None or catalog is None:
            await acknowledge(call, "Сначала выберите АКБ и режим", show_alert=True)
            return
        try:
            _, name, version_text = str(call.data).split(":")
            version = int(version_text)
            if name not in catalog.active_recipes():
                raise ValueError("Рецепт архивирован")
            recipe = catalog.library.load(name, version)
            report = inspect_recipe(recipe)
            if not report.admissible_structure:
                raise ValueError("; ".join(report.problems))
        except (ValueError, OSError) as exc:
            await acknowledge(call, str(exc)[:180], show_alert=True)
            return
        pending_start[user_id] = replace(
            pending, recipe_id=name, recipe_version=version,
            native_recipe_name=None, native_recipe_version=None,
        )
        await acknowledge(call)
        await answer(
            call, f"Выбран {name} v{version}. START запустит этот рецепт.",
            reply_markup=preview_keyboard("v2_battery_start"),
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
