"""Pure parsers for the production Telegram free-text input grammars."""

from typing import Any, Callable, Dict, Optional


def parse_off_command(
    text: str,
    *,
    max_stage_current: float,
    clock: Callable[[], float],
) -> Optional[Dict[str, Any]]:
    """Parse the existing OFF-condition grammar without owning its clock."""
    t = (text or "").strip().replace(",", ".")
    if not t.lower().startswith("off "):
        return None
    rest = t[4:].strip().replace("\u2265", ">=").replace("\u2264", "<=")  # ≥ ≤
    if not rest:
        return None
    tokens = rest.lower().split()
    voltage_ge: Optional[float] = None
    voltage_le: Optional[float] = None
    current_le: Optional[float] = None
    current_ge: Optional[float] = None
    time_sec: Optional[float] = None
    parts: list = []

    for tok in tokens:
        if ":" in tok:
            try:
                comp = tok.split(":")
                if len(comp) == 2:
                    h, m = int(comp[0].strip()), int(comp[1].strip())
                    sec = h * 3600 + m * 60
                elif len(comp) == 3:
                    h, m, s = int(comp[0].strip()), int(comp[1].strip()), int(comp[2].strip())
                    sec = h * 3600 + m * 60 + s
                else:
                    continue
                if sec <= 0:
                    continue
                time_sec = (time_sec or 0) + sec
                parts.append(f"таймер {tok}")
            except (ValueError, IndexError):
                continue
        elif tok.startswith("v>="):
            try:
                voltage_ge = float(tok[3:].strip())
                if 0 <= voltage_ge <= 20:
                    parts.append(f"V≥{voltage_ge:.1f} В")
            except ValueError:
                continue
        elif tok.startswith("v<="):
            try:
                voltage_le = float(tok[3:].strip())
                if 0 <= voltage_le <= 20:
                    parts.append(f"V≤{voltage_le:.1f} В")
            except ValueError:
                continue
        elif tok.startswith("i>="):
            try:
                current_ge = float(tok[3:].strip())
                if 0 < current_ge <= max_stage_current:
                    parts.append(f"I≥{current_ge:.2f} А")
            except ValueError:
                continue
        elif tok.startswith("i<="):
            try:
                current_le = float(tok[3:].strip())
                if 0 < current_le <= max_stage_current:
                    parts.append(f"I≤{current_le:.2f} А")
            except ValueError:
                continue
        else:
            try:
                val = float(tok)
                if 12.0 <= val <= 18.0:
                    voltage_ge = val
                    parts.append(f"{val:.1f} В (V≥)")
                elif 0.1 <= val <= max_stage_current:
                    current_le = val
                    parts.append(f"{val:.2f} А (I≤)")
                else:
                    continue
            except ValueError:
                continue

    if voltage_ge is None and voltage_le is None and current_le is None and current_ge is None and time_sec is None:
        return None
    return {
        "voltage_ge": voltage_ge,
        "voltage_le": voltage_le,
        "current_le": current_le,
        "current_ge": current_ge,
        "time_sec": time_sec,
        "start_time": clock(),
        "parts": parts,
    }


def parse_three_values(
    text: str, *, max_stage_current: float
) -> Optional[Dict[str, Any]]:
    """Parse V, I and the existing timer/current/voltage OFF condition."""
    parts = (text or "").strip().replace(",", ".").split()
    if len(parts) != 3:
        return None
    try:
        v = float(parts[0])
        i = float(parts[1])
        third = parts[2].strip().upper().rstrip("AАВV")
        if not third:
            return None
        if ":" in parts[2]:
            comp = parts[2].split(":")
            if len(comp) == 2:
                h, m = int(comp[0].strip()), int(comp[1].strip())
                time_sec = h * 3600 + m * 60
            elif len(comp) == 3:
                h, m, s = int(comp[0].strip()), int(comp[1].strip()), int(comp[2].strip())
                time_sec = h * 3600 + m * 60 + s
            else:
                return None
            if time_sec <= 0:
                return None
            return {"v": v, "i": i, "time_sec": time_sec}
        raw3 = parts[2].strip().replace(",", ".")
        last_char = (raw3[-1].upper() if len(raw3) > 1 else "")
        if last_char in ("A", "А"):
            val = float(third)
            if 0.1 <= val <= max_stage_current:
                return {"v": v, "i": i, "off_current": val}
            return None
        if last_char in ("V", "В"):
            val = float(third)
            if 0 <= val <= 20.0:
                return {"v": v, "i": i, "off_voltage": val}
            return None
    except (ValueError, IndexError):
        pass
    return None


def parse_two_numbers(text: str) -> Optional[tuple]:
    """Parse two numeric values using the current production grammar."""
    parts = (text or "").strip().replace(",", ".").split()
    if len(parts) != 2:
        return None
    try:
        v = float(parts[0])
        i = float(parts[1])
        return (v, i)
    except ValueError:
        return None
