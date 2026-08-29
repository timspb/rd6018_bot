from __future__ import annotations

import html
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from aiogram import F
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from battery_diagnostics import SpecificGravityMeasurement, assess_specific_gravity
from battery_diagnostics_store import record_specific_gravity
from pb_domain import BatteryChemistry
from v2_battery_catalog import list_batteries


@dataclass(frozen=True)
class ParsedSGInput:
    cells: Tuple[Optional[float], Optional[float], Optional[float], Optional[float], Optional[float], Optional[float]]
    temperature_c: Optional[float]
    context: str
    notes: str


_pending_sg_battery: Dict[int, Any] = {}
_sg_catalog: Dict[int, list[Any]] = {}
_installed = False


def parse_sg_input(text: str) -> ParsedSGInput:
    """Parse `six cells ; t=25 ; context=... ; note=...`.

    Use `-`/`x`/`na` for an inaccessible cell. Decimal comma is accepted inside
    numeric fields. Raw values are preserved; temperature correction is not guessed.
    """
    sections = [part.strip() for part in str(text or "").split(";") if part.strip()]
    if not sections:
        raise ValueError("нужны 6 значений плотности")
    tokens = sections[0].replace(",", ".").split()
    if len(tokens) != 6:
        raise ValueError("первая часть должна содержать ровно 6 банок")
    missing = {"-", "x", "na", "n/a", "нет", "?"}
    cells: list[Optional[float]] = []
    for index, token in enumerate(tokens, start=1):
        if token.lower() in missing:
            cells.append(None)
            continue
        try:
            value = float(token)
        except ValueError as exc:
            raise ValueError(f"банка {index}: неверное число {token!r}") from exc
        cells.append(value)

    temp: Optional[float] = None
    context = "manual"
    notes = ""
    for section in sections[1:]:
        lower = section.lower()
        if lower.startswith(("t=", "temp=", "temperature=")):
            raw = section.split("=", 1)[1].strip().replace(",", ".")
            try:
                temp = float(raw)
            except ValueError as exc:
                raise ValueError("температура должна быть числом") from exc
        elif lower.startswith(("context=", "ctx=")):
            context = section.split("=", 1)[1].strip() or "manual"
        elif lower.startswith(("note=", "notes=")):
            notes = section.split("=", 1)[1].strip()
        else:
            # Free trailing text is useful as operator context rather than rejected.
            notes = f"{notes}; {section}".strip("; ")

    return ParsedSGInput(
        cells=tuple(cells),  # type: ignore[arg-type]
        temperature_c=temp,
        context=context,
        notes=notes,
    )


def sg_menu_button() -> InlineKeyboardButton:
    return InlineKeyboardButton(text="🧪 Плотность по банкам", callback_data="v2_sg_menu")


