"""Opt-in Telegram recipe catalog commands; no actuator or charge START route."""
from __future__ import annotations

import html
import json
from typing import Any

from aiogram.filters import Command

from runtime.charge.programs.recipe_catalog import RecipeCatalog
from runtime.charge.programs.native_recipe_draft_library import NativeRecipeDraftLibrary
from runtime.charge.programs.native_recipe_draft import validate_native_draft
from runtime.charge.programs.native_recipe_session import require_supported_native_execution
from runtime.charge.programs.native_recipe_parameters import native_recipe_parameters
from runtime.charge.programs.native_recipe_catalog import get_native_recipe
from runtime.charge.programs.recipe_editor import edit_step, insert_step, transform_steps
from runtime.charge.programs.recipe_preflight import inspect_recipe
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

    native_drafts = NativeRecipeDraftLibrary(catalog.library.root.parent / "native_recipe_drafts")
    install_recipe_buttons(app, catalog=catalog, native_drafts=native_drafts)

    @app.router.message(Command("native_copy"))
    async def _native_copy(message: Any) -> None:
        if not await _allowed(message):
            return
        parts = str(message.text or "").split()
        if len(parts) != 3:
            await message.answer("Формат: /native_copy native_efb_normal my_efb")
            return
        try:
            source, name = parts[1:]
            get_native_recipe(source)
            draft = native_drafts.save(name, 1, {
                "schema": 1, "base_recipe_id": source,
                "execution_kind": "native_authority", "overrides": {},
            })
        except (ValueError, KeyError, FileExistsError, OSError) as exc:
            await message.answer("Ошибка копирования: " + html.escape(str(exc)),
                                 parse_mode=app.ParseMode.HTML)
            return
        await message.answer(
            f"Сохранена копия <code>{html.escape(name)}</code> v1 "
            f"из <code>{html.escape(draft.base_recipe_id)}</code>. "
            "Оригинал не изменён; копия пока не активируется.",
            parse_mode=app.ParseMode.HTML,
        )

    @app.router.message(Command("native_set"))
    async def _native_set(message: Any) -> None:
        if not await _allowed(message):
            return
        parts = str(message.text or "").split()
        if len(parts) != 4:
            await message.answer("Формат: /native_set my_efb charge.main.efb_voltage_v 14.8")
            return
        try:
            name, key, raw = parts[1:]
            versions = native_drafts.versions(name)
            if not versions:
                raise FileNotFoundError("копия не найдена")
            current = native_drafts.load(name, versions[-1])
            specs = {spec.key: spec for spec in native_recipe_parameters(current.base_recipe_id)}
            spec = specs.get(key)
            if spec is None:
                raise ValueError("параметр недоступен для этого рецепта")
            value = int(raw) if spec.value_type is int else float(raw.replace(",", "."))
            # Preserve exact integer type and refuse fractional truncation.
            if spec.value_type is int and str(value) != raw:
                raise ValueError("необходимо целое число")
            overrides = dict(current.overrides)
            overrides[key] = value
            changed = validate_native_draft({
                **current.as_document(), "overrides": overrides,
            })
            require_supported_native_execution(changed)
            native_drafts.save(name, versions[-1] + 1, changed.as_document())
        except (ValueError, KeyError, FileExistsError, FileNotFoundError, OSError) as exc:
            await message.answer("Ошибка настройки: " + html.escape(str(exc)),
                                 parse_mode=app.ParseMode.HTML)
            return
        await message.answer(
            f"<code>{html.escape(name)}</code> v{versions[-1] + 1}: "
            f"<code>{html.escape(key)}</code> = {html.escape(str(value))}. "
            "Версия сохранена, активная зарядка не изменена.",
            parse_mode=app.ParseMode.HTML,
        )

    @app.router.message(Command("native_show"))
    async def _native_show(message: Any) -> None:
        if not await _allowed(message):
            return
        parts = str(message.text or "").split()
        if len(parts) != 2:
            await message.answer("Формат: /native_show my_efb")
            return
        try:
            name = parts[1]
            versions = native_drafts.versions(name)
            if not versions:
                raise FileNotFoundError("копия не найдена")
            draft = native_drafts.load(name, versions[-1])
        except (ValueError, FileNotFoundError, OSError) as exc:
            await message.answer("Ошибка просмотра: " + html.escape(str(exc)),
                                 parse_mode=app.ParseMode.HTML)
            return
        overrides = "\n".join(
            f"<code>{html.escape(k)}</code> = {html.escape(str(v))}"
            for k, v in draft.overrides
        ) or "Нет изменений относительно оригинала"
        await message.answer(
            f"<b>{html.escape(name)} v{versions[-1]}</b>\n"
            f"Оригинал: <code>{html.escape(draft.base_recipe_id)}</code>\n"
            f"{overrides}\nКопия пока не применяется к контроллеру.",
            parse_mode=app.ParseMode.HTML,
        )

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

    @app.router.message(Command("recipe_delete_step"))
    async def _delete_step(message: Any) -> None:
        if not await _allowed(message):
            return
        parts = str(message.text or "").split()
        if len(parts) != 4:
            await message.answer("Формат: /recipe_delete_step имя версия шаг")
            return
        try:
            result = transform_steps(catalog, parts[1], int(parts[2]), "delete", int(parts[3]) - 1)
        except (ValueError, OSError) as exc:
            await message.answer(f"Удаление отклонено: {html.escape(str(exc))}", parse_mode=app.ParseMode.HTML)
            return
        await message.answer(f"Сохранена {html.escape(result.recipe_id)} v{result.version}")

    @app.router.message(Command("recipe_move_step"))
    async def _move_step(message: Any) -> None:
        if not await _allowed(message):
            return
        parts = str(message.text or "").split()
        if len(parts) != 5:
            await message.answer("Формат: /recipe_move_step имя версия шаг новое_место")
            return
        try:
            result = transform_steps(catalog, parts[1], int(parts[2]), "move",
                                     int(parts[3]) - 1, destination=int(parts[4]) - 1)
        except (ValueError, OSError) as exc:
            await message.answer(f"Перестановка отклонена: {html.escape(str(exc))}", parse_mode=app.ParseMode.HTML)
            return
        await message.answer(f"Сохранена {html.escape(result.recipe_id)} v{result.version}")

    @app.router.message(Command("recipe_condition"))
    async def _condition(message: Any) -> None:
        if not await _allowed(message):
            return
        parts = str(message.text or "").split()
        if len(parts) != 6:
            await message.answer("Формат: /recipe_condition имя версия шаг условие значение")
            return
        try:
            result = transform_steps(catalog, parts[1], int(parts[2]), "condition",
                                     int(parts[3]) - 1, condition=parts[4],
                                     threshold=float(parts[5].replace(",", ".")))
        except (ValueError, OSError) as exc:
            await message.answer(f"Условие отклонено: {html.escape(str(exc))}", parse_mode=app.ParseMode.HTML)
            return
        await message.answer(f"Сохранена {html.escape(result.recipe_id)} v{result.version}")

    @app.router.message(Command("recipe_check"))
    async def _check_recipe(message: Any) -> None:
        if not await _allowed(message):
            return
        parts = str(message.text or "").split()
        if len(parts) != 3:
            await message.answer("Формат: /recipe_check имя версия")
            return
        try:
            recipe = catalog.library.load(parts[1], int(parts[2]))
            report = inspect_recipe(recipe)
        except (ValueError, OSError) as exc:
            await message.answer(f"Проверка отклонена: {html.escape(str(exc))}",
                                 parse_mode=app.ParseMode.HTML)
            return
        verdict = "Структура PASS" if report.admissible_structure else "Структура FAIL"
        issues = [*report.problems, *report.warnings]
        details = "\n".join(html.escape(item) for item in issues)
        await message.answer(f"{verdict}: {html.escape(recipe.recipe_id)} v{recipe.version}\\n"
                             f"{details}\\nЭто не разрешение аппаратного START.",
                             parse_mode=app.ParseMode.HTML)

    app._recipe_catalog_commands_installed = True
