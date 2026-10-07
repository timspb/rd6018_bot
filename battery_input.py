from __future__ import annotations

from typing import List

from pb_domain import BatteryChemistry, BatteryCondition, BatteryIdentity, BatteryLifecycle


def _parse_chemistry(value: str) -> BatteryChemistry:
    raw = str(value).strip().lower().replace(" ", "").replace("-", "_")
    aliases = {
        "agm": BatteryChemistry.AGM,
        "efb": BatteryChemistry.EFB,
        "ca": BatteryChemistry.CA_CA,
        "caca": BatteryChemistry.CA_CA,
        "ca/ca": BatteryChemistry.CA_CA,
        "ca_ca": BatteryChemistry.CA_CA,
        "flooded": BatteryChemistry.FLOODED,
        "liquid": BatteryChemistry.FLOODED,
    }
    try:
        return aliases[raw]
    except KeyError as exc:
        raise ValueError("тип должен быть AGM, EFB, Ca/Ca или Flooded") from exc


def _split_spec(text: str) -> List[str]:
    """Split a battery spec while keeping ordinary Telegram input convenient.

    Preferred forms are whitespace or comma separated.  The historical pipe form is
    kept for compatibility.  Semicolon is accepted as another unambiguous delimiter.

    Whitespace grammar uses ``split(maxsplit=4)`` so the model field may contain
    spaces: ``id AGM 70 Varta Silver Dynamic AGM``.
    """
    raw = str(text or "").strip()
    if not raw:
        return []

    delimiter = None
    if "|" in raw:
        delimiter = "|"
    elif ";" in raw:
        delimiter = ";"
    elif raw.count(",") >= 2:
        # One comma may legitimately be a decimal separator in whitespace mode.
        delimiter = ","

    if delimiter is None:
        return raw.split(None, 4)

    parts = [part.strip() for part in raw.split(delimiter)]
    if len(parts) > 5:
        # Preserve delimiter text inside a long model name rather than discarding it.
        parts = parts[:4] + [delimiter.join(parts[4:]).strip()]
    return parts


def parse_battery_spec(text: str) -> tuple[BatteryIdentity, BatteryLifecycle]:
    """Parse ``ID chemistry Ah [manufacturer] [model]`` from natural one-line input."""
    parts = _split_spec(text)
    if len(parts) < 3:
        raise ValueError(
            "формат: ID AGM/EFB/Ca/Ca Ah [производитель] [модель]; "
            "разделитель — пробел или запятая"
        )

    battery_id = parts[0]
    if not battery_id or len(battery_id) > 64:
        raise ValueError("ID обязателен и должен быть короче 65 символов")

    chemistry = _parse_chemistry(parts[1])
    capacity_raw = parts[2].strip().lower()
    if capacity_raw.endswith("ah"):
        capacity_raw = capacity_raw[:-2].strip()
    try:
        capacity = float(capacity_raw.replace(",", "."))
    except ValueError as exc:
        raise ValueError("ёмкость Ah должна быть числом") from exc
    if capacity <= 0 or capacity > 1000:
        raise ValueError("ёмкость должна быть в диапазоне 0..1000 Ah")

    manufacturer = parts[3] if len(parts) >= 4 else ""
    model = parts[4] if len(parts) >= 5 else ""
    identity = BatteryIdentity(
        battery_id=battery_id,
        chemistry=chemistry,
        nominal_capacity_ah=capacity,
        manufacturer=manufacturer,
        model=model,
    )
    return identity, BatteryLifecycle(condition=BatteryCondition.UNKNOWN)
