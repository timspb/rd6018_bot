"""D074 offline independent-emergency-OFF boundary.

Pure orchestration over explicitly injected async adapters. NO live adapter is
supplied here, no production import, no bot/HA/ESP/SSH access and no executable
node104 service. Unlike the 900-second edge lease, a software timeout is NOT
proof that the hardware turned off.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import Enum
import math
import time
from typing import Awaitable, Callable, Generic, TypeVar

from .fixture_supervisor import (
    Readback, LeaseReadback, verify_independent_off,
)

T = TypeVar("T")
MAX_OFF_DEADLINE_S = 45.0


class OffOutcome(str, Enum):
    BLOCKED_NO_INDEPENDENT_OFF_ADAPTER = "BLOCKED_NO_INDEPENDENT_OFF_ADAPTER"
    BLOCKED_NO_INDEPENDENT_READBACK = "BLOCKED_NO_INDEPENDENT_READBACK"
    HOLD = "HOLD"
    LEASE_DISARMED = "LEASE_DISARMED"


@dataclass(frozen=True)
class NativeEvidence:
    """One actual native observation plus declared physical producer lineage.

    An HA proxy of ESPHome and an ESPHome snapshot of the same underlying
    poller MUST use the same physical_producer_id and are NOT two sources.
    """
    report: Readback
    physical_producer_id: str
    path_id: str
    native: bool


@dataclass(frozen=True)
class IndependentLeaseEvidence:
    report: LeaseReadback
    physical_producer_id: str
    path_id: str
    native: bool


@dataclass(frozen=True)
class OffReceipt:
    outcome: OffOutcome
    reason: str
    deadline_s: float
    off_independently_proved: bool = False
    lease_independently_disarmed: bool = False


AsyncOperation = Callable[[float], Awaitable[T]]


@dataclass(frozen=True)
class OffAdapters:
    # Credentials are owned by external, separately provisioned adapter
    # processes; no token, mutable HA session or in-process RD controller here.
    request_off: AsyncOperation[bool] | None = None
    native_read_a: AsyncOperation[NativeEvidence] | None = None
    native_read_b: AsyncOperation[NativeEvidence] | None = None
    disarm_edge_lease: AsyncOperation[bool] | None = None
    native_lease_read: AsyncOperation[IndependentLeaseEvidence] | None = None


def readiness(adapters: OffAdapters) -> OffOutcome | None:
    if not callable(adapters.request_off):
        return OffOutcome.BLOCKED_NO_INDEPENDENT_OFF_ADAPTER
    if not all(callable(fn) for fn in (
        adapters.native_read_a, adapters.native_read_b,
        adapters.disarm_edge_lease, adapters.native_lease_read,
    )):
        return OffOutcome.BLOCKED_NO_INDEPENDENT_READBACK
    return None


def _distinct_reports(a: NativeEvidence, b: NativeEvidence) -> bool:
    return (
        isinstance(a, NativeEvidence) and isinstance(b, NativeEvidence)
        and a.native is True and b.native is True
        and bool(a.physical_producer_id) and bool(b.physical_producer_id)
        and bool(a.path_id) and bool(b.path_id)
        and bool(a.report.source) and bool(b.report.source)
        and bool(a.report.report_id) and bool(b.report.report_id)
        and a.physical_producer_id != b.physical_producer_id
        and a.path_id != b.path_id
    )


def _third_source(lease: IndependentLeaseEvidence, a: NativeEvidence, b: NativeEvidence) -> bool:
    return (
        isinstance(lease, IndependentLeaseEvidence)
        and lease.native is True
        and bool(lease.physical_producer_id) and bool(lease.path_id)
        and bool(lease.report.source) and bool(lease.report.report_id)
        and lease.physical_producer_id not in {a.physical_producer_id, b.physical_producer_id}
        and lease.path_id not in {a.path_id, b.path_id}
        and lease.report.source not in {a.report.source, b.report.source}
        and lease.report.report_id not in {a.report.report_id, b.report.report_id}
    )


async def independent_off_then_disarm(
    adapters: OffAdapters, *,
    deadline_s: float = MAX_OFF_DEADLINE_S,
    freshness_s: float = 3.0,
    monotonic: Callable[[], float] = time.monotonic,
) -> OffReceipt:
    """Run a fail-closed OFF sequence against separately supplied async ports.

    Every callback gets the SAME absolute monotonic cutoff and must enforce
    its own socket/transport deadline. asyncio.wait_for bounds cooperative
    awaitables; it CANNOT interrupt a callback blocking the event-loop thread.
    """
    if not math.isfinite(deadline_s) or not 0 < deadline_s <= MAX_OFF_DEADLINE_S:
        raise ValueError("D061 deadline must be >0 and <=45 seconds")
    if not math.isfinite(freshness_s) or freshness_s <= 0:
        raise ValueError("invalid evidence freshness window")
    start = monotonic()
    cutoff = start + deadline_s
    missing = readiness(adapters)
    if missing is not None:
        return OffReceipt(missing, "missing_verified_adapter", deadline_s)

    def hold(reason: str, *, off_proved: bool = False) -> OffReceipt:
        return OffReceipt(OffOutcome.HOLD, reason, deadline_s, off_proved, False)

    async def bounded(operation: AsyncOperation[T]) -> T:
        remaining = cutoff - monotonic()
        if not math.isfinite(remaining) or remaining <= 0:
            raise TimeoutError("D061 deadline exhausted")
        return await asyncio.wait_for(operation(cutoff), timeout=remaining)

    try:
        assert adapters.request_off is not None
        if await bounded(adapters.request_off) is not True:
            return hold("off_command_not_positively_accepted")
        off_command_ack_at = monotonic()

        assert adapters.native_read_a is not None and adapters.native_read_b is not None
        a, b = await bounded(
            lambda bound: asyncio.gather(
                adapters.native_read_a(bound), adapters.native_read_b(bound)
            )
        )
        if not _distinct_reports(a, b):
            return hold("off_report_sources_not_independent")
        now = monotonic()
        if (a.report.observed_monotonic < off_command_ack_at
                or b.report.observed_monotonic < off_command_ack_at):
            return hold("off_readback_not_post_command")
        if not verify_independent_off(a.report, b.report, now=now, max_age_s=freshness_s):
            return hold("fresh_independent_off_not_proved")

        assert adapters.disarm_edge_lease is not None
        if await bounded(adapters.disarm_edge_lease) is not True:
            return hold("lease_disarm_not_accepted", off_proved=True)

        assert adapters.native_lease_read is not None
        lease = await bounded(adapters.native_lease_read)
        observed = monotonic()
        if not _third_source(lease, a, b):
            return hold("lease_source_not_independent", off_proved=True)
        if (lease.report.armed is not False
                or lease.report.observed_monotonic < off_command_ack_at
                or lease.report.observed_monotonic > observed
                or observed - lease.report.observed_monotonic > freshness_s
                or observed >= cutoff):
            return hold("lease_disarm_not_independently_verified", off_proved=True)
        return OffReceipt(
            OffOutcome.LEASE_DISARMED, "native_off_and_lease_proved",
            deadline_s, True, True,
        )
    except asyncio.CancelledError:
        # External supervisor must continue its own independent containment.
        raise
    except (Exception,):
        # No success by exception, timeout, parsing error or unreachable port.
        return hold("off_or_readback_ambiguous")
