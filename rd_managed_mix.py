from __future__ import annotations

import asyncio
import json
import math
import os
import tempfile
import time
import uuid
from dataclasses import dataclass, replace
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from ha_history import HomeAssistantHistoryError, HomeAssistantHistoryReader, MixHistoryEvidence
from pb_domain import BatteryChemistry
from rd6018_telemetry import RegulationMode, finite_float, resolve_regulation
from rd_live_adoption import MIX_FINISH_HOLD_S, MIX_HARD_LIMIT_HOURS
from rd_managed_adoption import (
    ADOPTION_SETPOINT_TOLERANCE,
    ManagedAdoptionFingerprint,
    ManagedLiveAdoptionCoordinator,
)
from recipe_engine import POLICIES
from runtime_safety import RuntimeSafetyError, _binary
from signal_analyzer import SignalAnalyzer, SignalEvent, SignalSample


ADOPTED_MIX_POLL_S = 5.0
# Keep the D062 public name while sharing the canonical D061 authority/readback
# tolerance. This prevents the two adopted-live paths from drifting semantically.
ADOPTED_MIX_SETPOINT_TOLERANCE = ADOPTION_SETPOINT_TOLERANCE


class ManagedMixState(str, Enum):
    IDLE = "idle"
    ADOPTION_PENDING = "adoption_pending"
    ACTIVE = "active"
    OFF_PENDING = "off_pending"
    INTERRUPTED = "interrupted"
    COMPLETED = "completed"
    FAILED = "failed"


class PriorMixAgeSource(str, Enum):
    RECORDER = "recorder"
    OPERATOR_DECLARED = "operator_declared"


@dataclass(frozen=True)
class PriorMixAge:
    elapsed_s: float
    source: PriorMixAgeSource
    observed_at_s: float


@dataclass(frozen=True)
class ManagedMixPreview:
    token: str
    battery_id: str
    chemistry: BatteryChemistry
    capacity_ah: float
    fingerprint: ManagedAdoptionFingerprint
    prior_age: PriorMixAge
    history: Optional[MixHistoryEvidence] = None


def _finite_nonnegative(value: Any, *, field: str) -> float:
    if value is None or isinstance(value, bool):
        raise RuntimeSafetyError(f"{field} is required")
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise RuntimeSafetyError(f"{field} is invalid") from exc
    if not math.isfinite(parsed) or parsed < 0:
        raise RuntimeSafetyError(f"{field} is invalid")
    return parsed


def _aged_elapsed(elapsed_s: float, observed_at_s: float, now_s: float) -> float:
    elapsed = _finite_nonnegative(elapsed_s, field="prior Mix age")
    observed = float(observed_at_s)
    now = float(now_s)
    if not math.isfinite(observed) or not math.isfinite(now):
        raise RuntimeSafetyError("prior Mix age timestamp is invalid")
    return elapsed + max(0.0, now - observed)


def resolve_prior_mix_age(
    history: Optional[MixHistoryEvidence],
    *,
    declared_elapsed_s: Optional[float] = None,
    declared_at_s: Optional[float] = None,
    now_s: Optional[float] = None,
) -> PriorMixAge:
    """Resolve an initial D063 age without inventing a new chemistry window.

    Recorder counts only with an explicit uninterrupted OFF->ON edge. An operator
    declaration is explicit evidence. When both exist the larger value wins: operator
    knowledge may conservatively extend, never shorten, Recorder evidence.
    """

    now = float(now_s if now_s is not None else time.time())
    candidates: list[PriorMixAge] = []
    if history is not None and history.output.reliable and history.output.elapsed_s is not None:
        elapsed = _aged_elapsed(history.output.elapsed_s, history.fetched_at_s, now)
        candidates.append(PriorMixAge(elapsed, PriorMixAgeSource.RECORDER, now))
    if declared_elapsed_s is not None:
        observed = float(declared_at_s if declared_at_s is not None else now)
        elapsed = _aged_elapsed(declared_elapsed_s, observed, now)
        candidates.append(PriorMixAge(elapsed, PriorMixAgeSource.OPERATOR_DECLARED, now))
    if not candidates:
        raise RuntimeSafetyError(
            "prior external Mix age is not proven; declare elapsed active time or remain HANDS_OFF/Manual/OFF"
        )
    return max(candidates, key=lambda item: item.elapsed_s)


