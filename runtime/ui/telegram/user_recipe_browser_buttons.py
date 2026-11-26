"""Telegram callback owner for the user recipe library browser."""
from __future__ import annotations

import html
from uuid import uuid4

from aiogram import F
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from runtime.charge.programs.recipe_preflight import inspect_recipe
from runtime.ui.telegram.recipe_menu_view import (
    STEP_VIEW_PAGE_SIZE, catalog_markup, recipe_history_markup, recipe_markup,
    step_summary,
)


def install_user_recipe_browser_buttons(app, catalog) -> None:
    """Register the existing read/edit catalog callbacks on the shared router."""

    @app.router.callback_query(F.data.startswith("recipes:check:"))
    async def check_recipe(call):
        if not await app._check_chat_and_respond(call):
            return
        try:
            _, _, name, version = str(call.data).split(":")
            recipe = catalog.library.load(name, int(version))
            report = inspect_recipe(recipe)
        except (ValueError, OSError) as exc:
            await call.answer(str(exc)[:150], show_alert=True)
            return
        issues = [*report.problems, *report.warnings]
        verdict = "PASS" if report.admissible_structure else "FAIL"
        details = "\n".join(html.escape(issue) for issue in issues)
        await call.answer()
        await call.message.answer(
            f"Проверка структуры: {verdict} — {html.escape(recipe.recipe_id)} v{recipe.version}\n"
            + (details or "Ошибок структуры нет.")
            + "\nЭто проверка сценария, не разрешение запуска оборудования.",
            parse_mode=app.ParseMode.HTML,
            reply_markup=recipe_markup(recipe.recipe_id, recipe.version),
        )

    @app.router.callback_query(F.data == "recipes:create")
    async def create_draft(call):
        if not await app._check_chat_and_respond(call):
            return
        name = "draft_" + uuid4().hex[:10]
        try:
            recipe = catalog.library.save({
                "id": name, "version": 1,
                "steps": [{"action": "off", "params": {},
                           "until": {"after_seconds": 1}}],
            })
        except (ValueError, OSError) as exc:
            await call.answer(str(exc)[:150], show_alert=True)
            return
        await call.answer()
        await call.message.answer(
            f"Черновик {name} v1 создан. Первый шаг — OFF; зарядка не запущена. "
            "Добавляйте шаги через /recipe_insert или редактор.",
            reply_markup=recipe_markup(recipe.recipe_id, recipe.version),
        )

    @app.router.callback_query(F.data.startswith("recipes:list"))
    async def show_list(call):
        if not await app._check_chat_and_respond(call):
            return
        try:
            parts = str(call.data).split(":")
            if len(parts) not in (2, 3) or parts[:2] != ["recipes", "list"]:
                raise ValueError("invalid catalog callback")
            page = int(parts[2]) if len(parts) == 3 else 0
            markup = catalog_markup(catalog, page=page)
        except ValueError as exc:
            await call.answer(str(exc)[:150], show_alert=True)
            return
        await call.answer()
        await call.message.answer(
            "Мои пользовательские рецепты (без запуска зарядки):",
            reply_markup=markup,
        )

    @app.router.callback_query(F.data.startswith("recipes:view:"))
    async def show_recipe(call):
        if not await app._check_chat_and_respond(call):
            return
        try:
            parts = str(call.data).split(":")
            if len(parts) not in (4, 5) or parts[:2] != ["recipes", "view"]:
                raise ValueError("Неверная ссылка на рецепт")
            _, _, name, raw_version = parts[:4]
            page = int(parts[4]) if len(parts) == 5 else 0
            recipe = catalog.library.load(name, int(raw_version))
            versions = catalog.library.versions(name)
            archived = (catalog.library.root / name / ".archived").exists()
            latest = versions[-1]
            pages = (len(recipe.steps) + STEP_VIEW_PAGE_SIZE - 1) // STEP_VIEW_PAGE_SIZE
            message_text = step_summary(recipe, archived=archived, latest=latest,
                                        page=page)
        except (ValueError, OSError) as exc:
            await call.answer(str(exc)[:120], show_alert=True)
            return
        await call.answer()
        await call.message.answer(
            message_text, parse_mode=app.ParseMode.HTML,
            reply_markup=recipe_markup(
                recipe.recipe_id, recipe.version,
                editable=not archived and recipe.version == latest,
                page=page, pages=pages),
        )

    @app.router.callback_query(F.data.startswith("recipes:history:"))
    async def recipe_history(call):
        if not await app._check_chat_and_respond(call):
            return
        try:
            _, _, name, raw_page = str(call.data).split(":")
            page = int(raw_page)
            markup = recipe_history_markup(catalog, name, page=page)
            count = len(catalog.library.versions(name))
            archived = (catalog.library.root / name / ".archived").exists()
        except (ValueError, OSError) as exc:
            await call.answer(str(exc)[:150], show_alert=True)
            return
        await call.answer()
        await call.message.answer(
            f"<b>История: {html.escape(name)}</b> · {count} версий"
            + (" · архив" if archived else "")
            + "\nВыберите версию для просмотра. История неизменяема.",
            parse_mode=app.ParseMode.HTML,
            reply_markup=markup,
        )

    @app.router.callback_query(F.data.startswith("recipes:duplicate:"))
    async def recipe_duplicate(call):
        if not await app._check_chat_and_respond(call):
            return
        try:
            _, _, name, raw_version = str(call.data).split(":")
            version = int(raw_version)
            copy_name = "copy_" + uuid4().hex[:10]
            copied = catalog.duplicate(name, version, copy_name)
        except (ValueError, FileNotFoundError, FileExistsError, OSError) as exc:
            await call.answer(str(exc)[:150], show_alert=True)
            return
        await call.answer()
        await call.message.answer(
            f"Создана копия <code>{html.escape(copied.recipe_id)}</code> "
            f"v{copied.version} из <code>{html.escape(name)}</code> v{version}. "
            "Исходная версия не изменена; Output не включался.",
            parse_mode=app.ParseMode.HTML,
            reply_markup=recipe_markup(copied.recipe_id, copied.version),
        )

    @app.router.callback_query(F.data.startswith("recipes:archiveask:"))
    async def recipe_archive_ask(call):
        if not await app._check_chat_and_respond(call):
            return
        try:
            _, _, name = str(call.data).split(":")
            versions = catalog.library.versions(name)
            if not versions:
                raise ValueError("рецепт не найден")
            if (catalog.library.root / name / ".archived").exists():
                raise ValueError("рецепт уже в архиве")
            confirm = f"recipes:archiveconfirm:{name}"
            if len(confirm.encode("utf-8")) > 64:
                raise ValueError("имя слишком длинное для кнопки")
        except (ValueError, OSError) as exc:
            await call.answer(str(exc)[:150], show_alert=True)
            return
        await call.answer()
        await call.message.answer(
            f"Архивировать <code>{html.escape(name)}</code>? "
            "Все версии останутся доступны для чтения, "
            "но новые версии сохранять будет нельзя.",
            parse_mode=app.ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Подтвердить архив",
                                      callback_data=confirm)],
                [InlineKeyboardButton(text="Отмена",
                                      callback_data="recipes:list")],
            ]),
        )

    @app.router.callback_query(F.data.startswith("recipes:archiveconfirm:"))
    async def recipe_archive_confirm(call):
        if not await app._check_chat_and_respond(call):
            return
        try:
            _, _, name = str(call.data).split(":")
            catalog.archive(name)
        except (ValueError, FileNotFoundError, FileExistsError, OSError) as exc:
            await call.answer(str(exc)[:150], show_alert=True)
            return
        await call.answer()
        await call.message.answer(
            f"<code>{html.escape(name)}</code> архивирован. Версии сохранены. "
            "Зарядка не изменена.",
            parse_mode=app.ParseMode.HTML,
            reply_markup=catalog_markup(catalog),
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
