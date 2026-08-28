from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from database import get_db
from pb_domain import (
    BatteryChemistry,
    BatteryCondition,
    BatteryIdentity,
    BatteryLifecycle,
    ChargeIntent,
)


@dataclass(frozen=True)
class BatteryRecord:
    identity: BatteryIdentity
    lifecycle: BatteryLifecycle


@dataclass(frozen=True)
class RecoveryCycleEvidence:
    battery_id: str
    started_at: float
    intent: ChargeIntent
    condition_before: BatteryCondition = BatteryCondition.UNKNOWN
    completed_at: Optional[float] = None
    main_target_v: Optional[float] = None
    main_imin_a: Optional[float] = None
    main_time_to_target_s: Optional[float] = None
    main_ah_in: Optional[float] = None
    hv_target_v: Optional[float] = None
    hv_imin_a: Optional[float] = None
    hv_time_to_target_s: Optional[float] = None
    hv_reversal_delta_a: Optional[float] = None
    temp_start_c: Optional[float] = None
    temp_max_c: Optional[float] = None
    max_dtemp_c_per_min: Optional[float] = None
    relax_v_5m: Optional[float] = None
    relax_v_15m: Optional[float] = None
    relax_v_1h: Optional[float] = None
    relax_v_12h: Optional[float] = None
    relax_v_24h: Optional[float] = None
    measured_capacity_ah: Optional[float] = None
    cca_a: Optional[float] = None
    internal_resistance_mohm: Optional[float] = None
    outcome: str = ""
    notes: str = ""


async def init_battery_registry() -> None:
    db = await get_db()
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS batteries (
            battery_id TEXT PRIMARY KEY,
            chemistry TEXT NOT NULL,
            nominal_capacity_ah REAL NOT NULL,
            manufacturer TEXT NOT NULL DEFAULT '',
            model TEXT NOT NULL DEFAULT '',
            condition TEXT NOT NULL DEFAULT 'unknown',
            water_added_total_ml REAL NOT NULL DEFAULT 0,
            water_added_per_cell_ml REAL,
            refill_timestamp REAL,
            cycles_since_refill INTEGER,
            measured_capacity_ah REAL,
            cca_a REAL,
            internal_resistance_mohm REAL,
            updated_at REAL NOT NULL
        )
        """
    )
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS recovery_cycles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            battery_id TEXT NOT NULL,
            started_at REAL NOT NULL,
            completed_at REAL,
            intent TEXT NOT NULL,
            condition_before TEXT NOT NULL,
            main_target_v REAL,
            main_imin_a REAL,
            main_time_to_target_s REAL,
            main_ah_in REAL,
            hv_target_v REAL,
            hv_imin_a REAL,
            hv_time_to_target_s REAL,
            hv_reversal_delta_a REAL,
            temp_start_c REAL,
            temp_max_c REAL,
            max_dtemp_c_per_min REAL,
            relax_v_5m REAL,
            relax_v_15m REAL,
            relax_v_1h REAL,
            relax_v_12h REAL,
            relax_v_24h REAL,
            measured_capacity_ah REAL,
            cca_a REAL,
            internal_resistance_mohm REAL,
            outcome TEXT NOT NULL DEFAULT '',
            notes TEXT NOT NULL DEFAULT '',
            FOREIGN KEY (battery_id) REFERENCES batteries(battery_id)
        )
        """
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_recovery_cycles_battery_started "
        "ON recovery_cycles(battery_id, started_at)"
    )
    await db.commit()


