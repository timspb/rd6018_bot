"""Telegram callbacks for mutable, versioned copies of native recipes."""
from __future__ import annotations

import html
from decimal import Decimal
from uuid import uuid4

from aiogram import F
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from runtime.charge.programs.native_recipe_catalog import get_native_recipe
from runtime.charge.programs.native_recipe_draft import validate_native_draft
from runtime.charge.programs.native_recipe_draft_library import NativeRecipeDraftLibrary
from runtime.charge.programs.native_recipe_parameters import native_recipe_parameters
from runtime.charge.programs.native_recipe_session import require_supported_native_execution
from runtime.config.variable_spec import OverridePolicy
from runtime.ui.telegram.recipe_menu_view import native_catalog_page, native_history_page, native_summary


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


def install_native_draft_buttons(app, native_drafts: NativeRecipeDraftLibrary) -> None:
    """Register native draft routes on the existing Telegram router."""
    @app.router.callback_query(F.data.startswith("recipes:nd:list"))
    async def native_draft_list(call):
        if not await app._check_chat_and_respond(call):
            return
        try:
            parts = str(call.data).split(":")
            if len(parts) not in (3, 4) or parts[:3] != ["recipes", "nd", "list"]:
                raise ValueError("Некорректная страница библиотеки")
            page = int(parts[3]) if len(parts) == 4 else 0
            markup, count, pages = native_catalog_page(native_drafts, page)
        except (ValueError, OSError) as exc:
            await call.answer(str(exc)[:120], show_alert=True)
            return
        await call.answer()
        await call.message.answer(
            f"Мои копии штатных рецептов · {count} шт. · страница {page + 1}/{pages}."
            " Изменения не активируют зарядку.",
            reply_markup=markup,
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
            latest = versions[-1]
            message_text = native_summary(
                name, version, draft, archived=archived, latest=latest)
            rows = []
            if version != latest:
                key = f"recipes:nd:view:{name}:{latest}"
                if len(key.encode("utf-8")) <= 64:
                    rows.append([InlineKeyboardButton(
                        text=f"◀ К актуальной v{latest}", callback_data=key)])
            if len(versions) > 1:
                history = f"recipes:nd:history:{name}:0"
                if len(history.encode("utf-8")) <= 64:
                    rows.append([InlineKeyboardButton(
                        text=f"История · {len(versions)} версий", callback_data=history)])
            if not archived and version == latest:
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
            message_text,
            parse_mode=app.ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        )

    @app.router.callback_query(F.data.startswith("recipes:nd:history:"))
    async def native_draft_history(call):
        if not await app._check_chat_and_respond(call):
            return
        try:
            _, _, _, name, raw_page = str(call.data).split(":")
            page = int(raw_page)
            markup, pages = native_history_page(native_drafts, name, page)
        except (ValueError, FileNotFoundError, OSError) as exc:
            await call.answer(str(exc)[:120], show_alert=True)
            return
        await call.answer()
        await call.message.answer(
            f"<b>История · {html.escape(name)}</b>\n"
            f"Страница {page + 1}/{pages} · все версии только для просмотра.",
            parse_mode=app.ParseMode.HTML,
            reply_markup=markup)

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
            total_pages = max(1, (len(specs) + page_size - 1) // page_size)
            lines = [f"<b>Настройка · {html.escape(name)} v{version}</b>",
                     f"Страница {page + 1}/{total_pages} · каждое изменение сохраняет новую версию.",
                     "Команды зарядки не отправляются."]
            rows = []
            for index in range(page * page_size, min((page + 1) * page_size, len(specs))):
                spec = specs[index]
                value = dict(draft.overrides).get(spec.key, spec.default)
                lines.append(f"• {html.escape(spec.description)}: "
                             f"<b>{html.escape(str(value))} {html.escape(spec.unit)}</b>"
                             + (" (изменено)" if spec.key in dict(draft.overrides) else " (по умолчанию)"))
                buttons = []
                for direction, label in (("down", "−"), ("up", "+")):
                    data = f"recipes:nd:adjust:{name}:{version}:{index}:{direction}"
                    if len(data.encode("utf-8")) <= 64:
                        buttons.append(InlineKeyboardButton(
                            text=f"{label} {spec.description[:20]}", callback_data=data))
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
            details = f"recipes:nd:view:{name}:{version + 1}"
            if len(details.encode("utf-8")) <= 64:
                rows.append([InlineKeyboardButton(
                    text="◀ К копии", callback_data=details)])
        except (ValueError, KeyError, FileNotFoundError, FileExistsError, OSError) as exc:
            await call.answer(str(exc)[:120], show_alert=True)
            return
        await call.answer()
        await call.message.answer(
            f"<b>{html.escape(name)} · v{version + 1}</b>\n"
            f"{html.escape(spec.description)}: <b>{html.escape(str(value))} "
            f"{html.escape(spec.unit)}</b>\n"
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
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text="⚙️ Открыть копию",
                    callback_data=f"recipes:nd:view:{name}:1",
                )],
                [InlineKeyboardButton(
                    text="Мои копии", callback_data="recipes:nd:list",
                )],
            ]),
        )
