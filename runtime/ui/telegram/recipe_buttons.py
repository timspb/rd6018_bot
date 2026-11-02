"""Read-only inline keyboard browser for user recipes."""
from __future__ import annotations

import html
from uuid import uuid4
from aiogram import F
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from runtime.charge.programs.recipe_catalog import RecipeCatalog
from runtime.charge.programs.recipe_editor import edit_step, insert_step, transform_steps


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
    rows.append([InlineKeyboardButton(text="Создать черновик", callback_data="recipes:create")])
    rows.append([InlineKeyboardButton(text="Обновить", callback_data="recipes:list")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def recipe_markup(recipe_id: str, version: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀ Библиотека", callback_data="recipes:list")],
        [InlineKeyboardButton(text="Редактор шагов", callback_data=f"recipes:edit:{recipe_id}:{version}")],
        [InlineKeyboardButton(text="Копировать: инструкция", callback_data=f"recipes:copyhelp:{recipe_id}:{version}")],
    ])

def install_recipe_buttons(app, *, catalog: RecipeCatalog) -> None:
    if getattr(app, "_recipe_buttons_installed", False):
        return

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

    @app.router.callback_query(F.data.startswith("recipes:edit:"))
    async def edit_menu(call):
        if not await app._check_chat_and_respond(call):
            return
        try:
            _, _, name, version = str(call.data).split(":")
            recipe = catalog.library.load(name, int(version))
        except (ValueError, OSError):
            await call.answer("Рецепт не найден", show_alert=True)
            return
        rows = []
        for index, step in enumerate(recipe.steps):
            if step["action"] != "set":
                continue
            for field, label in (("voltage_v", "U"), ("current_a", "I")):
                for delta, sign in ((-0.1, "-"), (0.1, "+")):
                    data = f"recipes:adjust:{name}:{version}:{index}:{field}:{sign}"
                    if len(data.encode("utf-8")) <= 64:
                        rows.append([InlineKeyboardButton(
                            text=f"Шаг {index+1} {label} {sign}0.1",
                            callback_data=data,
                        )])
        for index, step in enumerate(recipe.steps):
            if "after_seconds" in step["until"]:
                for change, label in (("minus", "-60с"), ("plus", "+60с")):
                    data = f"recipes:time:{name}:{version}:{index}:{change}"
                    if len(data.encode("utf-8")) <= 64:
                        rows.append([InlineKeyboardButton(text=f"Шаг {index+1} время {label}", callback_data=data)])
            if step["action"] == "set":
                for key, label in (("current_lte", "I ≤"), ("voltage_gte", "U ≥"), ("after_seconds", "Таймер")):
                    data = f"recipes:condition:{name}:{version}:{index}:{key}"
                    if len(data.encode("utf-8")) <= 64:
                        rows.append([InlineKeyboardButton(text=f"Шаг {index+1} условие {label}", callback_data=data)])
            key = next(iter(step["until"]))
            if key in {"current_lte", "voltage_gte"}:
                for direction, sign in (("minus", "-"), ("plus", "+")):
                    data = f"recipes:threshold:{name}:{version}:{index}:{direction}"
                    if len(data.encode("utf-8")) <= 64:
                        rows.append([InlineKeyboardButton(
                            text=f"Шаг {index+1} порог {sign}0.1", callback_data=data,
                        )])
            choices = [("delete", "Удалить")]
            if index > 0:
                choices.append(("up", "Вверх"))
            if index + 1 < len(recipe.steps):
                choices.append(("down", "Вниз"))
            for action, label in choices:
                data = f"recipes:step:{name}:{version}:{index}:{action}"
                if len(data.encode("utf-8")) <= 64:
                    rows.append([InlineKeyboardButton(
                        text=f"Шаг {index+1} {label}", callback_data=data,
                    )])
        for kind, label in (("set", "Добавить SET"), ("off", "Добавить OFF"), ("wait", "Добавить WAIT")):
            data = f"recipes:append:{name}:{version}:{kind}"
            if len(data.encode("utf-8")) <= 64:
                rows.append([InlineKeyboardButton(text=label, callback_data=data)])
        rows.append([InlineKeyboardButton(text="Назад", callback_data=f"recipes:view:{name}:{version}")])
        await call.answer()
        await call.message.answer(
            "Изменение уставок создаст новую версию (В/А).",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows[:35]),
        )

    @app.router.callback_query(F.data.startswith("recipes:threshold:"))
    async def change_threshold(call):
        if not await app._check_chat_and_respond(call):
            return
        try:
            _, _, name, raw_version, raw_index, direction = str(call.data).split(":")
            version, index = int(raw_version), int(raw_index)
            recipe = catalog.library.load(name, version)
            condition, current = next(iter(recipe.steps[index]["until"].items()))
            if condition not in {"current_lte", "voltage_gte"} or direction not in {"plus", "minus"}:
                raise ValueError("unsupported threshold edit")
            value = round(current + (0.1 if direction == "plus" else -0.1), 4)
            if value < 0:
                raise ValueError("threshold cannot be negative")
            updated = edit_step(catalog, name, version, index,
                                field="until:" + condition, value=value)
        except (ValueError, KeyError, IndexError, OSError) as exc:
            await call.answer(str(exc)[:150], show_alert=True)
            return
        await call.answer()
        await call.message.answer(
            f"Порог {condition}: {value:g}, версия {updated.version}.",
            reply_markup=recipe_markup(updated.recipe_id, updated.version),
        )

    @app.router.callback_query(F.data.startswith("recipes:condition:"))
    async def change_condition(call):
        if not await app._check_chat_and_respond(call):
            return
        try:
            _, _, name, raw_version, raw_index, condition = str(call.data).split(":")
            version, index = int(raw_version), int(raw_index)
            recipe = catalog.library.load(name, version)
            if recipe.steps[index]["action"] != "set":
                raise ValueError("condition applies to SET")
            values = {"current_lte": 0.2, "voltage_gte": 12.0, "after_seconds": 60.0}
            if condition not in values:
                raise ValueError("unsupported condition")
            updated = transform_steps(catalog, name, version, "condition", index,
                                      condition=condition, threshold=values[condition])
        except (ValueError, IndexError, OSError) as exc:
            await call.answer(str(exc)[:150], show_alert=True)
            return
        await call.answer()
        await call.message.answer(
            f"Условие {condition} задано, версия {updated.version}. Измените порог при необходимости.",
            reply_markup=recipe_markup(updated.recipe_id, updated.version),
        )

    @app.router.callback_query(F.data.startswith("recipes:time:"))
    async def change_time(call):
        if not await app._check_chat_and_respond(call):
            return
        try:
            _, _, name, raw_version, raw_index, direction = str(call.data).split(":")
            version, index = int(raw_version), int(raw_index)
            recipe = catalog.library.load(name, version)
            if direction not in {"plus", "minus"}:
                raise ValueError("invalid direction")
            current = recipe.steps[index]["until"]["after_seconds"]
            new_value = current + (60 if direction == "plus" else -60)
            if new_value <= 0:
                raise ValueError("duration must be positive")
            updated = edit_step(catalog, name, version, index,
                                field="until:after_seconds", value=new_value)
        except (ValueError, KeyError, IndexError, OSError) as exc:
            await call.answer(str(exc)[:150], show_alert=True)
            return
        await call.answer()
        await call.message.answer(
            f"Время шага {index+1}: {new_value:g} с, версия {updated.version}.",
            reply_markup=recipe_markup(updated.recipe_id, updated.version),
        )

    @app.router.callback_query(F.data.startswith("recipes:step:"))
    async def change_step(call):
        if not await app._check_chat_and_respond(call):
            return
        try:
            _, _, name, version_text, index_text, action = str(call.data).split(":")
            version, index = int(version_text), int(index_text)
            if action == "delete":
                updated = transform_steps(catalog, name, version, "delete", index)
            elif action in {"up", "down"}:
                updated = transform_steps(
                    catalog, name, version, "move", index,
                    destination=index + (-1 if action == "up" else 1),
                )
            else:
                raise ValueError("unsupported step action")
        except (ValueError, IndexError, OSError) as exc:
            await call.answer(str(exc)[:150], show_alert=True)
            return
        await call.answer()
        await call.message.answer(
            f"Сохранена версия {updated.version}. Предыдущая версия не изменена.",
            reply_markup=recipe_markup(updated.recipe_id, updated.version),
        )

    @app.router.callback_query(F.data.startswith("recipes:append:"))
    async def append_step(call):
        if not await app._check_chat_and_respond(call):
            return
        try:
            _, _, name, raw_version, kind = str(call.data).split(":")
            version = int(raw_version)
            recipe = catalog.library.load(name, version)
            if kind not in {"set", "off", "wait"}:
                raise ValueError("unknown step")
            # Conservative editable defaults; creation does not actuate hardware.
            params = {"voltage_v": min(12.0, catalog.library.max_voltage_v),
                      "current_a": min(0.5, catalog.library.max_current_a)} if kind == "set" else {}
            step = {"action": kind, "params": params, "until": {"after_seconds": 60}}
            updated = insert_step(catalog, name, version, len(recipe.steps), step)
        except (ValueError, OSError, KeyError, IndexError) as exc:
            await call.answer(str(exc)[:150], show_alert=True)
            return
        await call.answer()
        await call.message.answer(
            f"Добавлен {kind.upper()}: {updated.recipe_id} v{updated.version}. Зарядка не запущена.",
            reply_markup=recipe_markup(updated.recipe_id, updated.version),
        )

    @app.router.callback_query(F.data.startswith("recipes:adjust:"))
    async def adjust_step(call):
        if not await app._check_chat_and_respond(call):
            return
        try:
            _, _, name, version, index, field, sign = str(call.data).split(":")
            recipe = catalog.library.load(name, int(version))
            current = recipe.steps[int(index)]["params"][field]
            updated = edit_step(catalog, name, int(version), int(index),
                                field=field, value=round(current + (0.1 if sign == "+" else -0.1), 4))
        except (ValueError, IndexError, KeyError, OSError) as exc:
            await call.answer(f"Изменение отклонено: {str(exc)[:120]}", show_alert=True)
            return
        await call.answer()
        await call.message.answer(
            f"Сохранена версия {updated.version}. Предыдущие версии не изменены.",
            reply_markup=recipe_markup(updated.recipe_id, updated.version),
        )

    app._recipe_buttons_installed = True