async def upsert_battery(
    identity: BatteryIdentity,
    lifecycle: Optional[BatteryLifecycle] = None,
    *,
    updated_at: float,
) -> None:
    lifecycle = lifecycle or BatteryLifecycle()
    db = await get_db()
    await db.execute(
        """
        INSERT INTO batteries (
            battery_id, chemistry, nominal_capacity_ah, manufacturer, model,
            condition, water_added_total_ml, water_added_per_cell_ml,
            refill_timestamp, cycles_since_refill, measured_capacity_ah,
            cca_a, internal_resistance_mohm, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(battery_id) DO UPDATE SET
            chemistry=excluded.chemistry,
            nominal_capacity_ah=excluded.nominal_capacity_ah,
            manufacturer=excluded.manufacturer,
            model=excluded.model,
            condition=excluded.condition,
            water_added_total_ml=excluded.water_added_total_ml,
            water_added_per_cell_ml=excluded.water_added_per_cell_ml,
            refill_timestamp=excluded.refill_timestamp,
            cycles_since_refill=excluded.cycles_since_refill,
            measured_capacity_ah=excluded.measured_capacity_ah,
            cca_a=excluded.cca_a,
            internal_resistance_mohm=excluded.internal_resistance_mohm,
            updated_at=excluded.updated_at
        """,
        (
            identity.battery_id,
            identity.chemistry.value,
            identity.nominal_capacity_ah,
            identity.manufacturer,
            identity.model,
            lifecycle.condition.value,
            lifecycle.water_added_total_ml,
            lifecycle.water_added_per_cell_ml,
            lifecycle.refill_timestamp,
            lifecycle.cycles_since_refill,
            lifecycle.measured_capacity_ah,
            lifecycle.cca_a,
            lifecycle.internal_resistance_mohm,
            float(updated_at),
        ),
    )
    await db.commit()


async def get_battery(battery_id: str) -> Optional[BatteryRecord]:
    db = await get_db()
    async with db.execute(
        "SELECT * FROM batteries WHERE battery_id = ?",
        (battery_id,),
    ) as cursor:
        row = await cursor.fetchone()
    if row is None:
        return None

    identity = BatteryIdentity(
        battery_id=row["battery_id"],
        chemistry=BatteryChemistry(row["chemistry"]),
        nominal_capacity_ah=float(row["nominal_capacity_ah"]),
        manufacturer=row["manufacturer"] or "",
        model=row["model"] or "",
    )
    lifecycle = BatteryLifecycle(
        condition=BatteryCondition(row["condition"]),
        water_added_total_ml=float(row["water_added_total_ml"] or 0.0),
        water_added_per_cell_ml=(
            float(row["water_added_per_cell_ml"])
            if row["water_added_per_cell_ml"] is not None
            else None
        ),
        refill_timestamp=(
            float(row["refill_timestamp"])
            if row["refill_timestamp"] is not None
            else None
        ),
        cycles_since_refill=(
            int(row["cycles_since_refill"])
            if row["cycles_since_refill"] is not None
            else None
        ),
        measured_capacity_ah=(
            float(row["measured_capacity_ah"])
            if row["measured_capacity_ah"] is not None
            else None
        ),
        cca_a=float(row["cca_a"]) if row["cca_a"] is not None else None,
        internal_resistance_mohm=(
            float(row["internal_resistance_mohm"])
            if row["internal_resistance_mohm"] is not None
            else None
        ),
    )
    return BatteryRecord(identity=identity, lifecycle=lifecycle)


async def mark_battery_refilled(
    battery_id: str,
    *,
    total_ml: float,
    per_cell_ml: Optional[float] = None,
    timestamp: float,
) -> BatteryRecord:
    record = await get_battery(battery_id)
    if record is None:
        raise KeyError(f"unknown battery_id: {battery_id}")
    lifecycle = record.lifecycle
    lifecycle.mark_refill(
        total_ml=total_ml,
        per_cell_ml=per_cell_ml,
        timestamp=timestamp,
    )
    await upsert_battery(record.identity, lifecycle, updated_at=timestamp)
    updated = await get_battery(battery_id)
    assert updated is not None
    return updated


