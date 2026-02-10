"""
database.py — асинхронное хранение истории сенсоров и сессий заряда.
"""
import logging
from datetime import datetime, timedelta
from typing import List, Tuple

import aiosqlite

logger = logging.getLogger("rd6018")

DB_PATH = "rd6018.db"


async def init_db() -> None:
    """Создание таблиц при старте."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS sensor_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                voltage REAL,
                current REAL,
                power REAL,
                temp_ext REAL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS charge_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                battery_type TEXT NOT NULL,
                ah_capacity INTEGER NOT NULL,
                start_time TEXT NOT NULL,
                current_stage TEXT,
                status TEXT DEFAULT 'active'
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS charge_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                message_text TEXT
            )
        """)
        await db.commit()
        logger.info("Database initialized: %s", DB_PATH)


async def add_record(v: float, i: float, p: float, t: float) -> None:
    """Добавить запись в sensor_history."""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT INTO sensor_history (timestamp, voltage, current, power, temp_ext) VALUES (?, ?, ?, ?, ?)",
                (datetime.now().isoformat(), v, i, p, t),
            )
            await db.commit()
    except Exception as ex:
        logger.error("add_record failed: %s", ex)


async def get_history(limit: int = 100) -> Tuple[List[str], List[float], List[float]]:
    """
    Получить данные для графика.
    Возвращает (times, voltages, currents), downsampled до limit точек.
    """
    times: List[str] = []
    voltages: List[float] = []
    currents: List[float] = []

    try:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT timestamp, voltage, current FROM sensor_history ORDER BY id DESC LIMIT ?",
                (limit * 3,),  # берём больше, потом downsample
            ) as cursor:
                rows = await cursor.fetchall()

        if not rows:
            return times, voltages, currents

        # reverse чтобы время шло по возрастанию
        rows = list(reversed(rows))

        # Преобразование и type safety
        raw_times: List[str] = []
        raw_v: List[float] = []
        raw_i: List[float] = []
        for r in rows:
            ts = r["timestamp"]
            try:
                v = float(r["voltage"]) if r["voltage"] is not None else 0.0
            except (TypeError, ValueError):
                v = 0.0
            try:
                i = float(r["current"]) if r["current"] is not None else 0.0
            except (TypeError, ValueError):
                i = 0.0
            raw_times.append(ts if ts else "")
            raw_v.append(v)
            raw_i.append(i)

        # Downsample до limit точек
        n = len(raw_times)
        if n <= limit:
            times, voltages, currents = raw_times, raw_v, raw_i
        else:
            step = n / limit
            for idx in range(limit):
                i = int(idx * step)
                if i >= n:
                    break
                times.append(raw_times[i])
                voltages.append(raw_v[i])
                currents.append(raw_i[i])

        return times, voltages, currents
    except Exception as ex:
        logger.error("get_history failed: %s", ex)
        return times, voltages, currents


async def add_charge_log(message: str) -> None:
    """Добавить запись в charge_log."""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT INTO charge_log (timestamp, message_text) VALUES (?, ?)",
                (datetime.now().isoformat(), message),
            )
            await db.commit()
    except Exception as ex:
        logger.error("add_charge_log failed: %s", ex)


async def get_graph_data(limit: int = 100) -> Tuple[List[str], List[float], List[float]]:
    """Алиас для get_history (для совместимости со спецификацией)."""
    return await get_history(limit=limit)


async def get_logs_data(limit: int = 5) -> Tuple[List[str], List[float], List[float], List[float]]:
    """
    Получить последние записи для вывода логов (с temp_ext).
    Возвращает (times, voltages, currents, temps) в хронологическом порядке (от старого к новому).
    """
    times: List[str] = []
    voltages: List[float] = []
    currents: List[float] = []
    temps: List[float] = []

    try:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT timestamp, voltage, current, temp_ext FROM sensor_history ORDER BY id DESC LIMIT ?",
                (limit,),
            ) as cursor:
                rows = await cursor.fetchall()

        if not rows:
            return times, voltages, currents, temps

        rows = list(reversed(rows))
        for r in rows:
            ts = r["timestamp"] if r["timestamp"] else ""
            try:
                v = float(r["voltage"]) if r["voltage"] is not None else 0.0
            except (TypeError, ValueError):
                v = 0.0
            try:
                i = float(r["current"]) if r["current"] is not None else 0.0
            except (TypeError, ValueError):
                i = 0.0
            try:
                t = float(r["temp_ext"]) if r["temp_ext"] is not None else 0.0
            except (TypeError, ValueError):
                t = 0.0
            times.append(ts)
            voltages.append(v)
            currents.append(i)
            temps.append(t)

        return times, voltages, currents, temps
    except Exception as ex:
        logger.error("get_logs_data failed: %s", ex)
        return times, voltages, currents, temps


async def get_raw_history(
    limit: int = 50,
    max_minutes: int = 180,
) -> Tuple[List[str], List[float], List[float]]:
    """
    Получить последние limit записей без даунсемплинга.
    Только за последние max_minutes минут (чтобы не смешивать разные сессии заряда).
    Возвращает (times, voltages, currents) в хронологическом порядке (от старого к новому).
    """
    times: List[str] = []
    voltages: List[float] = []
    currents: List[float] = []

    try:
        since = (datetime.now() - timedelta(minutes=max_minutes)).isoformat()
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """SELECT timestamp, voltage, current FROM sensor_history
                   WHERE timestamp >= ? ORDER BY id DESC LIMIT ?""",
                (since, limit),
            ) as cursor:
                rows = await cursor.fetchall()

        if not rows:
            return times, voltages, currents

        rows = list(reversed(rows))
        for r in rows:
            ts = r["timestamp"] if r["timestamp"] else ""
            try:
                v = float(r["voltage"]) if r["voltage"] is not None else 0.0
            except (TypeError, ValueError):
                v = 0.0
            try:
                i = float(r["current"]) if r["current"] is not None else 0.0
            except (TypeError, ValueError):
                i = 0.0
            times.append(ts)
            voltages.append(v)
            currents.append(i)

        return times, voltages, currents
    except Exception as ex:
        logger.error("get_raw_history failed: %s", ex)
        return times, voltages, currents
