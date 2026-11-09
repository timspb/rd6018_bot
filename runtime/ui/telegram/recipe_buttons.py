"""Read-only inline keyboard browser for user recipes."""
from __future__ import annotations

import html
from decimal import Decimal
from uuid import uuid4
from aiogram import F
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from runtime.charge.programs.recipe_catalog import RecipeCatalog
from runtime.charge.programs.native_recipe_draft_library import NativeRecipeDraftLibrary
from runtime.charge.programs.native_recipe_session import require_supported_native_execution
from runtime.charge.programs.native_recipe_draft import validate_native_draft
from runtime.config.variable_spec import OverridePolicy
from runtime.charge.programs.native_recipe_catalog import get_native_recipe, native_recipes
from runtime.charge.programs.native_recipe_parameters import native_recipe_parameters
from runtime.charge.programs.recipe_editor import edit_step, insert_step, transform_steps
from runtime.charge.programs.recipe_preflight import inspect_recipe


def catalog_markup(catalog: RecipeCatalog, *, page: int = 0,
                   page_size: int = 20) -> InlineKeyboardMarkup:
    """Show every active recipe over multiple pages, retaining library actions."""
    if page_size < 1:
        raise ValueError("invalid catalog page size")
    entries = []
    for name in catalog.active_recipes():
        versions = catalog.library.versions(name)
        if versions:
            callback = f"recipes:view:{name}:{versions[-1]}"
            if len(callback.encode("utf-8")) <= 64:
                entries.append((name, versions[-1], callback))
    pages = max(1, (len(entries) + page_size - 1) // page_size)
    if not 0 <= page < pages:
        raise ValueError("catalog page outside available range")
    rows = [
        [InlineKeyboardButton(text=f"{name} · v{version}", callback_data=callback)]
        for name, version, callback in entries[page * page_size:(page + 1) * page_size]
    ]
    navigation = []
    if page > 0:
        navigation.append(InlineKeyboardButton(
            text="◀ Предыдущие", callback_data=f"recipes:list:{page-1}"))
    if page + 1 < pages:
        navigation.append(InlineKeyboardButton(
            text="Следующие ▶", callback_data=f"recipes:list:{page+1}"))
    if navigation:
        rows.append(navigation)
    rows.append([InlineKeyboardButton(
        text="⚙️ Штатные программы (12)",
        callback_data="recipes:native:list",
    )])
    rows.append([InlineKeyboardButton(text="Создать черновик", callback_data="recipes:create")])
    rows.append([InlineKeyboardButton(text="Обновить", callback_data=f"recipes:list:{page}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def native_recipe_markup() -> InlineKeyboardMarkup:
    """Browse native variants without mutation, START or custom-recipe actions."""
    rows = [
        [InlineKeyboardButton(
            text=f"{entry.profile} · {entry.intent}",
            callback_data=f"recipes:native:view:{entry.recipe_id}",
        )]
        for entry in native_recipes()
    ]
    rows.append([InlineKeyboardButton(
        text="Мои копии штатных программ", callback_data="recipes:nd:list",
    )])
    rows.append([InlineKeyboardButton(
        text="⬅️ Мои рецепты", callback_data="recipes:list",
    )])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def recipe_markup(recipe_id: str, version: int) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text="◀ Библиотека", callback_data="recipes:list")]]
    for label, data in (
        ("Редактор шагов", f"recipes:edit:{recipe_id}:{version}"),
        ("Проверить рецепт", f"recipes:check:{recipe_id}:{version}"),
        ("История версий", f"recipes:history:{recipe_id}:0"),
        ("Копировать", f"recipes:duplicate:{recipe_id}:{version}"),
        ("В архив", f"recipes:archiveask:{recipe_id}"),
    ):
        if len(data.encode("utf-8")) <= 64:
            rows.append([InlineKeyboardButton(text=label, callback_data=data)])
    return InlineKeyboardMarkup(inline_keyboard=rows)



def recipe_history_markup(catalog: RecipeCatalog, name: str, *,
                          page: int = 0, page_size: int = 8) -> InlineKeyboardMarkup:
    """Paginated immutable history, retaining the existing recipe viewer."""
    versions = catalog.library.versions(name)
    if not versions or page_size < 1:
        raise ValueError("recipe has no versions or page size invalid")
    ordered = sorted(versions, reverse=True)
    pages = (len(ordered) + page_size - 1) // page_size
    if not 0 <= page < pages:
        raise ValueError("history page outside available range")
    rows = []
    for version in ordered[page * page_size:(page + 1) * page_size]:
        data = f"recipes:view:{name}:{version}"
        if len(data.encode("utf-8")) <= 64:
            rows.append([InlineKeyboardButton(
                text=f"Версия {version}", callback_data=data)])
    navigation = []
    for target, label in ((page - 1, "◀"), (page + 1, "▶")):
        if 0 <= target < pages:
            data = f"recipes:history:{name}:{target}"
            if len(data.encode("utf-8")) <= 64:
                navigation.append(InlineKeyboardButton(text=label, callback_data=data))
    if navigation:
        rows.append(navigation)
    rows.append([InlineKeyboardButton(
        text="К библиотеке", callback_data="recipes:list")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def editor_page(rows: list, *, name: str, version: int, page: int,
                page_size: int = 30) -> InlineKeyboardMarkup:
    """Paginate editable controls; always retain a way back to the recipe."""
    if page_size < 1 or not rows:
        raise ValueError("empty editor controls or invalid page size")
    pages = (len(rows) + page_size - 1) // page_size
    if page < 0 or page >= pages:
        raise ValueError("editor page outside available range")
    selected = list(rows[page * page_size:(page + 1) * page_size])
    navigation = []
    for target, label in ((page - 1, "Назад к кнопкам"),
                          (page + 1, "Следующие кнопки")):
        if 0 <= target < pages:
            data = f"recipes:edit:{name}:{version}:{target}"
            if len(data.encode("utf-8")) <= 64:
                navigation.append(InlineKeyboardButton(text=label, callback_data=data))
    if navigation:
        selected.append(navigation)
    back = f"recipes:view:{name}:{version}"
    if len(back.encode("utf-8")) <= 64:
        selected.append([InlineKeyboardButton(text="К рецепту", callback_data=back)])
    return InlineKeyboardMarkup(inline_keyboard=selected)



def _native_editable_specs(draft):
    """Only module-owned, production-wired numeric parameters are actionable."""
    result = []
    for spec in native_recipe_parameters(draft.base_recipe_id):
        if spec.override_policy != OverridePolicy.CONFIG_FILE or spec.value_type not in (int, float):
            continue
        try:
            trial = validate_native_draft({
                **draft.as_document(),
                "overrides": {**dict(draft.overrides), spec.key: spec.default},
            })
            require_supported_native_execution(trial)
        except ValueError:
            continue
        result.append(spec)
    return tuple(result)


def _native_adjust_value(spec, current, direction):
    """Steps derive from the owning VariableSpec bounds, not recipe-specific JS/UI rules."""
    if direction not in ("up", "down"):
        raise ValueError("invalid adjustment direction")
    sign = 1 if direction == "up" else -1
    if spec.value_type is int:
        value = current + sign
    else:
        low = Decimal(str(spec.minimum if spec.minimum is not None else 0))
        high = Decimal(str(spec.maximum if spec.maximum is not None else spec.default))
        step = max((high - low) / Decimal(100), Decimal("0.001"))
        value = float(Decimal(str(current)) + sign * step)
    if spec.minimum is not None and value < spec.minimum:
        raise ValueError("parameter is at minimum")
    if spec.maximum is not None and value > spec.maximum:
        raise ValueError("parameter is at maximum")
    return value

def install_recipe_buttons(app, *, catalog: RecipeCatalog,
                           native_drafts: NativeRecipeDraftLibrary | None = None) -> None:
    if getattr(app, "_recipe_buttons_installed", False):
        return
    if native_drafts is None:
        native_drafts = NativeRecipeDraftLibrary(catalog.library.root.parent / "native_recipe_drafts")

    @app.router.callback_query(F.data == "recipes:nd:list")
    async def native_draft_list(call):
        if not await app._check_chat_and_respond(call):
            return
        rows = []
        for name in native_drafts.list_drafts():
            versions = native_drafts.versions(name)
            if not versions:
                continue
            command = f"recipes:nd:view:{name}:{versions[-1]}"
            if len(command.encode("utf-8")) <= 64:
                archived = (native_drafts.root / name / ".archived").exists()
                rows.append([InlineKeyboardButton(
                    text=f"{name} · v{versions[-1]}" + (" [архив]" if archived else ""),
                    callback_data=command)])
        rows.append([InlineKeyboardButton(
            text="К штатным программам", callback_data="recipes:native:list")])
        await call.answer()
        await call.message.answer(
            "Мои копии штатных рецептов. Изменения не активируют зарядку.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        )

    @app.router.callback_query(F.data.startswith("recipes:nd:view:"))
    async def native_draft_view(call):
        if not await app._check_chat_and_respond(call):
            return
        try:
            _, _, _, name, raw_version = str(call.data).split(":")
            version = int(raw_version)
            draft = native_drafts.load(name, version)
            require_supported_native_execution(draft)
            versions = native_drafts.versions(name)
            archived = (native_drafts.root / name / ".archived").exists()
            lines = [f"<b>{html.escape(name)} v{version}</b>",
                     f"Оригинал: <code>{html.escape(draft.base_recipe_id)}</code>",
                     "Архив" if archived else "Копия доступна для новой версии"]
            lines.extend(f"<code>{html.escape(key)}</code>: {html.escape(str(value))}"
                         for key, value in draft.overrides)
            rows = []
            for candidate in reversed(versions[-10:]):
                key = f"recipes:nd:view:{name}:{candidate}"
                if len(key.encode("utf-8")) <= 64:
                    rows.append([InlineKeyboardButton(
                        text=f"Версия {candidate}", callback_data=key)])
            if not archived and version == versions[-1]:
                key = f"recipes:nd:edit:{name}:{version}:0"
                if len(key.encode("utf-8")) <= 64:
                    rows.insert(0, [InlineKeyboardButton(
                        text="⚙️ Настроить параметры", callback_data=key)])
            rows.append([InlineKeyboardButton(
                text="Мои копии", callback_data="recipes:nd:list")])
        except (ValueError, FileNotFoundError, OSError) as exc:
            await call.answer(str(exc)[:120], show_alert=True)
            return
        await call.answer()
        await call.message.answer(
            "\n".join(lines)[:3600] + "\nВыбор версии не запускает зарядку.",
            parse_mode=app.ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        )

    @app.router.callback_query(F.data.startswith("recipes:nd:edit:"))
    async def native_draft_edit(call):
        if not await app._check_chat_and_respond(call):
            return
        try:
            _, _, _, name, raw_version, raw_page = str(call.data).split(":")
            version, page = int(raw_version), int(raw_page)
            versions = native_drafts.versions(name)
            if not versions or version != versions[-1]:
                raise ValueError("Открыта устаревшая версия; обновите рецепт")
            if (native_drafts.root / name / ".archived").exists():
                raise ValueError("Копия в архиве")
            draft = native_drafts.load(name, version)
            specs = _native_editable_specs(draft)
            page_size = 5
            if not 0 <= page * page_size < max(1, len(specs)):
                raise ValueError("Недопустимая страница параметров")
            lines = [f"<b>{html.escape(name)} · v{version}</b>",
                     "Изменения сохраняются отдельной версией, без START."]
            rows = []
            for index in range(page * page_size, min((page + 1) * page_size, len(specs))):
                spec = specs[index]
                value = dict(draft.overrides).get(spec.key, spec.default)
                lines.append(f"<code>{html.escape(spec.key)}</code>: "
                             f"{html.escape(str(value))} {html.escape(spec.unit)}")
                buttons = []
                for direction, label in (("down", "−"), ("up", "+")):
                    data = f"recipes:nd:adjust:{name}:{version}:{index}:{direction}"
                    if len(data.encode("utf-8")) <= 64:
                        buttons.append(InlineKeyboardButton(
                            text=f"{label} {spec.description[:18]}", callback_data=data))
                if buttons:
                    rows.append(buttons)
            nav = []
            for target, label in ((page - 1, "◀"), (page + 1, "▶")):
                if 0 <= target * page_size < len(specs):
                    data = f"recipes:nd:edit:{name}:{version}:{target}"
                    if len(data.encode("utf-8")) <= 64:
                        nav.append(InlineKeyboardButton(text=label, callback_data=data))
            if nav:
                rows.append(nav)
            back = f"recipes:nd:view:{name}:{version}"
            if len(back.encode("utf-8")) <= 64:
                rows.append([InlineKeyboardButton(text="◀ К копии", callback_data=back)])
        except (ValueError, FileNotFoundError, OSError) as exc:
            await call.answer(str(exc)[:120], show_alert=True)
            return
        await call.answer()
        await call.message.answer(
            "\n".join(lines), parse_mode=app.ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))

    @app.router.callback_query(F.data.startswith("recipes:nd:adjust:"))
    async def native_draft_adjust(call):
        if not await app._check_chat_and_respond(call):
            return
        try:
            _, _, _, name, raw_version, raw_index, direction = str(call.data).split(":")
            version, index = int(raw_version), int(raw_index)
            versions = native_drafts.versions(name)
            if not versions or version != versions[-1]:
                raise ValueError("Версия уже изменилась; откройте последнюю")
            if (native_drafts.root / name / ".archived").exists():
                raise ValueError("Копия в архиве")
            draft = native_drafts.load(name, version)
            specs = _native_editable_specs(draft)
            if not 0 <= index < len(specs):
                raise ValueError("Неизвестный параметр")
            spec = specs[index]
            overrides = dict(draft.overrides)
            value = _native_adjust_value(
                spec, overrides.get(spec.key, spec.default), direction)
            overrides[spec.key] = value
            changed = validate_native_draft({
                **draft.as_document(), "overrides": overrides})
            require_supported_native_execution(changed)
            native_drafts.save(name, version + 1, changed.as_document())
            back = f"recipes:nd:edit:{name}:{version + 1}:{index // 5}"
            rows = []
            if len(back.encode("utf-8")) <= 64:
                rows.append([InlineKeyboardButton(
                    text="Продолжить настройку", callback_data=back)])
        except (ValueError, KeyError, FileNotFoundError, FileExistsError, OSError) as exc:
            await call.answer(str(exc)[:120], show_alert=True)
            return
        await call.answer()
        await call.message.answer(
            f"<b>{html.escape(name)} · v{version + 1}</b>\n"
            f"<code>{html.escape(spec.key)}</code> = {html.escape(str(value))} "
            f"{html.escape(spec.unit)}\n"
            "Сохранена новая версия. Зарядка не запускалась.",
            parse_mode=app.ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))

    @app.router.callback_query(F.data.startswith("recipes:nd:copy:"))
    async def native_draft_copy(call):
        if not await app._check_chat_and_respond(call):
            return
        try:
            source = str(call.data).removeprefix("recipes:nd:copy:")
            get_native_recipe(source)
            name = "copy_" + uuid4().hex[:10]
            new = native_drafts.save(name, 1, {
                "schema": 1, "base_recipe_id": source,
                "execution_kind": "native_authority", "overrides": {},
            })
        except (KeyError, ValueError, FileExistsError, OSError) as exc:
            await call.answer(str(exc)[:120], show_alert=True)
            return
        await call.answer()
        await call.message.answer(
            f"Создана <code>{html.escape(name)}</code> v1 из "
            f"<code>{html.escape(new.base_recipe_id)}</code>. "
            "Настраивайте кнопкой «⚙️ Настроить параметры» в своей копии; Output не включался.",
            parse_mode=app.ParseMode.HTML,
        )

    @app.router.callback_query(F.data == "recipes:native:list")
    async def native_catalog(call):
        if not await app._check_chat_and_respond(call):
            return
        await call.answer()
        await call.message.answer(
            "⚙️ <b>Штатные программы</b>\n"
            "Действующие алгоритмы, только просмотр. "
            "Редактируемые пользовательские рецепты доступны отдельно.",
            parse_mode=app.ParseMode.HTML,
            reply_markup=native_recipe_markup(),
        )

    @app.router.callback_query(F.data.startswith("recipes:native:view:"))
    async def native_recipe_details(call):
        if not await app._check_chat_and_respond(call):
            return
        try:
            recipe_id = str(call.data).removeprefix("recipes:native:view:")
            entry = get_native_recipe(recipe_id)
        except KeyError:
            await call.answer("Штатная программа не найдена", show_alert=True)
            return
        await call.answer()
        await call.message.answer(
            f"<b>{html.escape(entry.profile)} · {html.escape(entry.intent)}</b>\n"
            "Тип: штатный динамический рецепт\n"
            "Исполнение: существующий контроллер MAIN / Recovery / MIX\n"
            "Возможные стадии: "
            + html.escape(", ".join(entry.stages))
            + "\nРедактирование и запуск из библиотеки недоступны. "
              "Для обычного запуска используйте выбор АКБ и режима.",
            parse_mode=app.ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Штатные программы",
                                      callback_data="recipes:native:list")],
                [InlineKeyboardButton(
                    text="⚙️ Параметры",
                    callback_data=f"recipes:native:params:{entry.recipe_id}")],
                [InlineKeyboardButton(text="Создать свою копию",
                                      callback_data=f"recipes:nd:copy:{entry.recipe_id}")],
                [InlineKeyboardButton(text="Мои копии",
                                      callback_data="recipes:nd:list")],
                [InlineKeyboardButton(text="Мои рецепты",
                                      callback_data="recipes:list")],
            ]),
        )

    @app.router.callback_query(F.data.startswith("recipes:native:params:"))
    async def native_recipe_parameters_view(call):
        if not await app._check_chat_and_respond(call):
            return
        try:
            recipe_id = str(call.data).removeprefix("recipes:native:params:")
            entry = get_native_recipe(recipe_id)
            specs = native_recipe_parameters(recipe_id)
        except KeyError:
            await call.answer("Штатный рецепт не найден", show_alert=True)
            return
        await call.answer()
        lines = [f"<b>Параметры: {html.escape(entry.profile)} · "
                 f"{html.escape(entry.intent)}</b>",
                 "Текущие значения объявлений (не активная версия настроек):"]
        for spec in specs:
            bound = (f"{spec.minimum if spec.minimum is not None else '—'}…"
                     f"{spec.maximum if spec.maximum is not None else '—'}")
            lines.append(
                f"<code>{html.escape(spec.key)}</code>: "
                f"{html.escape(str(spec.default))} {html.escape(spec.unit)} "
                f"({html.escape(bound)})"
            )
        lines.append("Изменения пока не применяются к контроллеру.")
        await call.message.answer(
            "\n".join(lines), parse_mode=app.ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text="⬅️ Штатный рецепт",
                    callback_data=f"recipes:native:view:{entry.recipe_id}",
                )],
            ]),
        )

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

    @app.router.callback_query(F.data.startswith("recipes:edit:"))
    async def edit_menu(call):
        if not await app._check_chat_and_respond(call):
            return
        try:
            parts = str(call.data).split(":")
            if len(parts) not in (4, 5):
                raise ValueError("invalid editor callback")
            _, _, name, version = parts[:4]
            page = int(parts[4]) if len(parts) == 5 else 0
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
        try:
            markup = editor_page(rows, name=name, version=int(version), page=page)
        except ValueError as exc:
            await call.answer(str(exc)[:150], show_alert=True)
            return
        await call.answer()
        await call.message.answer(
            "Изменение уставок создаст новую версию (В/А).",
            reply_markup=markup,
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
