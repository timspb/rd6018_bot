from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from battery_diagnostics import DiagnosticHypothesis, DiagnosticLevel
from battery_registry import get_battery
from database import get_db
from pb_domain import BatteryChemistry


class SGAccess(str, Enum):
    """Whether electrolyte can actually be sampled on this physical battery."""

    UNKNOWN = "unknown"
    SERVICEABLE = "serviceable"
    INACCESSIBLE = "inaccessible"


class HydrometerMode(str, Enum):
    """How the operator's instrument reports specific gravity."""

    UNKNOWN = "unknown"
    RAW = "raw"
    TEMPERATURE_COMPENSATED = "temperature_compensated"


class SGCorrectionProfile(str, Enum):
    """Explicitly selected SG temperature convention.

    Profiles are never inferred from a manufacturer/model string.  RAW_ONLY means
    no numeric temperature correction is applied by V2.
    """

    RAW_ONLY = "raw_only"
    TROJAN_80F = "trojan_80f"
    ROLLS_25C = "rolls_25c"


class SGPromptPoint(str, Enum):
    ROUTINE = "routine"
    DIAGNOSTIC_VERIFY = "diagnostic_verify"
    POST_CORRECTIVE_RETEST = "post_corrective_retest"


@dataclass(frozen=True)
class SGMeasurementMetadata:
    battery_id: str
    measured_at: float
    hydrometer_mode: HydrometerMode = HydrometerMode.UNKNOWN
    correction_profile: SGCorrectionProfile = SGCorrectionProfile.RAW_ONLY


@dataclass(frozen=True)
class SGPromptDecision:
    should_prompt: bool
    reason: str


_LEVEL_ORDER = {
    DiagnosticLevel.NORMAL: 0,
    DiagnosticLevel.WATCH: 1,
    DiagnosticLevel.VERIFY: 2,
    DiagnosticLevel.PROBABLE: 3,
    DiagnosticLevel.HIGH: 4,
}


async def init_sg_policy_store() -> None:
    db = await get_db()
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS battery_sg_access (
            battery_id TEXT PRIMARY KEY,
            access TEXT NOT NULL DEFAULT 'unknown',
            updated_at REAL NOT NULL,
            FOREIGN KEY (battery_id) REFERENCES batteries(battery_id)
        )
        """
    )
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS battery_sg_measurement_meta (
            battery_id TEXT NOT NULL,
            measured_at REAL NOT NULL,
            hydrometer_mode TEXT NOT NULL DEFAULT 'unknown',
            correction_profile TEXT NOT NULL DEFAULT 'raw_only',
            PRIMARY KEY (battery_id, measured_at),
            FOREIGN KEY (battery_id) REFERENCES batteries(battery_id)
        )
        """
    )
    await db.commit()


async def set_sg_access(battery_id: str, access: SGAccess, *, updated_at: float) -> None:
    if await get_battery(battery_id) is None:
        raise KeyError(f"unknown battery_id: {battery_id}")
    if not math.isfinite(float(updated_at)) or float(updated_at) <= 0:
        raise ValueError("updated_at must be a positive finite timestamp")
    await init_sg_policy_store()
    db = await get_db()
    await db.execute(
        """
        INSERT INTO battery_sg_access (battery_id, access, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(battery_id) DO UPDATE SET
            access=excluded.access,
            updated_at=excluded.updated_at
        """,
        (battery_id, SGAccess(access).value, float(updated_at)),
    )
    await db.commit()


async def get_sg_access(battery_id: str) -> SGAccess:
    await init_sg_policy_store()
    db = await get_db()
    async with db.execute(
        "SELECT access FROM battery_sg_access WHERE battery_id = ?",
        (battery_id,),
    ) as cursor:
        row = await cursor.fetchone()
    if row is None:
        return SGAccess.UNKNOWN
    try:
        return SGAccess(row["access"])
    except (TypeError, ValueError):
        return SGAccess.UNKNOWN


async def record_sg_measurement_metadata(metadata: SGMeasurementMetadata) -> None:
    if await get_battery(metadata.battery_id) is None:
        raise KeyError(f"unknown battery_id: {metadata.battery_id}")
    if not math.isfinite(float(metadata.measured_at)) or metadata.measured_at <= 0:
        raise ValueError("measured_at must be a positive finite timestamp")
    _validate_measurement_policy(metadata.hydrometer_mode, metadata.correction_profile)
    await init_sg_policy_store()
    db = await get_db()
    await db.execute(
        """
        INSERT INTO battery_sg_measurement_meta (
            battery_id, measured_at, hydrometer_mode, correction_profile
        ) VALUES (?, ?, ?, ?)
        ON CONFLICT(battery_id, measured_at) DO UPDATE SET
            hydrometer_mode=excluded.hydrometer_mode,
            correction_profile=excluded.correction_profile
        """,
        (
            metadata.battery_id,
            float(metadata.measured_at),
            metadata.hydrometer_mode.value,
            metadata.correction_profile.value,
        ),
    )
    await db.commit()


