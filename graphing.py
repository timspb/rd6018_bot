"""
graphing.py — построение графика U/I во времени (dark theme).
"""
import io
import logging
from datetime import datetime, time
from typing import List, Optional, Union

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.dates import DateFormatter

logger = logging.getLogger("rd6018")


def _to_float_list(data: List) -> List[float]:
    """Преобразовать все элементы в float (защита от categorical units)."""
    out: List[float] = []
    for x in data:
        try:
            out.append(float(x))
        except (TypeError, ValueError):
            out.append(0.0)
    return out


def _parse_timestamps(times: List[str]) -> List[datetime]:
    """Преобразовать строки времени (ISO или HH:MM:SS) в datetime."""
    result: List[datetime] = []
    base_date = datetime.now().date()
    for ts in times:
        if not ts or not isinstance(ts, str):
            result.append(datetime.now())
            continue
        try:
            if "T" in ts:
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00")[:19])
            else:
                parts = ts.split(":")
                if len(parts) >= 2:
                    h, m = int(parts[0]), int(parts[1])
                    s = int(parts[2]) if len(parts) >= 3 else 0
                    dt = datetime.combine(base_date, time(h, m, s))
                else:
                    dt = datetime.now()
            result.append(dt)
        except (ValueError, TypeError):
            result.append(datetime.now())
    return result


def generate_chart(
    times: List[str],
    voltages: List[float],
    currents: List[float],
) -> Optional[io.BytesIO]:
    """
    Построить dual-axis график U/I.
    Стиль: тёмный фон (#1e1e1e), X — время (HH:MM), Y1 — напряжение (Cyan), Y2 — ток (Yellow).
    Возвращает BytesIO или None при ошибке.
    """
    if not times or not voltages or not currents:
        return None

    v_list = _to_float_list(voltages)
    i_list = _to_float_list(currents)
    n = min(len(times), len(v_list), len(i_list))
    if n == 0:
        return None

    times_parsed = _parse_timestamps(times[:n])
    v_list = v_list[:n]
    i_list = i_list[:n]

    try:
        plt.style.use("dark_background")
        fig, ax1 = plt.subplots(figsize=(8, 4), facecolor="#1e1e1e")
        ax1.set_facecolor("#1e1e1e")

        ax1.plot(times_parsed, v_list, color="#00ffff", label="Voltage (V)", linewidth=1.5)
        ax1.set_xlabel("Время", color="#fff")
        ax1.set_ylabel("Voltage (V)", color="#00ffff")
        ax1.xaxis.set_major_formatter(DateFormatter("%H:%M"))
        ax1.tick_params(axis="x", colors="#fff", labelsize=8)
        ax1.tick_params(axis="y", colors="#00ffff")
        ax1.set_ylim(bottom=0)

        ax2 = ax1.twinx()
        ax2.plot(times_parsed, i_list, color="#ffff00", label="Current (A)", linewidth=1.5)
        ax2.set_ylabel("Current (A)", color="#ffff00")
        ax2.tick_params(axis="y", colors="#ffff00")
        ax2.set_ylim(bottom=0)

        fig.legend(loc="upper right", fontsize=8)
        fig.autofmt_xdate()
        fig.tight_layout()

        buf = io.BytesIO()
        fig.savefig(buf, format="png", facecolor=fig.get_facecolor(), bbox_inches="tight")
        plt.close(fig)
        buf.seek(0)
        return buf
    except Exception as ex:
        logger.error("generate_chart failed: %s", ex)
        plt.close("all")
        return None


def create_chart(
    times: List[Union[str, float]],
    voltages: List[Union[float, int]],
    currents: List[Union[float, int]],
) -> Optional[io.BytesIO]:
    """
    Алиас для generate_chart. Конвертирует строки времени в HH:MM при необходимости.
    """
    ts_str: List[str] = []
    for t in times:
        if isinstance(t, str):
            ts_str.append(t[-8:] if len(t) >= 8 else t)
        else:
            ts_str.append(str(t))
    return generate_chart(ts_str, list(voltages), list(currents))
