from __future__ import annotations

import json
import math
import os
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping, Optional


@dataclass(frozen=True)
class ExternalTempIntegrityPolicy:
    """Calibrated plausibility limits for fresh external-temperature reports.

    There are deliberately no production numeric defaults.  The detector is enabled
    only when an explicit consecutive-sample limit and at least one calibrated
    plausibility limit are supplied by the production composition/bench profile.
    """

    consecutive_samples: Optional[int] = None
    hv_consecutive_samples: Optional[int] = None
    min_plausible_c: Optional[float] = None
    max_plausible_c: Optional[float] = None
    max_step_c: Optional[float] = None
    max_slope_c_per_min: Optional[float] = None

    def __post_init__(self) -> None:
        normal = self.consecutive_samples
        hv = self.hv_consecutive_samples
        if normal is not None and int(normal) < 2:
            raise ValueError("external-temperature consecutive_samples must be >= 2")
        if hv is not None and int(hv) < 2:
            raise ValueError("external-temperature hv_consecutive_samples must be >= 2")
        if normal is None and hv is not None:
            raise ValueError("HV anomaly limit requires a baseline consecutive_samples limit")
        if normal is not None and hv is not None and int(hv) > int(normal):
            raise ValueError("HV external-temperature integrity policy may not be looser")
        if (
            self.min_plausible_c is not None
            and self.max_plausible_c is not None
            and float(self.min_plausible_c) >= float(self.max_plausible_c)
        ):
            raise ValueError("external-temperature plausible range is invalid")
        for name, value in (
            ("max_step_c", self.max_step_c),
            ("max_slope_c_per_min", self.max_slope_c_per_min),
        ):
            if value is not None and (not math.isfinite(float(value)) or float(value) <= 0):
                raise ValueError(f"{name} must be finite and > 0")

    @property
    def enabled(self) -> bool:
        return self.consecutive_samples is not None and any(
            value is not None
            for value in (
                self.min_plausible_c,
                self.max_plausible_c,
                self.max_step_c,
                self.max_slope_c_per_min,
            )
        )

    def limit(self, *, hv: bool) -> Optional[int]:
        if not self.enabled:
            return None
        if hv and self.hv_consecutive_samples is not None:
            return int(self.hv_consecutive_samples)
        return int(self.consecutive_samples or 0)


@dataclass(frozen=True)
class ExternalTempSample:
    value_c: float
    source_token: str
    source_epoch_s: Optional[float]


@dataclass(frozen=True)
class ExternalTempIntegrityDecision:
    new_source_sample: bool = False
    suspicious: bool = False
    anomaly_count: int = 0
    trip: bool = False
    detail: str = ""


