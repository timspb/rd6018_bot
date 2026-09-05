from __future__ import annotations

from typing import List

from battery_registry import BatteryRecord, get_battery, init_battery_registry
from database import get_db


async def list_batteries(*, limit: int = 50) -> List[BatteryRecord]:
    """Return physical batteries ordered by most recently updated.

    The registry remains the storage authority; this small query-oriented adapter keeps
    Telegram/UI concerns out of ``battery_registry.py`` and avoids exposing raw sqlite
    rows to presentation code.
    """

    await init_battery_registry()
    db = await get_db()
    safe_limit = max(1, min(200, int(limit)))
    async with db.execute(
        """
        SELECT battery_id
        FROM batteries
        ORDER BY updated_at DESC, battery_id ASC
        LIMIT ?
        """,
        (safe_limit,),
    ) as cursor:
        rows = await cursor.fetchall()

    records: List[BatteryRecord] = []
    for row in rows:
        record = await get_battery(str(row["battery_id"]))
        if record is not None:
            records.append(record)
    return records
