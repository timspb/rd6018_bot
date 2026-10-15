"""Passive SAFE_WAIT voltage-relaxation recorder (EFB and Ca/Ca only).

No charge intent, setpoint, voltage authority, OFF/ON command, or stage mutation.
Only source-fresh battery-voltage measurements during *verified* Output OFF
enter the diagnostic journal. Gaps or unknown output close, never interpolate.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from typing import Any, Mapping


ALLOWED_PROFILES = frozenset({"EFB", "CA/CA"})
MAX_SOURCE_AGE_S = 75.0
MIN_SAMPLE_INTERVAL_S = 20.0
MAX_CONTINUOUS_GAP_S = 180.0
ENDPOINT_TOLERANCE_S = 90.0
MAX_VALID_BATTERY_V = 20.0
WINDOWS_S = {"relax_5_15": (300.0, 900.0), "relax_15_60": (900.0, 3600.0)}


def _finite(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
    except (ValueError, TypeError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _fresh(meta: Mapping[str, Any], name: str) -> bool:
    item = meta.get(name)
    if not isinstance(item, Mapping) or item.get("status") != "ok":
        return False
    age = _finite(item.get("age_s"))
    return age is not None and 0.0 <= age <= MAX_SOURCE_AGE_S


@dataclass(frozen=True)
class RelaxationInput:
    session_id: str
    battery_id: str | None
    profile: str
    safe_wait_epoch_s: float
    continuation: str
    observed_at_s: float
    voltage_v: float
    current_a: float
    temp_c: float | None
    source_age_s: float
    run_key: str


def qualify(
    *, live: Mapping[str, Any], stage: str, safe_wait_stage: str, session_id: str | None,
    battery_id: str | None, profile: str, safe_wait_epoch_s: Any,
    continuation: str | None, observed_at_s: Any,
) -> RelaxationInput | None:
    """Return passive evidence, not a charging decision.

    SAFE_WAIT is not extended for a signature; an early authorized transition
    leaves windows incomplete. Unknown output is NEVER treated as OFF.
    """
    chemistry = str(profile or "").upper()
    if chemistry not in ALLOWED_PROFILES or stage != safe_wait_stage:
        return None
    if continuation not in {"MAIN", "DONE"} or not session_id:
        return None
    epoch = _finite(safe_wait_epoch_s)
    now = _finite(observed_at_s)
    if epoch is None or epoch <= 0 or now is None or now < epoch:
        return None
    meta = live.get("_meta")
    if not isinstance(meta, Mapping) or not all(
        _fresh(meta, name) for name in ("battery_voltage", "switch", "current")
    ):
        return None
    if str(live.get("switch", "")).lower() not in {"off", "false", "0"}:
        return None
    voltage = _finite(live.get("battery_voltage"))
    current = _finite(live.get("current"))
    if voltage is None or not 5.0 <= voltage <= MAX_VALID_BATTERY_V:
        return None
    if current is None or not 0 <= current <= 0.03:
        return None
    temp = _finite(live.get("temp_ext"))
    if temp is not None and not -30 <= temp <= 80:
        temp = None
    identity = json.dumps(
        [session_id, battery_id, float(epoch), continuation, chemistry], separators=(",", ":")
    )
    key = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
    return RelaxationInput(
        session_id=str(session_id), battery_id=battery_id or None,
        profile=chemistry, safe_wait_epoch_s=epoch, continuation=continuation,
        observed_at_s=now, voltage_v=voltage, current_a=current,
        temp_c=temp, source_age_s=float(meta["battery_voltage"]["age_s"]), run_key=key,
    )


def calculate_signature(samples: list[tuple[float, float]]) -> dict[str, Any]:
    """OLS slope in mV/min. No interpolation over missing endpoints/gaps."""
    ordered = sorted(samples)
    result: dict[str, Any] = {}
    if not ordered:
        return {name: {"status": "insufficient_data"} for name in WINDOWS_S}
    start = ordered[0][0]
    for label, (a, b) in WINDOWS_S.items():
        inside = [(t - start, v) for t, v in ordered if a <= t - start <= b]
        if (len(inside) < 5 or inside[0][0] - a > ENDPOINT_TOLERANCE_S
                or b - inside[-1][0] > ENDPOINT_TOLERANCE_S
                or any(y[0] - x[0] > MAX_CONTINUOUS_GAP_S
                       for x, y in zip(inside, inside[1:]))):
            result[label] = {"status": "insufficient_data"}
            continue
        n = len(inside)
        mt = sum(t for t, _ in inside) / n
        mv = sum(v for _, v in inside) / n
        denominator = sum((t - mt) ** 2 for t, _ in inside)
        if denominator <= 0:
            result[label] = {"status": "insufficient_data"}
            continue
        slope_mv_min = 60000.0 * sum((t - mt) * (v - mv) for t, v in inside) / denominator
        result[label] = {
            "status": "measured", "sample_count": n,
            "slope_mv_per_min": round(slope_mv_min, 4),
            "estimated_drop_mv": round(-slope_mv_min * (b - a) / 60.0, 3),
        }
    first, later = result["relax_5_15"], result["relax_15_60"]
    if first["status"] == "measured" and later["status"] == "measured":
        early = abs(first["slope_mv_per_min"])
        result["slope_magnitude_ratio"] = round(
            abs(later["slope_mv_per_min"]) / early, 4
        ) if early >= 0.1 else None
    else:
        result["slope_magnitude_ratio"] = None
    result["interpretation"] = "observational_only_not_stratification_proof"
    return result


class VoltageRelaxationRecorder:
    """Append-only SQLite journal owned by this module; no hardware access."""

    def __init__(self) -> None:
        self._ready = False
        self._active: tuple[str, int] | None = None

    async def _schema(self, db: Any) -> None:
        if self._ready:
            return
        await db.execute("""CREATE TABLE IF NOT EXISTS voltage_relaxation_runs (
            run_key TEXT NOT NULL, segment INTEGER NOT NULL,
            session_id TEXT NOT NULL, battery_id TEXT, profile TEXT NOT NULL,
            continuation TEXT NOT NULL, safe_wait_epoch_s REAL NOT NULL,
            started_at_s REAL NOT NULL, last_at_s REAL NOT NULL,
            status TEXT NOT NULL, signature_json TEXT NOT NULL DEFAULT '{}',
            PRIMARY KEY(run_key, segment))""")
        await db.execute("""CREATE TABLE IF NOT EXISTS voltage_relaxation_samples (
            run_key TEXT NOT NULL, segment INTEGER NOT NULL,
            timestamp_s REAL NOT NULL, elapsed_s REAL NOT NULL,
            battery_voltage_v REAL NOT NULL, battery_current_a REAL NOT NULL,
            battery_temp_c REAL, source_age_s REAL NOT NULL,
            PRIMARY KEY(run_key, segment, timestamp_s))""")
        await db.execute("""CREATE INDEX IF NOT EXISTS voltage_relaxation_samples_by_run
            ON voltage_relaxation_samples(run_key,segment,elapsed_s)""")
        await db.commit()
        self._ready = True

    async def _close(self, db: Any) -> None:
        if self._active is not None:
            await db.execute(
                "UPDATE voltage_relaxation_runs SET status='closed' WHERE run_key=? AND segment=?",
                self._active,
            )
            await db.commit()
            self._active = None

    async def observe(
        self, db: Any, *, live: Mapping[str, Any], stage: str, safe_wait_stage: str,
        session_id: str | None, battery_id: str | None, profile: str,
        safe_wait_epoch_s: Any, continuation: str | None, observed_at_s: Any,
    ) -> dict[str, Any] | None:
        await self._schema(db)
        sample = qualify(
            live=live, stage=stage, safe_wait_stage=safe_wait_stage, session_id=session_id, battery_id=battery_id,
            profile=profile, safe_wait_epoch_s=safe_wait_epoch_s,
            continuation=continuation, observed_at_s=observed_at_s,
        )
        if sample is None:
            await self._close(db)
            return None
        if self._active is not None and self._active[0] != sample.run_key:
            await self._close(db)
        if self._active is None:
            cursor = await db.execute(
                "SELECT segment, last_at_s, status FROM voltage_relaxation_runs "
                "WHERE run_key=? ORDER BY segment DESC LIMIT 1", (sample.run_key,),
            )
            last = await cursor.fetchone()
            if (last is not None and last[2] == "active"
                    and 0 <= sample.observed_at_s - float(last[1]) <= MAX_CONTINUOUS_GAP_S):
                self._active = (sample.run_key, int(last[0]))
            else:
                if last is not None and last[2] == "active":
                    await db.execute(
                        "UPDATE voltage_relaxation_runs SET status='closed' WHERE run_key=? AND segment=?",
                        (sample.run_key, int(last[0])),
                    )
                number = int(last[0]) + 1 if last is not None else 1
                self._active = (sample.run_key, number)
                await db.execute(
                    "INSERT INTO voltage_relaxation_runs VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (sample.run_key, number, sample.session_id, sample.battery_id,
                     sample.profile, sample.continuation, sample.safe_wait_epoch_s,
                     sample.observed_at_s, sample.observed_at_s, "active", "{}"),
                )
        assert self._active is not None
        key, number = self._active
        cursor = await db.execute(
            "SELECT started_at_s,last_at_s FROM voltage_relaxation_runs "
            "WHERE run_key=? AND segment=?", (key, number),
        )
        started, previous = await cursor.fetchone()
        interval = sample.observed_at_s - float(previous)
        if interval < 0:
            return None  # Clock rollback is not a new OFF period.
        if interval > MAX_CONTINUOUS_GAP_S:
            await self._close(db)
            return await self.observe(
                db, live=live, stage=stage, safe_wait_stage=safe_wait_stage, session_id=session_id,
                battery_id=battery_id, profile=profile,
                safe_wait_epoch_s=safe_wait_epoch_s,
                continuation=continuation, observed_at_s=observed_at_s,
            )
        if interval < MIN_SAMPLE_INTERVAL_S:
            exists = await db.execute(
                "SELECT 1 FROM voltage_relaxation_samples "
                "WHERE run_key=? AND segment=? AND timestamp_s=?",
                (key, number, sample.observed_at_s),
            )
            if await exists.fetchone() is not None or sample.observed_at_s != float(started):
                return None
        await db.execute(
            "INSERT OR IGNORE INTO voltage_relaxation_samples VALUES (?,?,?,?,?,?,?,?)",
            (key, number, sample.observed_at_s, sample.observed_at_s - float(started),
             sample.voltage_v, sample.current_a, sample.temp_c, sample.source_age_s),
        )
        cursor = await db.execute(
            "SELECT timestamp_s,battery_voltage_v FROM voltage_relaxation_samples "
            "WHERE run_key=? AND segment=? ORDER BY timestamp_s", (key, number),
        )
        samples = [(float(t), float(v)) for t, v in await cursor.fetchall()]
        signature = calculate_signature(samples)
        await db.execute(
            "UPDATE voltage_relaxation_runs SET last_at_s=?, signature_json=? "
            "WHERE run_key=? AND segment=?",
            (sample.observed_at_s, json.dumps(signature, sort_keys=True), key, number),
        )
        await db.commit()
        return {
            "run_key": key, "segment": number, "samples": len(samples),
            "elapsed_s": sample.observed_at_s - float(started),
            "signature": signature,
        }


__all__ = ["VoltageRelaxationRecorder", "calculate_signature", "qualify",
           "RelaxationInput", "WINDOWS_S"]
