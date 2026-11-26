"""Telegram callbacks for the read-only built-in native recipe catalog."""
from __future__ import annotations

import html

from aiogram import F
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from runtime.charge.programs.native_recipe_catalog import get_native_recipe
from runtime.charge.programs.native_recipe_parameters import native_recipe_parameters
from runtime.ui.telegram.recipe_menu_view import native_recipe_markup


def install_native_recipe_catalog_buttons(app) -> None:
    """Register native catalog routes on the existing shared application router."""
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
