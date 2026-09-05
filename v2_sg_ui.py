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
from sg_policy_v2 import (
    HydrometerMode,
    SGAccess,
    SGCorrectionProfile,
    SGMeasurementMetadata,
    corrected_specific_gravity,
    get_sg_access,
    record_sg_measurement_metadata,
    set_sg_access,
)
from v2_battery_catalog import list_batteries


@dataclass(frozen=True)
class ParsedSGInput:
    cells: Tuple[Optional[float], Optional[float], Optional[float], Optional[float], Optional[float], Optional[float]]
    temperature_c: Optional[float]
    context: str
    notes: str
    hydrometer_mode: HydrometerMode = HydrometerMode.UNKNOWN
    correction_profile: SGCorrectionProfile = SGCorrectionProfile.RAW_ONLY


_pending_sg_battery: Dict[int, Any] = {}
_sg_catalog: Dict[int, list[Any]] = {}
_installed = False


def _parse_hydrometer_mode(value: str) -> HydrometerMode:
    raw = str(value).strip().lower().replace("-", "_")
    aliases = {
        "unknown": HydrometerMode.UNKNOWN,
        "?": HydrometerMode.UNKNOWN,
        "raw": HydrometerMode.RAW,
        "plain": HydrometerMode.RAW,
        "manual": HydrometerMode.RAW,
        "tc": HydrometerMode.TEMPERATURE_COMPENSATED,
        "atc": HydrometerMode.TEMPERATURE_COMPENSATED,
        "temperature_compensated": HydrometerMode.TEMPERATURE_COMPENSATED,
        "temp_compensated": HydrometerMode.TEMPERATURE_COMPENSATED,
    }
    try:
        return aliases[raw]
    except KeyError as exc:
        raise ValueError("hydrometer: raw, tc или unknown") from exc


def _parse_correction_profile(value: str) -> SGCorrectionProfile:
    raw = str(value).strip().lower().replace("-", "_")
    aliases = {
        "raw": SGCorrectionProfile.RAW_ONLY,
        "none": SGCorrectionProfile.RAW_ONLY,
        "raw_only": SGCorrectionProfile.RAW_ONLY,
        "trojan": SGCorrectionProfile.TROJAN_80F,
        "trojan80": SGCorrectionProfile.TROJAN_80F,
        "trojan_80f": SGCorrectionProfile.TROJAN_80F,
        "rolls": SGCorrectionProfile.ROLLS_25C,
        "rolls25": SGCorrectionProfile.ROLLS_25C,
        "rolls_25c": SGCorrectionProfile.ROLLS_25C,
    }
    try:
        return aliases[raw]
    except KeyError as exc:
        raise ValueError("profile: raw, trojan80 или rolls25") from exc