class ManagedMixAdoptionCoordinator:
    """D062 MIX_ADOPTED authority built on the D061 live edge primitive.

    Ownership transfer itself is non-actuating. The external program is accepted only
    when it is already a protected high-voltage Mix inside the selected chemistry
    envelope. Prior active time is carried into the hard Mix budget. Delta evidence is
    strictly post-adoption. Normal completion is verified Output OFF, never
    SAFE_WAIT/Storage. Process restart never resumes this high-voltage authority.
    """

    VERSION = 1

    def __init__(
        self,
        app: Any,
        manager: Any,
        d061: ManagedLiveAdoptionCoordinator,
        *,
        state_file: str = "rd_managed_mix_adoption_v2.json",
        poll_s: float = ADOPTED_MIX_POLL_S,
        monotonic=time.monotonic,
        wall_time=time.time,
        history_reader: Optional[HomeAssistantHistoryReader] = None,
    ) -> None:
        self.app = app
        self.manager = manager
        self.guard = manager.guard
        self.d061 = d061
        self.edge = d061.edge
        self.state_file = str(state_file)
        self.poll_s = max(1.0, float(poll_s))
        self._monotonic = monotonic
        self._wall_time = wall_time
        self.history_reader = history_reader or HomeAssistantHistoryReader(app.hass, app.ENTITY_MAP)
        self.state = ManagedMixState.IDLE
        self.session_id = ""
        self.battery_id = ""
        self.chemistry: Optional[BatteryChemistry] = None
        self.capacity_ah = 0.0
        self.max_authority: Optional[ManagedAdoptionFingerprint] = None
        self.current_authority: Optional[ManagedAdoptionFingerprint] = None
        self.prior_elapsed_s = 0.0
        self.prior_age_source = ""
        self.adopted_active_elapsed_s = 0.0
        self.started_at_s = 0.0
        self.last_source_timestamp_s: Optional[float] = None
        self.finish_hold_started_at_s: Optional[float] = None
        self.terminal_reason = ""
        self.last_status = ""
        self._active_anchor_mono: Optional[float] = None
        self._finish_hold_anchor_mono: Optional[float] = None
        self._task: Optional[asyncio.Task] = None
        self.analyzer = SignalAnalyzer()
        self._restore()

    @property
    def active(self) -> bool:
        return self.state is ManagedMixState.ACTIVE

    @property
    def off_pending(self) -> bool:
        return self.state is ManagedMixState.OFF_PENDING

    @property
    def managed_authority(self) -> bool:
        return self.active or self.off_pending

    @property
    def hard_limit_s(self) -> Optional[float]:
        if self.chemistry is None:
            return None
        hours = MIX_HARD_LIMIT_HOURS.get(self.chemistry)
        return None if hours is None else float(hours) * 3600.0

    @property
    def total_active_elapsed_s(self) -> float:
        elapsed = float(self.prior_elapsed_s) + float(self.adopted_active_elapsed_s)
        if self.active and self._active_anchor_mono is not None:
            delta = float(self._monotonic()) - float(self._active_anchor_mono)
            if math.isfinite(delta) and delta > 0:
                elapsed += delta
        return max(0.0, elapsed)

    @property
    def remaining_budget_s(self) -> Optional[float]:
        limit = self.hard_limit_s
        return None if limit is None else max(0.0, limit - self.total_active_elapsed_s)

    @staticmethod
    def _parse_fp(raw: Any) -> Optional[ManagedAdoptionFingerprint]:
        if not isinstance(raw, dict):
            return None
        try:
            values = tuple(float(raw[key]) for key in (
                "set_voltage_v", "set_current_a", "ovp_v", "ocp_a"
            ))
        except (KeyError, TypeError, ValueError):
            return None
        if not all(math.isfinite(value) and value > 0 for value in values):
            return None
        return ManagedAdoptionFingerprint(*values)

    def _document(self) -> dict[str, Any]:
        def fp(value: Optional[ManagedAdoptionFingerprint]) -> Optional[dict[str, float]]:
            if value is None:
                return None
            return {
                "set_voltage_v": value.set_voltage_v,
                "set_current_a": value.set_current_a,
                "ovp_v": value.ovp_v,
                "ocp_a": value.ocp_a,
            }

        return {
            "version": self.VERSION,
            "state": self.state.value,
            "session_id": self.session_id,
            "battery_id": self.battery_id,
            "chemistry": self.chemistry.value if self.chemistry is not None else None,
            "capacity_ah": self.capacity_ah,
            "max_authority": fp(self.max_authority),
            "current_authority": fp(self.current_authority),
            "prior_elapsed_s": self.prior_elapsed_s,
            "prior_age_source": self.prior_age_source,
            "adopted_active_elapsed_s": self.adopted_active_elapsed_s,
            "started_at_s": self.started_at_s,
            "last_source_timestamp_s": self.last_source_timestamp_s,
            "finish_hold_started_at_s": self.finish_hold_started_at_s,
            "terminal_reason": self.terminal_reason,
            "last_status": self.last_status,
            "saved_at_s": float(self._wall_time()),
        }

    def _persist(self) -> None:
        path = os.path.abspath(self.state_file)
        directory = os.path.dirname(path) or "."
        os.makedirs(directory, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(prefix=".rd-managed-mix-", suffix=".tmp", dir=directory, text=True)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(self._document(), handle, ensure_ascii=False, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_path, path)
            try:
                dir_fd = os.open(directory, os.O_RDONLY)
                try:
                    os.fsync(dir_fd)
                finally:
                    os.close(dir_fd)
            except OSError:
                pass
        finally:
            try:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
            except OSError:
                pass

    def _restore(self) -> None:
        if not os.path.exists(self.state_file):
            return
        try:
            with open(self.state_file, "r", encoding="utf-8") as handle:
                raw = json.load(handle)
            if not isinstance(raw, dict) or int(raw.get("version")) != self.VERSION:
                return
            previous = ManagedMixState(str(raw.get("state") or "idle"))
            self.session_id = str(raw.get("session_id") or "")
            self.battery_id = str(raw.get("battery_id") or "")
            chemistry = raw.get("chemistry")
            self.chemistry = BatteryChemistry(str(chemistry)) if chemistry else None
            self.capacity_ah = float(raw.get("capacity_ah") or 0.0)
            self.max_authority = self._parse_fp(raw.get("max_authority"))
            self.current_authority = self._parse_fp(raw.get("current_authority"))
            self.prior_elapsed_s = _finite_nonnegative(raw.get("prior_elapsed_s", 0.0), field="prior_elapsed_s")
            self.prior_age_source = str(raw.get("prior_age_source") or "")
            self.adopted_active_elapsed_s = _finite_nonnegative(
                raw.get("adopted_active_elapsed_s", 0.0), field="adopted_active_elapsed_s"
            )
            self.started_at_s = float(raw.get("started_at_s") or 0.0)
            self.last_source_timestamp_s = finite_float(raw.get("last_source_timestamp_s"))
            self.finish_hold_started_at_s = finite_float(raw.get("finish_hold_started_at_s"))
            self.terminal_reason = str(raw.get("terminal_reason") or "")
            self.last_status = str(raw.get("last_status") or "")
            if previous in {
                ManagedMixState.ADOPTION_PENDING,
                ManagedMixState.ACTIVE,
                ManagedMixState.OFF_PENDING,
            }:
                self.state = ManagedMixState.OFF_PENDING
                self.finish_hold_started_at_s = None
                self.last_source_timestamp_s = None
                self.last_status = (
                    "process_restart: MIX_ADOPTED authority is never resumed; verified Output OFF pending"
                )
                self._persist()
            else:
                self.state = previous
        except (OSError, ValueError, TypeError, json.JSONDecodeError, RuntimeSafetyError):
            self.state = ManagedMixState.IDLE

    def _chemistry_preflight(
        self,
        chemistry: BatteryChemistry,
        capacity_ah: float,
        fingerprint: ManagedAdoptionFingerprint,
    ) -> None:
        if chemistry not in MIX_HARD_LIMIT_HOURS or chemistry is BatteryChemistry.CUSTOM:
            raise RuntimeSafetyError("MIX_ADOPTED requires a supported Pb chemistry")
        capacity = _finite_nonnegative(capacity_ah, field="battery capacity")
        if capacity <= 0:
            raise RuntimeSafetyError("MIX_ADOPTED requires positive battery capacity")
        policy = POLICIES[chemistry]
        tol = ADOPTED_MIX_SETPOINT_TOLERANCE
        if fingerprint.set_voltage_v <= policy.normal_voltage_ceiling_v + tol:
            raise RuntimeSafetyError("MIX_ADOPTED requires an already-running high-voltage Mix program")
        if fingerprint.set_voltage_v > policy.recovery_voltage_ceiling_v + tol:
            raise RuntimeSafetyError(
                f"live Mix voltage {fingerprint.set_voltage_v:.2f}V exceeds {chemistry.value} envelope "
                f"{policy.recovery_voltage_ceiling_v:.2f}V"
            )
        hv_current_limit = min(
            float(self.guard.policy.absolute_current_ceiling_a),
            capacity * float(policy.hv_current_c_max),
        )
        if fingerprint.set_current_a > hv_current_limit + tol:
            raise RuntimeSafetyError(
                f"live Mix current {fingerprint.set_current_a:.2f}A exceeds chemistry HV envelope "
                f"{hv_current_limit:.2f}A"
            )

    def _preflight_mix_live(
        self,
        live: dict[str, Any],
        *,
        chemistry: BatteryChemistry,
        capacity_ah: float,
        expected: Optional[ManagedAdoptionFingerprint] = None,
    ) -> ManagedAdoptionFingerprint:
        fingerprint = self.d061._preflight_live(live, expected=expected)
        self._chemistry_preflight(chemistry, capacity_ah, fingerprint)
        return fingerprint

    def _conflict(self) -> Optional[str]:
        controller = getattr(self.app, "charge_controller", None)
        if controller is not None and bool(getattr(controller, "is_active", False)):
            return "AUTO controller is already active"
        manual = getattr(self.app, "manual_session_manager", None)
        if manual is not None and bool(getattr(manual, "is_active", False)):
            return "Manual controller is already active"
        if self.d061.active or self.d061.off_pending:
            return "D061 Adopted Manual already owns managed authority"
        observer = getattr(self.app, "rd_live_mix_observer", None)
        if observer is not None:
            raw = getattr(observer, "state", None)
            state = str(getattr(raw, "value", raw) or "")
            if state in {"active", "off_pending"}:
                return "HANDS_OFF Mix observer already owns safety/OFF authority"
        return None

    async def _fresh_prior_age(self, preview: ManagedMixPreview, live: dict[str, Any]) -> PriorMixAge:
        """Revalidate D063 age without ever decreasing the already accepted floor."""

        now = float(self._wall_time())
        floor = PriorMixAge(
            _aged_elapsed(preview.prior_age.elapsed_s, preview.prior_age.observed_at_s, now),
            preview.prior_age.source,
            now,
        )
        try:
            history = await self.history_reader.read_mix_evidence(live=live)
        except HomeAssistantHistoryError:
            return floor
        if not history.output.reliable or history.output.elapsed_s is None:
            return floor
        fresh = PriorMixAge(
            _aged_elapsed(history.output.elapsed_s, history.fetched_at_s, now),
            PriorMixAgeSource.RECORDER,
            now,
        )
        return fresh if fresh.elapsed_s > floor.elapsed_s else floor

    def _require_budget(self, chemistry: BatteryChemistry, prior_elapsed_s: float) -> None:
        limit_h = MIX_HARD_LIMIT_HOURS.get(chemistry)
        if limit_h is None:
            raise RuntimeSafetyError("MIX_ADOPTED chemistry has no hard Mix limit")
        if float(prior_elapsed_s) >= float(limit_h) * 3600.0:
            raise RuntimeSafetyError(
                f"prior Mix age {float(prior_elapsed_s) / 3600.0:.2f}h already exhausts "
                f"{chemistry.value} hard limit {limit_h:g}h; managed Mix adoption is forbidden"
            )

    @staticmethod
    def _source_timestamp(live: dict[str, Any]) -> Optional[float]:
        meta = live.get("_meta")
        if not isinstance(meta, dict):
            return None
        values: list[float] = []
        for key in (
            "current", "battery_voltage", "temp_ext_v2", "temp_ext",
            "regulation_code", "is_cv", "is_cc",
        ):
            item = meta.get(key)
            if not isinstance(item, dict):
                continue
            raw = item.get("last_reported") or item.get("last_updated")
            if not isinstance(raw, str) or not raw:
                continue
            text = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
            try:
                parsed = datetime.fromisoformat(text).timestamp()
            except (ValueError, OverflowError):
                continue
            if math.isfinite(parsed) and parsed > 0:
                values.append(parsed)
        return min(values) if values else None

    def _reset_delta_epoch(
        self,
        fingerprint: ManagedAdoptionFingerprint,
        reason: str,
        *,
        source_barrier_s: Optional[float] = None,
    ) -> None:
        self.current_authority = fingerprint
        self.finish_hold_started_at_s = None
        self._finish_hold_anchor_mono = None
        self.last_source_timestamp_s = (
            float(source_barrier_s)
            if source_barrier_s is not None
            else float(self._wall_time())
        )
        self.analyzer.reset_stage("MIX_ADOPTED", target_voltage_v=fingerprint.set_voltage_v)
        self.last_status = reason
        self._persist()

    def _advance_active_clock(self) -> None:
        if not self.active:
            self._active_anchor_mono = None
            return
        now = float(self._monotonic())
        if self._active_anchor_mono is None:
            self._active_anchor_mono = now
            return
        delta = now - float(self._active_anchor_mono)
        if not math.isfinite(delta) or delta < 0:
            raise RuntimeSafetyError("MIX_ADOPTED monotonic active-time clock moved backwards")
        self.adopted_active_elapsed_s += delta
        self._active_anchor_mono = now

    async def adopt(self, preview: ManagedMixPreview) -> bool:
        """Acquire D062 authority with an explicit local edge uncertainty boundary."""

        edge_command_uncertain = False
        async with self.manager._transition_lock:
            if self.active or self.off_pending:
                raise RuntimeSafetyError("MIX_ADOPTED already owns pending state")
            if not bool(getattr(self.manager, "hands_off", False)):
                raise RuntimeSafetyError("MIX_ADOPTED requires durable HANDS_OFF")
            if bool(getattr(self.guard, "_off_unconfirmed", False)):
                raise RuntimeSafetyError("MIX_ADOPTED blocked: previous Output OFF is unconfirmed")
            conflict = self._conflict()
            if conflict is not None:
                raise RuntimeSafetyError(f"MIX_ADOPTED blocked: {conflict}")
            if self.edge is None:
                raise RuntimeSafetyError("MIX_ADOPTED requires the D061 local edge adoption primitive")

            self.manager._release_in_progress = True
            try:
                first = await self.guard._raw_live()
                self._preflight_mix_live(
                    first,
                    chemistry=preview.chemistry,
                    capacity_ah=preview.capacity_ah,
                    expected=preview.fingerprint,
                )
                age = await self._fresh_prior_age(preview, first)
                self._require_budget(preview.chemistry, age.elapsed_s)

                self.state = ManagedMixState.ADOPTION_PENDING
                self.session_id = uuid.uuid4().hex
                self.battery_id = preview.battery_id
                self.chemistry = preview.chemistry
                self.capacity_ah = float(preview.capacity_ah)
                self.max_authority = preview.fingerprint
                self.current_authority = preview.fingerprint
                self.prior_elapsed_s = float(age.elapsed_s)
                self.prior_age_source = age.source.value
                self.adopted_active_elapsed_s = 0.0
                self.started_at_s = float(self._wall_time())
                self.last_source_timestamp_s = None
                self.finish_hold_started_at_s = None
                self.terminal_reason = ""
                self.last_status = "D063 age accepted; edge live ownership acquisition pending"
                self._persist()

                # prepare() and the second HA/chemistry TOCTOU are read-only. Even if
                # the edge object's old diagnostic flag is stale True from an earlier
                # operation, failure here MUST NOT turn an external HANDS_OFF program off.
                prepared = await self.edge.prepare()
                second = await self.guard._raw_live()
                self._preflight_mix_live(
                    second,
                    chemistry=preview.chemistry,
                    capacity_ah=preview.capacity_ah,
                    expected=preview.fingerprint,
                )

                try:
                    await self.edge.adopt(expected_generation=prepared.generation)
                finally:
                    # From this exact invocation boundary onward transport/ACK loss can
                    # mean the edge command executed. Only now is OFF containment legal.
                    edge_command_uncertain = bool(
                        getattr(self.edge, "command_may_have_executed", True)
                    )

                third = await self.guard._raw_live()
                fingerprint = self._preflight_mix_live(
                    third,
                    chemistry=preview.chemistry,
                    capacity_ah=preview.capacity_ah,
                    expected=preview.fingerprint,
                )

                self.manager._clear_stale_auto_restore_authority()
                pb_mode = type(self.manager.mode).PB_MANAGED
                self.manager._write_mode(pb_mode)
                self.manager.mode = pb_mode
                self.guard._orphan_output_seen_at = None

                self.current_authority = fingerprint
                self.state = ManagedMixState.ACTIVE
                self.started_at_s = float(self._wall_time())
                self._active_anchor_mono = float(self._monotonic())
                self._finish_hold_anchor_mono = None
                source_barrier = self._source_timestamp(third)
                self.last_source_timestamp_s = (
                    source_barrier if source_barrier is not None else self.started_at_s
                )
                self.analyzer.reset_stage("MIX_ADOPTED", target_voltage_v=fingerprint.set_voltage_v)
                self.last_status = (
                    f"MIX_ADOPTED active; prior={self.prior_elapsed_s / 3600.0:.2f}h "
                    f"source={self.prior_age_source}; waiting for fresh post-adoption Delta"
                )
                self._persist()
                self._task = asyncio.create_task(self._run(), name="rd6018-managed-mix-adoption")
                return True
            except Exception as exc:
                if edge_command_uncertain:
                    await self.force_verified_off(
                        f"MIX_ADOPTED_INCOMPLETE_AFTER_EDGE:{type(exc).__name__}:{exc}",
                        failed=True,
                    )
                else:
                    self.state = ManagedMixState.FAILED
                    self.terminal_reason = "ADOPTION_PREFLIGHT_FAILED"
                    self.last_status = f"MIX_ADOPTED preflight failed: {type(exc).__name__}: {exc}"
                    self._persist()
                raise
            finally:
                self.manager._release_in_progress = False

    def authorize_managed_write(self, field: str, value: float) -> None:
        if not self.managed_authority:
            return
        authority = self.current_authority
        requested = finite_float(value)
        if authority is None or requested is None:
            raise RuntimeSafetyError("MIX_ADOPTED write authority is unavailable")
        ceiling = float(getattr(authority, field))
        if float(requested) > ceiling + ADOPTED_MIX_SETPOINT_TOLERANCE:
            raise RuntimeSafetyError(
                f"MIX_ADOPTED {field} increase blocked: {float(requested):.3f} > {ceiling:.3f}"
            )

    def ratchet_after_managed_write(self, field: str, value: float) -> None:
        if not self.active or self.current_authority is None:
            return
        requested = finite_float(value)
        if requested is None:
            return
        old = self.current_authority
        current = replace(old, **{field: min(float(getattr(old, field)), float(requested))})
        if current != old:
            self._reset_delta_epoch(
                current,
                f"managed {field} decrease ratcheted authority; fresh Delta epoch restarted",
            )

    async def force_verified_off(self, reason: str, *, failed: bool = True) -> bool:
        self._advance_active_clock()
        self.state = ManagedMixState.OFF_PENDING
        self.terminal_reason = str(reason)
        self.finish_hold_started_at_s = None
        self._finish_hold_anchor_mono = None
        self.last_status = f"{reason}: verified Output OFF pending"
        self._persist()
        try:
            if bool(getattr(self.manager, "hands_off", False)):
                ok = bool(await self.manager.operator_output_off(self.app.ENTITY_MAP.get("switch")))
            else:
                ok = bool(await self.app.hass.turn_off(self.app.ENTITY_MAP.get("switch")))
        except Exception as exc:
            self.last_status = f"{reason}: Output OFF unconfirmed: {type(exc).__name__}: {exc}"
            self._persist()
            return False
        if not ok:
            self.last_status = f"{reason}: Output OFF unconfirmed"
            self._persist()
            return False
        self._active_anchor_mono = None
        self.state = ManagedMixState.FAILED if failed else ManagedMixState.COMPLETED
        self.last_status = f"{reason}: Output verified OFF"
        self._persist()
        return True

    async def stop_by_operator(self) -> bool:
        return await self.force_verified_off("OPERATOR_STOP", failed=False)

    async def _external_off_complete(self) -> None:
        lease = getattr(self.guard, "edge_safety_lease", None)
        if lease is not None:
            try:
                await lease.disarm()
            except Exception:
                pass
        self._advance_active_clock()
        self._active_anchor_mono = None
        self.state = ManagedMixState.COMPLETED
        self.terminal_reason = "OUTPUT_OFF_EXTERNAL"
        self.last_status = "Output became OFF; MIX_ADOPTED authority retired"
        self._persist()

    async def observe_once(self) -> None:
        if self.off_pending:
            await self.force_verified_off(self.terminal_reason or "OFF_PENDING", failed=True)
            return
        if not self.active:
            return
        if not bool(getattr(self.manager, "pb_managed", False)):
            await self.force_verified_off("MIX_ADOPTED_LOST_PB_MANAGED", failed=True)
            return

        live = await self.app.hass.get_all_live()
        output_state = _binary(live.get("switch"))
        if output_state is False:
            await self._external_off_complete()
            return
        if output_state is not True:
            await self.force_verified_off("MIX_ADOPTED_OUTPUT_UNKNOWN", failed=True)
            return

        self._advance_active_clock()
        fingerprint = self.d061.fingerprint_from_live(live)
        authority = self.current_authority
        if fingerprint is None or authority is None:
            await self.force_verified_off("MIX_ADOPTED_PROGRAM_READBACK_LOST", failed=True)
            return

        increases: list[str] = []
        for field in ("set_voltage_v", "set_current_a", "ovp_v", "ocp_a"):
            actual = float(getattr(fingerprint, field))
            ceiling = float(getattr(authority, field))
            if actual > ceiling + ADOPTED_MIX_SETPOINT_TOLERANCE:
                increases.append(f"{field}:{actual:.3f}>{ceiling:.3f}")
        if increases:
            await self.force_verified_off(
                "MIX_ADOPTED_OUT_OF_BAND_INCREASE:" + ",".join(increases), failed=True
            )
            return

        ratcheted = ManagedAdoptionFingerprint(
            set_voltage_v=min(authority.set_voltage_v, fingerprint.set_voltage_v),
            set_current_a=min(authority.set_current_a, fingerprint.set_current_a),
            ovp_v=min(authority.ovp_v, fingerprint.ovp_v),
            ocp_a=min(authority.ocp_a, fingerprint.ocp_a),
        )
        if ratcheted != authority:
            try:
                assert self.chemistry is not None
                self._chemistry_preflight(self.chemistry, self.capacity_ah, ratcheted)
            except Exception as exc:
                await self.force_verified_off(
                    f"MIX_ADOPTED_RATCHET_INVALID:{type(exc).__name__}:{exc}", failed=True
                )
                return
            self._reset_delta_epoch(
                ratcheted,
                "external V/I/protection decrease ratcheted authority; fresh Delta epoch restarted",
                source_barrier_s=self._source_timestamp(live),
            )

        limit = self.hard_limit_s
        if (
            limit is not None
            and self.finish_hold_started_at_s is None
            and self.total_active_elapsed_s >= limit
        ):
            await self.force_verified_off("MIX_TIMEOUT", failed=True)
            self._notify(
                "🛑 <b>MIX_ADOPTED:</b> chemistry active-time budget exhausted before accepted Delta hold. "
                "Output verified OFF; diagnose before another automatic HV window."
            )
            return

        source_timestamp = self._source_timestamp(live)
        if source_timestamp is None:
            raise RuntimeSafetyError("MIX_ADOPTED source timestamps unavailable")
        if self.last_source_timestamp_s is not None and source_timestamp <= self.last_source_timestamp_s:
            self._persist()
            return

        voltage = finite_float(live.get("battery_voltage"))
        current = finite_float(live.get("current"))
        temp = finite_float(live.get("temp_ext_v2"))
        if temp is None:
            temp = finite_float(live.get("temp_ext"))
        regulation = resolve_regulation(live)
        if voltage is None or current is None or temp is None or regulation not in {
            RegulationMode.CV, RegulationMode.CC
        }:
            raise RuntimeSafetyError("MIX_ADOPTED coherent U/I/T/CV-CC sample unavailable")

        self.last_source_timestamp_s = source_timestamp
        analysis = self.analyzer.observe(
            SignalSample(
                timestamp_s=source_timestamp,
                voltage_v=float(voltage),
                current_a=float(current),
                temp_c=float(temp),
                is_cv=regulation is RegulationMode.CV,
                is_cc=regulation is RegulationMode.CC,
            )
        )
        metrics = analysis.metrics
        self.last_status = (
            f"{regulation.value}: used={self.total_active_elapsed_s / 3600.0:.2f}h "
            f"Imin={metrics.current_min_a!r} dI={metrics.delta_current_from_min_a!r} "
            f"Vmax={metrics.voltage_max_v!r} dV={metrics.delta_voltage_from_max_v!r}"
        )

        if SignalEvent.END_OF_CHARGE_LIKELY in analysis.events and self.finish_hold_started_at_s is None:
            self.finish_hold_started_at_s = float(self._wall_time())
            self._finish_hold_anchor_mono = float(self._monotonic())
            self.last_status = "fresh post-adoption Delta accepted; sticky 2h finish hold started"
            self._notify(
                "🎯 <b>MIX_ADOPTED:</b> свежая Delta подтверждена после adoption. "
                "Начата sticky 2ч выдержка; HA history не использовалась как Delta evidence."
            )

        if self._finish_hold_anchor_mono is not None:
            held = float(self._monotonic()) - float(self._finish_hold_anchor_mono)
            if not math.isfinite(held) or held < 0:
                raise RuntimeSafetyError("MIX_ADOPTED finish-hold monotonic clock moved backwards")
            if held >= MIX_FINISH_HOLD_S:
                await self.force_verified_off("DELTA_HOLD_COMPLETE", failed=False)
                self._notify(
                    "⏹ <b>MIX_ADOPTED завершён:</b> свежая Delta + 2ч. Output подтверждён OFF. "
                    "SAFE_WAIT/Storage не запускались."
                )
                return
        self._persist()

    def _notify(self, message: str) -> None:
        callback = getattr(self.app, "_charge_notify", None)
        if callable(callback):
            try:
                callback(message, critical=False)
            except TypeError:
                callback(message)
            except Exception:
                pass

    async def _run(self) -> None:
        try:
            while self.active or self.off_pending:
                await self.observe_once()
                if not (self.active or self.off_pending):
                    break
                await asyncio.sleep(self.poll_s)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            if self.active or self.off_pending:
                await self.force_verified_off(
                    f"MIX_ADOPTED_RUNTIME_ERROR:{type(exc).__name__}:{exc}", failed=True
                )

    async def recover_startup(self) -> bool:
        if not self.off_pending:
            return True
        ok = await self.force_verified_off(
            self.terminal_reason or "MIX_ADOPTED_RESTART_CONTAINMENT", failed=True
        )
        if ok:
            self.state = ManagedMixState.INTERRUPTED
            self.last_status = "restart containment completed; fresh operator program is required"
            self._persist()
        return ok


def install_runtime_composition(app: Any, coordinator: ManagedMixAdoptionCoordinator) -> None:
    """Integrate MIX_ADOPTED into the actual strict V2 runtime-safety owner model."""

    guard = coordinator.guard
    cls = type(guard)
    if not bool(getattr(cls, "_d062_managed_mix_hooks", False)):
        old_controller_active = cls.controller_active
        old_recipe_voltage_ceiling = cls._recipe_voltage_ceiling
        old_stage_target = cls._stage_target
        old_temp_hv = getattr(cls, "_temp_integrity_hv_active", None)
        old_retire_temp = getattr(cls, "_retire_temp_integrity_session", None)

        def controller_active(self: Any) -> bool:
            base = bool(old_controller_active.fget(self)) if isinstance(old_controller_active, property) else False
            mix = getattr(self.app, "rd_managed_mix_adoption", None)
            return base or bool(mix is not None and getattr(mix, "managed_authority", False))

        def recipe_voltage_ceiling(self: Any) -> float:
            mix = getattr(self.app, "rd_managed_mix_adoption", None)
            authority = getattr(mix, "current_authority", None) if mix is not None else None
            chemistry = getattr(mix, "chemistry", None) if mix is not None else None
            if bool(mix is not None and getattr(mix, "managed_authority", False)) and authority is not None:
                ceiling = float(authority.set_voltage_v)
                if chemistry in POLICIES:
                    ceiling = min(ceiling, float(POLICIES[chemistry].recovery_voltage_ceiling_v))
                return min(ceiling, float(self.policy.absolute_voltage_ceiling_v))
            return float(old_recipe_voltage_ceiling(self))

        def stage_target(self: Any, live: dict[str, Any]) -> tuple[Optional[float], Optional[float]]:
            mix = getattr(self.app, "rd_managed_mix_adoption", None)
            authority = getattr(mix, "current_authority", None) if mix is not None else None
            if bool(mix is not None and getattr(mix, "managed_authority", False)) and authority is not None:
                return float(authority.set_voltage_v), float(authority.set_current_a)
            return old_stage_target(self, live)

        cls.controller_active = property(controller_active)
        cls._recipe_voltage_ceiling = recipe_voltage_ceiling
        cls._stage_target = stage_target

        if callable(old_temp_hv):
            def temp_hv(self: Any) -> bool:
                mix = getattr(self.app, "rd_managed_mix_adoption", None)
                authority = getattr(mix, "current_authority", None) if mix is not None else None
                if bool(mix is not None and getattr(mix, "managed_authority", False)) and authority is not None:
                    return float(authority.set_voltage_v) > 15.0
                return bool(old_temp_hv(self))
            cls._temp_integrity_hv_active = temp_hv

        if callable(old_retire_temp):
            async def retire_temp(self: Any, reason: str) -> None:
                mix = getattr(self.app, "rd_managed_mix_adoption", None)
                if bool(mix is not None and getattr(mix, "managed_authority", False)):
                    await mix.force_verified_off(f"external_temp_integrity:{reason}", failed=True)
                    return
                await old_retire_temp(self, reason)
            cls._retire_temp_integrity_session = retire_temp

        cls._d062_managed_mix_hooks = True

    hass = app.hass
    if bool(getattr(hass, "_d062_managed_mix_wrapped", False)):
        return
    original_turn_on = hass.turn_on
    original_set_voltage = hass.set_voltage
    original_set_current = hass.set_current
    original_set_ovp = hass.set_ovp
    original_set_ocp = hass.set_ocp

    async def turn_on(entity_id: Optional[str] = None) -> bool:
        mix = getattr(app, "rd_managed_mix_adoption", None)
        if mix is not None and mix.managed_authority:
            raise RuntimeSafetyError(
                "MIX_ADOPTED cannot re-energize Output; a fresh managed program is required"
            )
        return bool(await original_turn_on(entity_id))

    async def write(field: str, value: float, fn: Any) -> bool:
        mix = getattr(app, "rd_managed_mix_adoption", None)
        if mix is not None:
            mix.authorize_managed_write(field, value)
        result = bool(await fn(value))
        if result and mix is not None:
            mix.ratchet_after_managed_write(field, value)
        return result

    async def set_voltage(value: float) -> bool:
        return await write("set_voltage_v", value, original_set_voltage)

    async def set_current(value: float) -> bool:
        return await write("set_current_a", value, original_set_current)

    async def set_ovp(value: float) -> bool:
        return await write("ovp_v", value, original_set_ovp)

    async def set_ocp(value: float) -> bool:
        return await write("ocp_a", value, original_set_ocp)

    hass.turn_on = turn_on
    hass.set_voltage = set_voltage
    hass.set_current = set_current
    hass.set_ovp = set_ovp
    hass.set_ocp = set_ocp
    hass._d062_managed_mix_wrapped = True
