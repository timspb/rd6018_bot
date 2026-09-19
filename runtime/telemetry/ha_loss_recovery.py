"""HA-loss recovery window for the preserved V2 runtime.

The coordinator is deliberately non-actuating.  It owns only the classification and
timing of an HA telemetry outage; the caller remains responsible for invoking the
existing containment function once the window expires.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Awaitable, Callable, Mapping

from .authority import RuntimeTelemetryProvider, TelemetrySnapshot, TelemetrySource


logger = logging.getLogger("rd6018.runtime.telemetry.ha_loss")


HA_RECOVERY_WINDOW_S = 14.0 * 60.0


class HALossState(str, Enum):
    HA_CONNECTED = "HA_CONNECTED"
    HA_DEGRADED = "HA_DEGRADED"
    RECOVERING = "RECOVERING"
    CONTAINMENT_REQUIRED = "CONTAINMENT_REQUIRED"


@dataclass(frozen=True)
class HALossRecoveryStatus:
    state: HALossState
    ha_loss_started_at: float | None = None
    recovery_deadline: float | None = None
    last_direct_telemetry_at: float | None = None
    direct_snapshot: TelemetrySnapshot | None = None


class HALossRecoveryWindow:
    """Track an HA outage without issuing commands or changing runtime ownership."""

    def __init__(
        self,
        *,
        direct_reader: Callable[[], Awaitable[Any]] | Any | None = None,
        window_s: float = HA_RECOVERY_WINDOW_S,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if window_s <= 0:
            raise ValueError("HA recovery window must be positive")
        self.window_s = float(window_s)
        self._clock = clock
        self._provider = RuntimeTelemetryProvider(
            esp_direct_reader=direct_reader,
            max_age_s=20.0,
            clock=clock,
        )
        self._status = HALossRecoveryStatus(HALossState.HA_CONNECTED)
        self._containment_claimed = False

    @property
    def status(self) -> HALossRecoveryStatus:
        return self._status

    @property
    def recovering(self) -> bool:
        return self._status.state in {HALossState.HA_DEGRADED, HALossState.RECOVERING}

    def should_defer_containment(self, now: float | None = None) -> bool:
        if not self.recovering or self._status.recovery_deadline is None:
            return False
        return (self._clock() if now is None else float(now)) < self._status.recovery_deadline

    def observe_ha_success(self, *, now: float | None = None) -> None:
        current = self._clock() if now is None else float(now)
        if self.recovering:
            logger.info(
                "HA_RECOVERED duration=%.3fs direct_telemetry_at=%s",
                current - (self._status.ha_loss_started_at or current),
                self._status.last_direct_telemetry_at,
            )
        self._status = HALossRecoveryStatus(HALossState.HA_CONNECTED)
        self._containment_claimed = False

    async def observe_ha_loss(self, *, last_known: Mapping[str, Any] | None = None) -> HALossRecoveryStatus:
        now = self._clock()
        if not self.recovering and self._status.state != HALossState.CONTAINMENT_REQUIRED:
            self._status = HALossRecoveryStatus(
                HALossState.HA_DEGRADED,
                ha_loss_started_at=now,
                recovery_deadline=now + self.window_s,
            )
            logger.warning(
                "HA_LOSS_DETECTED %s",
                {
                    "duration": 0.0,
                    "source": TelemetrySource.HA.value,
                    "direct_esp_available": False,
                    "output_state": None if last_known is None else last_known.get("switch"),
                    "voltage": None if last_known is None else last_known.get("voltage"),
                    "current": None if last_known is None else last_known.get("current"),
                },
            )

        direct_snapshot: TelemetrySnapshot | None = None
        if self.recovering:
            selected, comparison = await self._provider.collect()
            if selected.source == TelemetrySource.ESP_DIRECT and selected.confidence >= 1.0:
                direct_snapshot = selected
                self._status = HALossRecoveryStatus(
                    HALossState.RECOVERING,
                    self._status.ha_loss_started_at,
                    self._status.recovery_deadline,
                    now,
                    direct_snapshot,
                )
            logger.info(
                "HA_LOSS_PROBE %s",
                {
                    "duration": now - (self._status.ha_loss_started_at or now),
                    "source": selected.source.value,
                    "direct_esp_available": TelemetrySource.ESP_DIRECT in comparison.snapshots,
                    "output_state": selected.values.get("output_state"),
                    "voltage": selected.values.get("voltage"),
                    "current": selected.values.get("current"),
                    "age": selected.age,
                    "failures": comparison.failure_modes,
                },
            )

        if self._status.recovery_deadline is not None and now >= self._status.recovery_deadline:
            self._status = HALossRecoveryStatus(
                HALossState.CONTAINMENT_REQUIRED,
                self._status.ha_loss_started_at,
                self._status.recovery_deadline,
                self._status.last_direct_telemetry_at,
                self._status.direct_snapshot,
            )
            logger.error(
                "HA_RECOVERY_TIMEOUT duration=%.3fs deadline=%.3f",
                now - (self._status.ha_loss_started_at or now),
                self._status.recovery_deadline,
            )
        return self._status

    def claim_containment(self) -> bool:
        """Return true once so the caller can invoke the existing containment owner."""
        if self._containment_claimed:
            return False
        if self._status.state != HALossState.CONTAINMENT_REQUIRED:
            return False
        self._containment_claimed = True
        return True
