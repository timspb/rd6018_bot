"""Hardware-inert-friendly independent OFF sequence used by kill supervision.

Callbacks are deliberately explicit: an actuator ACK is never an OFF proof.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class IndependentOffProof:
    ha_timestamp: float
    native_timestamp: float
    lease_generation: int
    ha_off: bool
    native_off: bool
    protection_normal: bool


def _valid_report(report: Any, now: float, max_age: float) -> bool:
    if not isinstance(report, dict):
        return False
    timestamp = report.get("timestamp")
    if isinstance(timestamp, bool) or not isinstance(timestamp, (int, float)):
        return False
    age = now - float(timestamp)
    return math.isfinite(age) and 0 <= age <= max_age


def independent_output_off(*, ha_off_command: Callable[[], Any],
                           native_off_command: Callable[[], Any],
                           ha_readback: Callable[[], dict],
                           native_readback: Callable[[], dict],
                           disarm_lease: Callable[[], Any],
                           lease_readback: Callable[[], dict],
                           retire_ownership: Callable[[], Any],
                           retire_poller: Callable[[], Any],
                           expected_generation: int,
                           timeout_s: float = 8.0, max_age_s: float = 3.0,
                           clock: Callable[[], float] = time.time,
                           monotonic: Callable[[], float] = time.monotonic,
                           sleep: Callable[[float], Any] = time.sleep) -> IndependentOffProof:
    """Command both channels, require fresh independent proof, then disarm.

    Synchronous callbacks keep the supervisor independent of the killed bot's
    interpreter/runtime. Callers must bound each callback to the remaining budget.
    """
    deadline = monotonic() + timeout_s
    # Idempotent sequence: HA first, native second, then independently read both.
    ha_off_command()
    native_off_command()
    while monotonic() < deadline:
        now = clock()
        ha, native = ha_readback(), native_readback()
        if (_valid_report(ha, now, max_age_s) and _valid_report(native, now, max_age_s)
                and ha.get("timestamp") != native.get("timestamp")
                and ha.get("output") is False and native.get("output") is False
                and _zero(ha.get("voltage")) and _zero(ha.get("current"))
                and _zero(native.get("voltage")) and _zero(native.get("current"))
                and ha.get("protection") == "NORMAL"
                and native.get("protection") == "NORMAL"):
            break
        sleep(min(0.1, max(0.0, deadline - monotonic())))
    else:
        raise RuntimeError("fresh independent HA/native verified-OFF proof unavailable")
    if disarm_lease() is not True:
        raise RuntimeError("edge lease disarm command failed")
    lease = lease_readback()
    if (not isinstance(lease, dict) or lease.get("armed") is not False
            or lease.get("generation") != expected_generation
            or lease.get("timestamp") is None
            or not _valid_report(lease, clock(), max_age_s)):
        raise RuntimeError("edge lease disarm/generation readback mismatch")
    if retire_ownership() is not True or retire_poller() is not True:
        raise RuntimeError("ownership or poller retirement not confirmed")
    return IndependentOffProof(float(ha["timestamp"]), float(native["timestamp"]),
                               int(lease["generation"]), True, True, True)


def _zero(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return False
    return math.isfinite(number) and abs(number) <= 0.02
