from __future__ import annotations

from typing import List

from battery_diagnostics import DynamicLoopProbe, SpecificGravityMeasurement
from battery_registry import get_battery
from database import get_db


async def init_battery_diagnostics_store() -> None:
    db = await get_db()
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS battery_specific_gravity (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            battery_id TEXT NOT NULL,
            measured_at REAL NOT NULL,
            temperature_c REAL,
            context TEXT NOT NULL DEFAULT '',
            source TEXT NOT NULL DEFAULT 'manual',
            cell_1 REAL,
            cell_2 REAL,
            cell_3 REAL,
            cell_4 REAL,
            cell_5 REAL,
            cell_6 REAL,
            notes TEXT NOT NULL DEFAULT '',
            FOREIGN KEY (battery_id) REFERENCES batteries(battery_id)
        )
        """
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_battery_sg_battery_time "
        "ON battery_specific_gravity(battery_id, measured_at)"
    )
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS battery_dynamic_loop_probes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            battery_id TEXT NOT NULL,
            measured_at REAL NOT NULL,
            stage TEXT NOT NULL DEFAULT '',
            baseline_voltage_v REAL NOT NULL,
            baseline_current_a REAL NOT NULL,
            stepped_voltage_v REAL NOT NULL,
            stepped_current_a REAL NOT NULL,
            dynamic_loop_mohm REAL,
            connection_id TEXT NOT NULL DEFAULT '',
            notes TEXT NOT NULL DEFAULT '',
            FOREIGN KEY (battery_id) REFERENCES batteries(battery_id)
        )
        """
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_dynamic_loop_battery_time "
        "ON battery_dynamic_loop_probes(battery_id, measured_at)"
    )
    await db.commit()


async def record_specific_gravity(measurement: SpecificGravityMeasurement) -> int:
    if await get_battery(measurement.battery_id) is None:
        raise KeyError(f"unknown battery_id: {measurement.battery_id}")
    db = await get_db()
    cursor = await db.execute(
        """
        INSERT INTO battery_specific_gravity (
            battery_id, measured_at, temperature_c, context, source,
            cell_1, cell_2, cell_3, cell_4, cell_5, cell_6, notes
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            measurement.battery_id,
            measurement.measured_at,
            measurement.temperature_c,
            measurement.context,
            measurement.source,
            *measurement.cells,
            measurement.notes,
        ),
    )
    row_id = int(cursor.lastrowid)
    await cursor.close()
    await db.commit()
    return row_id


async def list_specific_gravity(
    battery_id: str,
    *,
    limit: int = 20,
) -> List[SpecificGravityMeasurement]:
    db = await get_db()
    async with db.execute(
        """
        SELECT * FROM battery_specific_gravity
        WHERE battery_id = ?
        ORDER BY measured_at DESC, id DESC
        LIMIT ?
        """,
        (battery_id, max(1, int(limit))),
    ) as cursor:
        rows = await cursor.fetchall()

    result: List[SpecificGravityMeasurement] = []
    for row in reversed(rows):
        result.append(
            SpecificGravityMeasurement.from_iterable(
                battery_id=row["battery_id"],
                measured_at=float(row["measured_at"]),
                temperature_c=(
                    float(row["temperature_c"])
                    if row["temperature_c"] is not None
                    else None
                ),
                context=row["context"] or "",
                source=row["source"] or "manual",
                cells=(
                    row["cell_1"],
                    row["cell_2"],
                    row["cell_3"],
                    row["cell_4"],
                    row["cell_5"],
                    row["cell_6"],
                ),
                notes=row["notes"] or "",
            )
        )
    return result


async def record_dynamic_loop_probe(probe: DynamicLoopProbe) -> int:
    if await get_battery(probe.battery_id) is None:
        raise KeyError(f"unknown battery_id: {probe.battery_id}")
    db = await get_db()
    cursor = await db.execute(
        """
        INSERT INTO battery_dynamic_loop_probes (
            battery_id, measured_at, stage,
            baseline_voltage_v, baseline_current_a,
            stepped_voltage_v, stepped_current_a,
            dynamic_loop_mohm, connection_id, notes
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            probe.battery_id,
            probe.measured_at,
            probe.stage,
            probe.baseline_voltage_v,
            probe.baseline_current_a,
            probe.stepped_voltage_v,
            probe.stepped_current_a,
            probe.dynamic_loop_mohm,
            probe.connection_id,
            probe.notes,
        ),
    )
    row_id = int(cursor.lastrowid)
    await cursor.close()
    await db.commit()
    return row_id


async def list_dynamic_loop_probes(
    battery_id: str,
    *,
    limit: int = 20,
) -> List[DynamicLoopProbe]:
    db = await get_db()
    async with db.execute(
        """
        SELECT * FROM battery_dynamic_loop_probes
        WHERE battery_id = ?
        ORDER BY measured_at DESC, id DESC
        LIMIT ?
        """,
        (battery_id, max(1, int(limit))),
    ) as cursor:
        rows = await cursor.fetchall()

    result: List[DynamicLoopProbe] = []
    for row in reversed(rows):
        result.append(
            DynamicLoopProbe(
                battery_id=row["battery_id"],
                measured_at=float(row["measured_at"]),
                stage=row["stage"] or "",
                baseline_voltage_v=float(row["baseline_voltage_v"]),
                baseline_current_a=float(row["baseline_current_a"]),
                stepped_voltage_v=float(row["stepped_voltage_v"]),
                stepped_current_a=float(row["stepped_current_a"]),
                connection_id=row["connection_id"] or "",
                notes=row["notes"] or "",
            )
        )
    return result
