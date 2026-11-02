"""Opt-in Telegram recipe catalog commands; no actuator or charge START route."""
from __future__ import annotations

import html
import json
from typing import Any

from aiogram.filters import Command

from runtime.charge.programs.recipe_catalog import RecipeCatalog
from runtime.charge.programs.recipe_editor import edit_step, insert_step
from runtime.ui.telegram.recipe_buttons import catalog_markup, install_recipe_buttons


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

    install_recipe_buttons(app, catalog=catalog)

    @app.router.message(Command("recipes"))
    async def _recipes(message: Any) -> None:
        if not await _allowed(message):
            return
        await message.answer(format_catalog(catalog), parse_mode=app.ParseMode.HTML,
                             reply_markup=catalog_markup(catalog))
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

    @app.router.message(Command("recipe_new"))
    async def _new(message: Any) -> None:
        if not await _allowed(message):
            return
        parts = str(message.text or "").split(maxsplit=2)
        if len(parts) != 3:
            await message.answer("Формат: /recipe_new имя JSON_массива_шагов")
            return
        try:
            steps = json.loads(parts[2])
            result = catalog.library.save({"id": parts[1], "version": 1, "steps": steps})
        except (ValueError, TypeError, FileExistsError, OSError) as exc:
            await message.answer(f"Сохранение отклонено: {html.escape(str(exc))}",
                                 parse_mode=app.ParseMode.HTML)
            return
        await message.answer(f"Создан рецепт {html.escape(result.recipe_id)} v1")

    @app.router.message(Command("recipe_version"))
    async def _version(message: Any) -> None:
        if not await _allowed(message):
            return
        parts = str(message.text or "").split(maxsplit=2)
        if len(parts) != 3:
            await message.answer("Формат: /recipe_version имя JSON_массива_шагов")
            return
        try:
            result = catalog.next_version(parts[1], json.loads(parts[2]))
        except (ValueError, TypeError, FileNotFoundError, FileExistsError, OSError) as exc:
            await message.answer(f"Новая версия отклонена: {html.escape(str(exc))}",
                                 parse_mode=app.ParseMode.HTML)
            return
        await message.answer(f"Сохранена {html.escape(result.recipe_id)} v{result.version}")

    @app.router.message(Command("recipe_show"))
    async def _show(message: Any) -> None:
        if not await _allowed(message):
            return
        parts = str(message.text or "").split()
        if len(parts) != 3:
            await message.answer("Формат: /recipe_show имя версия")
            return
        try:
            recipe = catalog.library.load(parts[1], int(parts[2]))
        except (ValueError, FileNotFoundError, OSError) as exc:
            await message.answer(f"Просмотр отклонён: {html.escape(str(exc))}",
                                 parse_mode=app.ParseMode.HTML)
            return
        lines = [f"<b>{html.escape(recipe.recipe_id)} v{recipe.version}</b>"]
        for index, step in enumerate(recipe.steps, 1):
            details = json.dumps(step, ensure_ascii=False, sort_keys=True)
            lines.append(f"{index}. <code>{html.escape(details)}</code>")
        text = "\n".join(lines)
        if len(text) > 3800:
            await message.answer("Рецепт слишком длинный для одного сообщения.")
            return
        await message.answer(text, parse_mode=app.ParseMode.HTML)

    @app.router.message(Command("recipe_set"))
    async def _set_field(message: Any) -> None:
        if not await _allowed(message):
            return
        parts = str(message.text or "").split()
        if len(parts) != 6:
            await message.answer("Формат: /recipe_set имя версия шаг поле значение")
            return
        try:
            name, version, index, field, raw_value = parts[1:]
            if field not in {"voltage_v", "current_a", "after_seconds",
                             "voltage_gte", "voltage_lte", "current_gte",
                             "current_lte", "temperature_gte", "temperature_lte"}:
                raise ValueError("unsupported field")
            field = field if field in {"voltage_v", "current_a"} else "until:" + field
            value = float(raw_value.replace(",", "."))
            result = edit_step(catalog, name, int(version), int(index) - 1,
                               field=field, value=value)
        except (ValueError, IndexError, FileNotFoundError, OSError) as exc:
            await message.answer(f"Изменение отклонено: {html.escape(str(exc))}",
                                 parse_mode=app.ParseMode.HTML)
            return
        await message.answer(f"Сохранена {html.escape(result.recipe_id)} v{result.version}")

    @app.router.message(Command("recipe_insert"))
    async def _insert(message: Any) -> None:
        if not await _allowed(message):
            return
        parts = str(message.text or "").split(maxsplit=4)
        if len(parts) != 5:
            await message.answer("Формат: /recipe_insert имя версия позиция JSON_шага")
            return
        try:
            name, version, position, raw = parts[1:]
            step = json.loads(raw)
            updated = insert_step(catalog, name, int(version), int(position) - 1, step)
        except (ValueError, TypeError, IndexError, OSError) as exc:
            await message.answer(f"Вставка отклонена: {html.escape(str(exc))}",
                                 parse_mode=app.ParseMode.HTML)
            return
        await message.answer(f"Создана {html.escape(updated.recipe_id)} v{updated.version}")

    app._recipe_catalog_commands_installed = True
