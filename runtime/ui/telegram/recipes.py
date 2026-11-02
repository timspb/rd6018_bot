"""Opt-in Telegram recipe catalog commands; no actuator or charge START route."""
from __future__ import annotations

import html
from typing import Any

from aiogram.filters import Command

from runtime.charge.programs.recipe_catalog import RecipeCatalog


def format_catalog(catalog: RecipeCatalog) -> str:
    names = catalog.list_recipes()
    if not names:
        return "Библиотека рецептов пуста. Действующие режимы не изменены."
    rows = ["<b>Мои рецепты</b>"]
    active = set(catalog.active_recipes())
    for name in names:
        versions = catalog.library.versions(name)
        state = "активен" if name in active else "архив"
        rows.append(f"• <code>{html.escape(name)}</code> — v{max(versions)} ({state})")
    rows.append("Эти рецепты пока не запускаются через Telegram.")
    return "\n".join(rows)


def install_recipe_catalog_commands(app: Any, *, catalog: RecipeCatalog) -> None:
    """Register non-destructive recipe library commands under existing chat ACL."""
    if getattr(app, "_recipe_catalog_commands_installed", False):
        return

    async def _allowed(message: Any) -> bool:
        return bool(await app._check_chat_and_respond(message))

    @app.router.message(Command("recipes"))
    async def _recipes(message: Any) -> None:
        if not await _allowed(message):
            return
        await message.answer(format_catalog(catalog), parse_mode=app.ParseMode.HTML)
    @app.router.message(Command("recipe_copy"))
    async def _copy(message: Any) -> None:
        if not await _allowed(message):
            return
        parts = str(message.text or "").split()
        if len(parts) != 4:
            await message.answer("Формат: /recipe_copy источник версия новое_имя")
            return
        try:
            result = catalog.duplicate(parts[1], int(parts[2]), parts[3])
        except (ValueError, FileNotFoundError, FileExistsError) as exc:
            await message.answer(f"Копирование отклонено: {html.escape(str(exc))}",
                                 parse_mode=app.ParseMode.HTML)
            return
        await message.answer(f"Сохранено: {html.escape(result.recipe_id)} v{result.version}")

    @app.router.message(Command("recipe_archive"))
    async def _archive(message: Any) -> None:
        if not await _allowed(message):
            return
        parts = str(message.text or "").split()
        if len(parts) != 2:
            await message.answer("Формат: /recipe_archive имя")
            return
        try:
            catalog.archive(parts[1])
        except (ValueError, FileNotFoundError, FileExistsError) as exc:
            await message.answer(f"Архивация отклонена: {html.escape(str(exc))}",
                                 parse_mode=app.ParseMode.HTML)
            return
        await message.answer(f"Рецепт {html.escape(parts[1])} архивирован; версии сохранены.")

    app._recipe_catalog_commands_installed = True
