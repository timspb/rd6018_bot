"""Pure, non-actuating Telegram Recipe Studio menu presentation.

The existing recipe libraries own persistence and versioning. Callback routing,
operator ACL and session/charge ownership remain in recipe_buttons.py.
"""
from __future__ import annotations

import html

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from runtime.charge.programs.native_recipe_parameters import native_recipe_parameters


STEP_VIEW_PAGE_SIZE = 8


def step_summary(recipe, *, archived: bool, latest: int,
                 page: int = 0, page_size: int = STEP_VIEW_PAGE_SIZE) -> str:
    """Human-readable bounded page of steps, never truncate an open HTML tag."""
    pages = (len(recipe.steps) + page_size - 1) // page_size if page_size > 0 else 0
    if not 0 <= page < pages:
        raise ValueError("Недоступная страница шагов")
    lines = [f"<b>Пошаговый рецепт · {html.escape(recipe.recipe_id)} v{recipe.version}</b>",
             "Архив · только просмотр" if archived else
             ("Текущая версия" if recipe.version == latest
              else f"Историческая версия · актуальна v{latest}")]
    predicates = {
        "after_seconds": ("Через", "с"),
        "voltage_gte": ("U ≥", "В"), "voltage_lte": ("U ≤", "В"),
        "current_gte": ("I ≥", "А"), "current_lte": ("I ≤", "А"),
        "temperature_gte": ("T ≥", "°C"), "temperature_lte": ("T ≤", "°C"),
    }
    lines.append(f"Шаги {page * page_size + 1}–"
                 f"{min((page + 1) * page_size, len(recipe.steps))} из {len(recipe.steps)}"
                 f" · страница {page + 1}/{pages}")
    for number in range(page * page_size, min((page + 1) * page_size, len(recipe.steps))):
        step = recipe.steps[number]
        action = step["action"]
        params = step["params"]
        description = (f"SET · U {params['voltage_v']:g} В · I {params['current_a']:g} А"
                       if action == "set" else
                       "OFF · выход выключен" if action == "off"
                       else "WAIT · ожидание после OFF")
        predicate, target = next(iter(step["until"].items()))
        condition, unit = predicates[predicate]
        lines.append(f"{number + 1}. <b>{html.escape(description)}</b> → "
                     f"{condition} {target:g} {unit}")
    lines.append("Просмотр не запускает зарядку.")
    return "\n".join(lines)


def native_summary(name: str, version: int, draft, *, archived: bool, latest: int) -> str:
    """Summarize overrides using the original module-owned VariableSpec metadata."""
    lines = [f"<b>{html.escape(name)} · v{version}</b>",
             f"Основа: <code>{html.escape(draft.base_recipe_id)}</code>",
             "Статус: архив · только просмотр" if archived
             else ("Статус: текущая версия" if version == latest
                   else f"Статус: историческая версия · актуальна v{latest}")]
    specs = {spec.key: spec for spec in native_recipe_parameters(draft.base_recipe_id)}
    if draft.overrides:
        lines.append("<b>Изменённые параметры:</b>")
        for key, value in draft.overrides:
            spec = specs.get(key)
            label = spec.description if spec is not None else key
            unit = spec.unit if spec is not None else ""
            lines.append(f"• {html.escape(label)}: <b>{html.escape(str(value))}"
                         f" {html.escape(unit)}</b>")
    else:
        lines.append("Изменений относительно основы нет.")
    lines.append("Выбор версии не запускает зарядку.")
    return "\n".join(lines)[:3600]


def native_catalog_page(library, page: int, *, page_size: int = 12):
    """Single bounded menu containing active first, archived afterward."""
    entries = []
    for name in library.list_drafts():
        versions = library.versions(name)
        if not versions:
            continue
        command = f"recipes:nd:view:{name}:{versions[-1]}"
        if len(command.encode("utf-8")) <= 64:
            archived = (library.root / name / ".archived").exists()
            entries.append((name, versions[-1], command, archived))
    entries.sort(key=lambda item: (item[3], item[0]))
    pages = max(1, (len(entries) + page_size - 1) // page_size)
    if not 0 <= page < pages:
        raise ValueError("Страница библиотеки недоступна")
    rows = []
    for name, version, command, archived in entries[page * page_size:(page + 1) * page_size]:
        rows.append([InlineKeyboardButton(
            text=f"{name} · v{version}" + (" [архив]" if archived else ""),
            callback_data=command)])
    navigation = []
    for target, label in ((page - 1, "◀"), (page + 1, "▶")):
        if 0 <= target < pages:
            navigation.append(InlineKeyboardButton(
                text=label, callback_data=f"recipes:nd:list:{target}"))
    if navigation:
        rows.append(navigation)
    rows.append([InlineKeyboardButton(
        text="К штатным программам", callback_data="recipes:native:list")])
    rows.append([InlineKeyboardButton(
        text="К библиотеке", callback_data="recipes:list")])
    return InlineKeyboardMarkup(inline_keyboard=rows), len(entries), pages


def native_history_page(library, name: str, page: int, *, page_size: int = 6):
    """Reach every immutable version, not only first/last shortcuts."""
    versions = tuple(reversed(library.versions(name)))
    pages = (len(versions) + page_size - 1) // page_size
    if not versions or not 0 <= page < pages:
        raise ValueError("История не найдена")
    rows = []
    for version in versions[page * page_size:(page + 1) * page_size]:
        key = f"recipes:nd:view:{name}:{version}"
        if len(key.encode("utf-8")) <= 64:
            rows.append([InlineKeyboardButton(text=f"Версия {version}", callback_data=key)])
    navigation = []
    for target, label in ((page - 1, "◀ Назад"), (page + 1, "Далее ▶")):
        if 0 <= target < pages:
            key = f"recipes:nd:history:{name}:{target}"
            if len(key.encode("utf-8")) <= 64:
                navigation.append(InlineKeyboardButton(text=label, callback_data=key))
    if navigation:
        rows.append(navigation)
    latest = f"recipes:nd:view:{name}:{versions[0]}"
    if len(latest.encode("utf-8")) <= 64:
        rows.append([InlineKeyboardButton(
            text="◀ К актуальной версии", callback_data=latest)])
    rows.append([InlineKeyboardButton(text="Мои копии", callback_data="recipes:nd:list")])
    return InlineKeyboardMarkup(inline_keyboard=rows), pages