def _finite(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _parse_epoch(value: Any) -> Optional[float]:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        text = value.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        return datetime.fromisoformat(text).timestamp()
    except (TypeError, ValueError, OverflowError):
        return None


class ExternalTempIntegrityMonitor:
    """Stateful N-consecutive detector keyed by HA source-report identity.

    Missing/stale/non-finite handling intentionally does not live here: the V2 runtime
    freshness/critical-telemetry guard owns those immediate fail-close classes.  This
    monitor sees only already-valid fresh snapshots and handles the remaining class of
    fresh-but-suspicious values.
    """

    def __init__(
        self,
        policy: Optional[ExternalTempIntegrityPolicy] = None,
        *,
        fault_file: str = "external_temp_integrity_fault_v2.json",
    ) -> None:
        self.policy = policy or ExternalTempIntegrityPolicy()
        self.fault_file = str(fault_file)
        self._last_sample: Optional[ExternalTempSample] = None
        self._last_source_token: Optional[str] = None
        self._anomaly_count = 0
        self._latched = False
        self._latch_reason = ""
        self._latch_source_token: Optional[str] = None
        self._rearm_baseline: Optional[ExternalTempSample] = None
        self._load_latch()

    @property
    def enabled(self) -> bool:
        return self.policy.enabled

    @property
    def latched(self) -> bool:
        return self._latched

    @property
    def latch_reason(self) -> str:
        return self._latch_reason

    @property
    def anomaly_count(self) -> int:
        return self._anomaly_count

    @staticmethod
    def _sample(live: Mapping[str, Any]) -> Optional[ExternalTempSample]:
        value = _finite(live.get("temp_ext"))
        meta = live.get("_meta")
        entry = meta.get("temp_ext") if isinstance(meta, Mapping) else None
        if value is None or not isinstance(entry, Mapping):
            return None
        token = entry.get("last_reported")
        if not isinstance(token, str) or not token:
            token = entry.get("last_updated")
        if not isinstance(token, str) or not token:
            return None
        return ExternalTempSample(value, token, _parse_epoch(token))

    def _suspicious_detail(
        self,
        previous: Optional[ExternalTempSample],
        current: ExternalTempSample,
    ) -> str:
        p = self.policy
        value = current.value_c
        if p.min_plausible_c is not None and value < float(p.min_plausible_c):
            return f"temperature {value:.2f}C below calibrated plausible minimum"
        if p.max_plausible_c is not None and value > float(p.max_plausible_c):
            return f"temperature {value:.2f}C above calibrated plausible maximum"
        if previous is None:
            return ""
        delta = abs(value - previous.value_c)
        if p.max_step_c is not None and delta > float(p.max_step_c):
            return f"temperature step {delta:.2f}C exceeds calibrated limit"
        if (
            p.max_slope_c_per_min is not None
            and previous.source_epoch_s is not None
            and current.source_epoch_s is not None
        ):
            dt_s = current.source_epoch_s - previous.source_epoch_s
            if dt_s > 0:
                slope = delta * 60.0 / dt_s
                if slope > float(p.max_slope_c_per_min):
                    return f"temperature slope {slope:.2f}C/min exceeds calibrated limit"
        return ""

    def observe(self, live: Mapping[str, Any], *, hv: bool = False) -> ExternalTempIntegrityDecision:
        if not self.enabled or self._latched:
            return ExternalTempIntegrityDecision(anomaly_count=self._anomaly_count)
        sample = self._sample(live)
        if sample is None:
            return ExternalTempIntegrityDecision(anomaly_count=self._anomaly_count)
        if sample.source_token == self._last_source_token:
            return ExternalTempIntegrityDecision(anomaly_count=self._anomaly_count)

        previous = self._last_sample
        self._last_sample = sample
        self._last_source_token = sample.source_token
        detail = self._suspicious_detail(previous, sample)
        if not detail:
            self._anomaly_count = 0
            return ExternalTempIntegrityDecision(new_source_sample=True)

        self._anomaly_count += 1
        limit = self.policy.limit(hv=hv)
        trip = limit is not None and self._anomaly_count >= limit
        if trip:
            self._latch(detail, sample.source_token)
        return ExternalTempIntegrityDecision(
            new_source_sample=True,
            suspicious=True,
            anomaly_count=self._anomaly_count,
            trip=trip,
            detail=detail,
        )

    def _latch(self, reason: str, source_token: str) -> None:
        self._latched = True
        self._latch_reason = str(reason)
        self._latch_source_token = str(source_token)
        self._rearm_baseline = None
        document = {
            "latched": True,
            "reason": self._latch_reason,
            "source_token": self._latch_source_token,
            "tripped_at": time.time(),
        }
        tmp = f"{self.fault_file}.tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as handle:
                json.dump(document, handle, ensure_ascii=False, indent=2)
            os.replace(tmp, self.fault_file)
        except OSError:
            try:
                if os.path.exists(tmp):
                    os.remove(tmp)
            except OSError:
                pass

    def _load_latch(self) -> None:
        if not self.fault_file or not os.path.exists(self.fault_file):
            return
        try:
            with open(self.fault_file, "r", encoding="utf-8") as handle:
                document = json.load(handle)
        except (OSError, json.JSONDecodeError, TypeError):
            return
        if not bool(document.get("latched")):
            return
        self._latched = True
        self._latch_reason = str(document.get("reason") or "external temperature integrity fault")
        token = document.get("source_token")
        self._latch_source_token = str(token) if token else None

    def can_rearm(self, live: Mapping[str, Any], *, hv: bool = False) -> tuple[bool, str]:
        if not self._latched:
            return True, ""
        if not self.enabled:
            return False, "calibrated external-temperature integrity policy is unavailable"
        sample = self._sample(live)
        if sample is None:
            return False, "fresh external-temperature source identity is unavailable"
        if sample.source_token == self._latch_source_token:
            return False, "external-temperature source has not produced a new report since the trip"
        if self._rearm_baseline is None:
            detail = self._suspicious_detail(None, sample)
            self._rearm_baseline = sample
            if detail:
                return False, detail
            return False, "one clean report observed; another distinct clean report is required"
        if sample.source_token == self._rearm_baseline.source_token:
            return False, "waiting for another distinct external-temperature source report"
        detail = self._suspicious_detail(self._rearm_baseline, sample)
        self._rearm_baseline = sample
        if detail:
            return False, detail
        return True, ""

    def clear_latch(self) -> None:
        self._latched = False
        self._latch_reason = ""
        self._latch_source_token = None
        self._anomaly_count = 0
        self._last_sample = self._rearm_baseline
        self._last_source_token = (
            self._rearm_baseline.source_token if self._rearm_baseline is not None else None
        )
        self._rearm_baseline = None
        try:
            if self.fault_file and os.path.exists(self.fault_file):
                os.remove(self.fault_file)
        except OSError:
            pass