async def record_recovery_cycle(evidence: RecoveryCycleEvidence) -> int:
    if await get_battery(evidence.battery_id) is None:
        raise KeyError(f"unknown battery_id: {evidence.battery_id}")
    db = await get_db()
    cursor = await db.execute(
        """
        INSERT INTO recovery_cycles (
            battery_id, started_at, completed_at, intent, condition_before,
            main_target_v, main_imin_a, main_time_to_target_s, main_ah_in,
            hv_target_v, hv_imin_a, hv_time_to_target_s, hv_reversal_delta_a,
            temp_start_c, temp_max_c, max_dtemp_c_per_min,
            relax_v_5m, relax_v_15m, relax_v_1h, relax_v_12h, relax_v_24h,
            measured_capacity_ah, cca_a, internal_resistance_mohm,
            outcome, notes
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            evidence.battery_id,
            evidence.started_at,
            evidence.completed_at,
            evidence.intent.value,
            evidence.condition_before.value,
            evidence.main_target_v,
            evidence.main_imin_a,
            evidence.main_time_to_target_s,
            evidence.main_ah_in,
            evidence.hv_target_v,
            evidence.hv_imin_a,
            evidence.hv_time_to_target_s,
            evidence.hv_reversal_delta_a,
            evidence.temp_start_c,
            evidence.temp_max_c,
            evidence.max_dtemp_c_per_min,
            evidence.relax_v_5m,
            evidence.relax_v_15m,
            evidence.relax_v_1h,
            evidence.relax_v_12h,
            evidence.relax_v_24h,
            evidence.measured_capacity_ah,
            evidence.cca_a,
            evidence.internal_resistance_mohm,
            evidence.outcome,
            evidence.notes,
        ),
    )
    await db.commit()
    row_id = int(cursor.lastrowid)
    await cursor.close()

    if evidence.completed_at is not None:
        record = await get_battery(evidence.battery_id)
        assert record is not None
        lifecycle = record.lifecycle
        lifecycle.record_completed_cycle()
        if evidence.measured_capacity_ah is not None:
            lifecycle.measured_capacity_ah = evidence.measured_capacity_ah
        if evidence.cca_a is not None:
            lifecycle.cca_a = evidence.cca_a
        if evidence.internal_resistance_mohm is not None:
            lifecycle.internal_resistance_mohm = evidence.internal_resistance_mohm
        await upsert_battery(
            record.identity,
            lifecycle,
            updated_at=evidence.completed_at,
        )

    return row_id


async def list_recovery_cycles(
    battery_id: str,
    *,
    limit: int = 20,
) -> List[RecoveryCycleEvidence]:
    db = await get_db()
    async with db.execute(
        """
        SELECT * FROM recovery_cycles
        WHERE battery_id = ?
        ORDER BY started_at DESC, id DESC
        LIMIT ?
        """,
        (battery_id, max(1, int(limit))),
    ) as cursor:
        rows = await cursor.fetchall()

    result: List[RecoveryCycleEvidence] = []
    for row in reversed(rows):
        result.append(
            RecoveryCycleEvidence(
                battery_id=row["battery_id"],
                started_at=float(row["started_at"]),
                completed_at=(
                    float(row["completed_at"])
                    if row["completed_at"] is not None
                    else None
                ),
                intent=ChargeIntent(row["intent"]),
                condition_before=BatteryCondition(row["condition_before"]),
                main_target_v=row["main_target_v"],
                main_imin_a=row["main_imin_a"],
                main_time_to_target_s=row["main_time_to_target_s"],
                main_ah_in=row["main_ah_in"],
                hv_target_v=row["hv_target_v"],
                hv_imin_a=row["hv_imin_a"],
                hv_time_to_target_s=row["hv_time_to_target_s"],
                hv_reversal_delta_a=row["hv_reversal_delta_a"],
                temp_start_c=row["temp_start_c"],
                temp_max_c=row["temp_max_c"],
                max_dtemp_c_per_min=row["max_dtemp_c_per_min"],
                relax_v_5m=row["relax_v_5m"],
                relax_v_15m=row["relax_v_15m"],
                relax_v_1h=row["relax_v_1h"],
                relax_v_12h=row["relax_v_12h"],
                relax_v_24h=row["relax_v_24h"],
                measured_capacity_ah=row["measured_capacity_ah"],
                cca_a=row["cca_a"],
                internal_resistance_mohm=row["internal_resistance_mohm"],
                outcome=row["outcome"] or "",
                notes=row["notes"] or "",
            )
        )
    return result