async def get_sg_measurement_metadata(
    battery_id: str,
    measured_at: float,
) -> Optional[SGMeasurementMetadata]:
    await init_sg_policy_store()
    db = await get_db()
    async with db.execute(
        """
        SELECT hydrometer_mode, correction_profile
        FROM battery_sg_measurement_meta
        WHERE battery_id = ? AND measured_at = ?
        """,
        (battery_id, float(measured_at)),
    ) as cursor:
        row = await cursor.fetchone()
    if row is None:
        return None
    return SGMeasurementMetadata(
        battery_id=battery_id,
        measured_at=float(measured_at),
        hydrometer_mode=HydrometerMode(row["hydrometer_mode"]),
        correction_profile=SGCorrectionProfile(row["correction_profile"]),
    )


def _validate_measurement_policy(
    hydrometer_mode: HydrometerMode,
    correction_profile: SGCorrectionProfile,
) -> None:
    mode = HydrometerMode(hydrometer_mode)
    profile = SGCorrectionProfile(correction_profile)
    if mode is HydrometerMode.TEMPERATURE_COMPENSATED and profile is not SGCorrectionProfile.RAW_ONLY:
        raise ValueError("temperature-compensated hydrometer must not receive a second software correction")
    if profile is not SGCorrectionProfile.RAW_ONLY and mode is not HydrometerMode.RAW:
        raise ValueError("manufacturer correction profile requires hydrometer_mode=raw")


def corrected_specific_gravity(
    raw_sg: float,
    *,
    temperature_c: Optional[float],
    hydrometer_mode: HydrometerMode,
    correction_profile: SGCorrectionProfile,
) -> Optional[float]:
    """Return an explicitly authorized temperature-corrected SG value.

    Raw readings remain the stored primary evidence.  A temperature-compensated
    instrument is already corrected, so its reported value is returned unchanged.
    For an ordinary raw hydrometer V2 only computes a corrected value when the
    operator explicitly selected a named convention and supplied electrolyte temp.

    TROJAN_80F follows Trojan's published maintenance convention: +/-0.004 per
    10 F (5.56 C) around 80 F (~26.7 C).
    ROLLS_25C follows the Rolls flooded-battery manual convention: +/-0.003 per
    5 C around 25 C.
    """
    raw = float(raw_sg)
    if not math.isfinite(raw):
        raise ValueError("raw_sg must be finite")
    mode = HydrometerMode(hydrometer_mode)
    profile = SGCorrectionProfile(correction_profile)
    _validate_measurement_policy(mode, profile)

    if mode is HydrometerMode.TEMPERATURE_COMPENSATED:
        return raw
    if mode is not HydrometerMode.RAW or profile is SGCorrectionProfile.RAW_ONLY:
        return None
    if temperature_c is None or not math.isfinite(float(temperature_c)):
        return None

    temp = float(temperature_c)
    if profile is SGCorrectionProfile.TROJAN_80F:
        return raw + 0.004 * ((temp - (80.0 - 32.0) * 5.0 / 9.0) / (10.0 * 5.0 / 9.0))
    if profile is SGCorrectionProfile.ROLLS_25C:
        return raw + 0.003 * ((temp - 25.0) / 5.0)
    return None


def decide_sg_prompt(
    *,
    chemistry: BatteryChemistry,
    access: SGAccess,
    point: SGPromptPoint,
    hypothesis: Optional[DiagnosticHypothesis] = None,
    level: Optional[DiagnosticLevel] = None,
    prior_imbalance: bool = False,
    safe_to_measure: bool = True,
) -> SGPromptDecision:
    """Decide whether V2 should proactively ask for per-cell SG.

    No routine nagging: SG is requested only when it can resolve an ambiguity or
    close the loop after a corrective cycle.  Missing/unavailable SG is never fault
    evidence and therefore simply returns a non-prompt decision here.
    """
    chemistry = BatteryChemistry(chemistry)
    access = SGAccess(access)
    point = SGPromptPoint(point)

    if chemistry is BatteryChemistry.AGM:
        return SGPromptDecision(False, "agm_no_electrolyte_sampling")
    if access is SGAccess.UNKNOWN:
        return SGPromptDecision(False, "electrolyte_access_unconfirmed")
    if access is SGAccess.INACCESSIBLE:
        return SGPromptDecision(False, "electrolyte_inaccessible")
    if not safe_to_measure:
        return SGPromptDecision(False, "measurement_not_safe_now")

    if point is SGPromptPoint.POST_CORRECTIVE_RETEST:
        if prior_imbalance:
            return SGPromptDecision(True, "retest_prior_cell_imbalance")
        return SGPromptDecision(False, "no_prior_imbalance_to_retest")

    if point is SGPromptPoint.DIAGNOSTIC_VERIFY:
        if hypothesis not in {
            DiagnosticHypothesis.CELL_FAULT,
            DiagnosticHypothesis.STRATIFICATION,
            DiagnosticHypothesis.SULFATION,
        }:
            return SGPromptDecision(False, "sg_not_resolving_current_hypothesis")
        if level is None or _LEVEL_ORDER[DiagnosticLevel(level)] < _LEVEL_ORDER[DiagnosticLevel.VERIFY]:
            return SGPromptDecision(False, "diagnostic_level_below_verify")
        return SGPromptDecision(True, "sg_resolves_diagnostic_ambiguity")

    return SGPromptDecision(False, "routine_sg_not_requested")