def parse_sg_input(text: str) -> ParsedSGInput:
    """Parse `six cells ; t=25 ; context=... ; hydrometer=... ; profile=...`.

    Use `-`/`x`/`na` for an inaccessible cell. Decimal comma is accepted inside
    numeric fields. Raw values are always preserved. Software temperature correction
    is only authorized by an explicit raw-hydrometer + named-profile combination.
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
    hydrometer_mode = HydrometerMode.UNKNOWN
    correction_profile = SGCorrectionProfile.RAW_ONLY
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
        elif lower.startswith(("hydrometer=", "meter=")):
            hydrometer_mode = _parse_hydrometer_mode(section.split("=", 1)[1])
        elif lower.startswith(("profile=", "correction=")):
            correction_profile = _parse_correction_profile(section.split("=", 1)[1])
        else:
            # Free trailing text is useful as operator context rather than rejected.
            notes = f"{notes}; {section}".strip("; ")

    if hydrometer_mode is HydrometerMode.TEMPERATURE_COMPENSATED and correction_profile is not SGCorrectionProfile.RAW_ONLY:
        raise ValueError("для температурно-компенсированного ареометра software profile не нужен")
    if correction_profile is not SGCorrectionProfile.RAW_ONLY:
        if hydrometer_mode is not HydrometerMode.RAW:
            raise ValueError("manufacturer profile разрешён только с hydrometer=raw")
        if temp is None:
            raise ValueError("для manufacturer profile нужна температура электролита t=...")

    return ParsedSGInput(
        cells=tuple(cells),  # type: ignore[arg-type]
        temperature_c=temp,
        context=context,
        notes=notes,
        hydrometer_mode=hydrometer_mode,
        correction_profile=correction_profile,
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


def _access_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Банки доступны", callback_data="v2_sg_access_serviceable")],
            [InlineKeyboardButton(text="🚫 Банки недоступны", callback_data="v2_sg_access_inaccessible")],
            [InlineKeyboardButton(text="⬅ Назад", callback_data="v2_sg_menu")],
        ]
    )


def _format_assessment(
    measurement: SpecificGravityMeasurement,
    metadata: SGMeasurementMetadata,
) -> str:
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

    corrected = []
    for value in measurement.cells:
        if value is None:
            corrected.append(None)
            continue
        corrected.append(
            corrected_specific_gravity(
                value,
                temperature_c=measurement.temperature_c,
                hydrometer_mode=metadata.hydrometer_mode,
                correction_profile=metadata.correction_profile,
            )
        )
    if any(value is not None for value in corrected):
        corrected_text = "  ".join(
            f"{idx}:{value:.3f}" if value is not None else f"{idx}:—"
            for idx, value in enumerate(corrected, start=1)
        )
        if metadata.hydrometer_mode is HydrometerMode.TEMPERATURE_COMPENSATED:
            correction_line = f"\nАреометр: температурно-компенсированный; reported SG: {corrected_text}"
        else:
            correction_line = (
                f"\nExplicit correction <code>{metadata.correction_profile.value}</code>: "
                f"{corrected_text}"
            )
    else:
        correction_line = "\nТемпературная software-коррекция не применялась; сохранены raw SG."

    return (
        f"<b>🧪 Плотность сохранена</b>\n"
        f"<code>{html.escape(measurement.battery_id)}</code>\n"
        f"raw: {cells}\n"
        f"spread = <b>{spread}</b>; низкие outlier-банки: <b>{outliers}</b>"
        f"{correction_line}\n"
        f"Статус: {html.escape(interpretation)}.\n\n"
        "Один SG-замер не объявляется КЗ банки. Широкий разброс после полного заряда — "
        "evidence дисбаланса/стратификации и повод для manufacturer-appropriate corrective cycle + retest."
    )


def install_sg_ui(app: Any) -> None:
    global _installed
    if _installed:
        return
    _installed = True

    async def _ask_measurement(call: Any, record: Any) -> None:
        user_id = call.from_user.id if call.from_user else 0
        _pending_sg_battery[user_id] = record
        chemistry = record.identity.chemistry
        warning = ""
        if chemistry is BatteryChemistry.EFB:
            warning = "\nEFB: SG разрешён только потому, что для этой физической АКБ вы подтвердили доступ к банкам."
        await call.message.answer(
            "<b>Введите 6 значений одним сообщением</b>\n"
            "Пример raw-замера без software-коррекции:\n"
            "<code>1.275 1.272 1.270 1.180 1.274 1.271; t=25; context=post_charge; hydrometer=raw</code>\n\n"
            "Если нужен явный manufacturer profile:\n"
            "<code>...; t=25; hydrometer=raw; profile=trojan80</code>\n"
            "или <code>profile=rolls25</code>.\n"
            "Температурно-компенсированный прибор: <code>hydrometer=tc</code> без profile.\n\n"
            "Недоступная отдельная банка: <code>-</code>. Можно добавить <code>note=...</code>.\n"
            "Профиль никогда не выбирается автоматически по названию производителя."
            + warning,
            parse_mode=ParseMode.HTML,
        )

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
                "Нет сохранённых не-AGM АКБ для побаночного SG. Для AGM ввод плотности не предлагается."
            )
            return
        await call.message.answer(
            "<b>🧪 Побаночная плотность</b>\n"
            "Выберите физическую АКБ. Если доступ к банкам ещё не подтверждён, V2 сначала спросит это отдельно:",
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
        if record.identity.chemistry is BatteryChemistry.AGM:
            await call.message.answer("AGM: побаночный SG не применяется.")
            return

        access = await get_sg_access(record.identity.battery_id)
        if access is SGAccess.SERVICEABLE:
            await _ask_measurement(call, record)
            return

        _pending_sg_battery[user_id] = record
        if access is SGAccess.INACCESSIBLE:
            await call.message.answer(
                "Для этой физической АКБ сохранено: банки недоступны. SG не запрашивается.\n"
                "Если конструкция/АКБ изменилась, статус можно явно переопределить:",
                reply_markup=_access_keyboard(),
            )
            return

        await call.message.answer(
            "Доступ к электролиту для этой физической АКБ ещё не подтверждён.\n"
            "Не ориентируемся только на надпись EFB/Ca/Flooded — подтвердите фактическую конструкцию:",
            reply_markup=_access_keyboard(),
        )

    @app.router.callback_query(F.data == "v2_sg_access_serviceable")
    async def sg_access_serviceable(call: Any) -> None:
        if not await app._check_chat_and_respond(call):
            return
        user_id = call.from_user.id if call.from_user else 0
        record = _pending_sg_battery.get(user_id)
        if record is None:
            await call.answer("Выбор АКБ устарел", show_alert=True)
            return
        if record.identity.chemistry is BatteryChemistry.AGM:
            await call.answer("AGM не поддерживает побаночный SG", show_alert=True)
            return
        await set_sg_access(record.identity.battery_id, SGAccess.SERVICEABLE, updated_at=time.time())
        await call.answer("Доступ к банкам сохранён")
        await _ask_measurement(call, record)

    @app.router.callback_query(F.data == "v2_sg_access_inaccessible")
    async def sg_access_inaccessible(call: Any) -> None:
        if not await app._check_chat_and_respond(call):
            return
        user_id = call.from_user.id if call.from_user else 0
        record = _pending_sg_battery.get(user_id)
        if record is None:
            await call.answer("Выбор АКБ устарел", show_alert=True)
            return
        await set_sg_access(record.identity.battery_id, SGAccess.INACCESSIBLE, updated_at=time.time())
        _pending_sg_battery.pop(user_id, None)
        await call.answer("Сохранено")
        await call.message.answer(
            "🚫 Побаночный SG для этой физической АКБ отключён: электролит недоступен. "
            "Отсутствие SG не повышает fault score."
        )

    installed_dialog = app.handle_dialog_mode

    async def sg_aware_dialog(message: Any) -> None:
        user_id = message.from_user.id if message.from_user else 0
        record = _pending_sg_battery.get(user_id)
        if record is None:
            await installed_dialog(message)
            return
        access = await get_sg_access(record.identity.battery_id)
        if access is not SGAccess.SERVICEABLE:
            await message.answer("SG не принимается, пока доступ к банкам не подтверждён как SERVICEABLE.")
            return
        try:
            parsed = parse_sg_input(message.text or "")
            measured_at = time.time()
            measurement = SpecificGravityMeasurement.from_iterable(
                battery_id=record.identity.battery_id,
                measured_at=measured_at,
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
                "Формат: <code>SG1 SG2 SG3 SG4 SG5 SG6; t=25; context=...; hydrometer=raw</code>",
                parse_mode=ParseMode.HTML,
            )
            return

        metadata = SGMeasurementMetadata(
            battery_id=measurement.battery_id,
            measured_at=measurement.measured_at,
            hydrometer_mode=parsed.hydrometer_mode,
            correction_profile=parsed.correction_profile,
        )
        metadata_warning = ""
        try:
            await record_sg_measurement_metadata(metadata)
        except Exception as exc:
            # The raw SG measurement is the primary durable evidence. Losing optional
            # metadata must not make the operator retry and accidentally duplicate it.
            metadata_warning = f"\n⚠️ metadata correction policy не сохранена: {html.escape(str(exc))}"

        _pending_sg_battery.pop(user_id, None)
        await message.answer(
            _format_assessment(measurement, metadata) + metadata_warning,
            parse_mode=ParseMode.HTML,
        )

    app.handle_dialog_mode = sg_aware_dialog