def _catalog_keyboard(records: list[Any]) -> InlineKeyboardMarkup:
    rows = []
    for index, record in enumerate(records[:20]):
        identity = record.identity
        label = f"{identity.battery_id} · {identity.chemistry.value} · {identity.nominal_capacity_ah:g}Ah"
        rows.append([InlineKeyboardButton(text=label[:60], callback_data=f"v2_sg_pick_{index}")])
    rows.append([InlineKeyboardButton(text="⬅ К программам", callback_data="charge_modes")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _format_assessment(measurement: SpecificGravityMeasurement) -> str:
    assessment = assess_specific_gravity(measurement)
    cells = "  ".join(
        f"{idx}:{value:.3f}" if value is not None else f"{idx}:—"
        for idx, value in enumerate(measurement.cells, start=1)
    )
    spread = "—" if assessment.spread is None else f"{assessment.spread:.3f}"
    outliers = ", ".join(str(i) for i in assessment.low_outlier_cells) or "нет"
    interpretation = {
        "normal": "разброс небольшой",
        "watch": "замер неполный — использовать только как дополнительное evidence",
        "verify": "разброс требует проверки/корректирующего цикла и повторного замера",
        "probable": "выраженная аномалия",
        "high": "выраженная аномалия",
    }.get(assessment.level.value, assessment.level.value)
    return (
        f"<b>🧪 Плотность сохранена</b>\n"
        f"<code>{html.escape(measurement.battery_id)}</code>\n"
        f"{cells}\n"
        f"spread = <b>{spread}</b>; низкие outlier-банки: <b>{outliers}</b>\n"
        f"Статус: {html.escape(interpretation)}.\n\n"
        "Один SG-замер не объявляется КЗ банки. Для flooded широкий разброс может быть "
        "признаком дисбаланса/стратификации и поводом для corrective equalization + retest."
    )


def install_sg_ui(app: Any) -> None:
    global _installed
    if _installed:
        return
    _installed = True

    @app.router.callback_query(F.data == "v2_sg_menu")
    async def sg_menu(call: Any) -> None:
        if not await app._check_chat_and_respond(call):
            return
        await call.answer()
        user_id = call.from_user.id if call.from_user else 0
        records = await list_batteries(limit=50)
        eligible = [
            record
            for record in records
            if record.identity.chemistry is not BatteryChemistry.AGM
        ]
        _sg_catalog[user_id] = eligible[:20]
        if not eligible:
            await call.message.answer(
                "Нет сохранённых обслуживаемых/Flooded/Ca/EFB АКБ для побаночного SG. "
                "Для AGM ввод плотности не предлагается."
            )
            return
        await call.message.answer(
            "<b>🧪 Побаночная плотность</b>\nВыберите физическую АКБ:",
            parse_mode=ParseMode.HTML,
            reply_markup=_catalog_keyboard(eligible),
        )

    @app.router.callback_query(F.data.startswith("v2_sg_pick_"))
    async def sg_pick(call: Any) -> None:
        if not await app._check_chat_and_respond(call):
            return
        user_id = call.from_user.id if call.from_user else 0
        try:
            index = int(str(call.data).rsplit("_", 1)[1])
            record = _sg_catalog[user_id][index]
        except (ValueError, IndexError, KeyError):
            await call.answer("Список устарел — откройте ввод плотности заново", show_alert=True)
            return
        await call.answer()
        _pending_sg_battery[user_id] = record
        chemistry = record.identity.chemistry
        warning = ""
        if chemistry is BatteryChemistry.EFB:
            warning = "\nДля EFB вводить только если конструкция реально даёт безопасный доступ к банкам."
        await call.message.answer(
            "<b>Введите 6 значений одним сообщением</b>\n"
            "Пример:\n"
            "<code>1.275 1.272 1.270 1.180 1.274 1.271; t=25; context=post_charge</code>\n\n"
            "Недоступная банка: <code>-</code>.\n"
            "Можно добавить <code>note=...</code>."
            + warning,
            parse_mode=ParseMode.HTML,
        )

    installed_dialog = app.handle_dialog_mode

    async def sg_aware_dialog(message: Any) -> None:
        user_id = message.from_user.id if message.from_user else 0
        record = _pending_sg_battery.get(user_id)
        if record is None:
            await installed_dialog(message)
            return
        try:
            parsed = parse_sg_input(message.text or "")
            measurement = SpecificGravityMeasurement.from_iterable(
                battery_id=record.identity.battery_id,
                measured_at=time.time(),
                cells=parsed.cells,
                temperature_c=parsed.temperature_c,
                context=parsed.context,
                notes=parsed.notes,
                source="telegram_manual",
            )
            await record_specific_gravity(measurement)
        except Exception as exc:
            await message.answer(
                f"❌ {html.escape(str(exc))}\n"
                "Формат: <code>SG1 SG2 SG3 SG4 SG5 SG6; t=25; context=...</code>",
                parse_mode=ParseMode.HTML,
            )
            return
        _pending_sg_battery.pop(user_id, None)
        await message.answer(_format_assessment(measurement), parse_mode=ParseMode.HTML)

    app.handle_dialog_mode = sg_aware_dialog
