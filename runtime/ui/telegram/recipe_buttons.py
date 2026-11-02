"""Read-only inline keyboard browser for user recipes."""
from __future__ import annotations

import html
from aiogram import F
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from runtime.charge.programs.recipe_catalog import RecipeCatalog


def catalog_markup(catalog: RecipeCatalog) -> InlineKeyboardMarkup:
    names = catalog.active_recipes()
    rows = []
    for name in names[:30]:
        versions = catalog.library.versions(name)
        if versions and len(f"recipes:view:{name}:{versions[-1]}".encode("utf-8")) <= 64:
            rows.append([InlineKeyboardButton(
                text=f"{name} · v{versions[-1]}",
                callback_data=f"recipes:view:{name}:{versions[-1]}",
            )])
    rows.append([InlineKeyboardButton(text="Обновить", callback_data="recipes:list")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def recipe_markup(recipe_id: str, version: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀ Библиотека", callback_data="recipes:list")],
        [InlineKeyboardButton(text="Копировать: инструкция", callback_data=f"recipes:copyhelp:{recipe_id}:{version}")],
    ])

def install_recipe_buttons(app, *, catalog: RecipeCatalog) -> None:
    if getattr(app, "_recipe_buttons_installed", False):
        return

    @app.router.callback_query(F.data == "recipes:list")
    async def show_list(call):
        if not await app._check_chat_and_respond(call):
            return
        await call.answer()
        await call.message.answer(
            "Мои пользовательские рецепты (без запуска зарядки):",
            reply_markup=catalog_markup(catalog),
        )

    @app.router.callback_query(F.data.startswith("recipes:view:"))
    async def show_recipe(call):
        if not await app._check_chat_and_respond(call):
            return
        try:
            _, _, name, version = str(call.data).split(":")
            recipe = catalog.library.load(name, int(version))
        except (ValueError, OSError):
            await call.answer("Рецепт не найден", show_alert=True)
            return
        lines = [f"<b>{html.escape(recipe.recipe_id)} v{recipe.version}</b>"]
        for i, step in enumerate(recipe.steps, 1):
            action = html.escape(step["action"])
            predicate, target = next(iter(step["until"].items()))
            lines.append(f"{i}. {action}: {html.escape(str(step['params']))} → {predicate} {target}")
        await call.answer()
        await call.message.answer(
            "\n".join(lines)[:3900], parse_mode=app.ParseMode.HTML,
            reply_markup=recipe_markup(recipe.recipe_id, recipe.version),
        )

    @app.router.callback_query(F.data.startswith("recipes:copyhelp:"))
    async def copy_help(call):
        if not await app._check_chat_and_respond(call):
            return
        try:
            _, _, name, version = str(call.data).split(":")
            catalog.library.load(name, int(version))
        except (ValueError, OSError):
            await call.answer("Рецепт не найден", show_alert=True)
            return
        await call.answer()
        await call.message.answer(
            f"Чтобы создать отдельную копию, отправь:\n"
            f"<code>/recipe_copy {html.escape(name)} {version} новое_имя</code>",
            parse_mode=app.ParseMode.HTML,
        )

    app._recipe_buttons_installed = True
