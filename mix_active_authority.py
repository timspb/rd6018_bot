from __future__ import annotations

import json
import math
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from charge_logic import SESSION_FILE


class MixActiveAuthorityError(RuntimeError):
    pass


@dataclass(frozen=True)
class MixActiveAuthoritySnapshot:
    session_id: str
    elapsed_s: float
    active: bool
    last_wall_s: Optional[float]
    terminal_reason: Optional[str] = None


class MixActiveTimeAuthority:
    """Durable monotonic authority clock for automatic Mix.

    Within one process, elapsed time advances from ``time.monotonic()`` only while
    Mix cannot be proved OFF.  The durable record stores accumulated elapsed time
    and whether the last proved state was active.  After a process restart, if the
    previous record was active, wall-clock downtime is conservatively charged as
    active time; it is never reconstructed from Ah or a legacy stage-start clock.

    This deliberately biases toward *less* remaining automatic HV authority when a
    crash leaves the physical Output state uncertain.
    """

    VERSION = 1

    def __init__(
        self,
        path: Optional[str | os.PathLike[str]] = None,
        *,
        monotonic=time.monotonic,
        wall_time=time.time,
    ) -> None:
        self.path = Path(path or f"{SESSION_FILE}.mix-authority.json")
        self._monotonic = monotonic
        self._wall_time = wall_time
        self._snapshot: Optional[MixActiveAuthoritySnapshot] = None
        self._anchor_mono: Optional[float] = None

    @staticmethod
    def _finite_nonnegative(value: Any, *, field: str) -> float:
        if isinstance(value, bool):
            raise MixActiveAuthorityError(f"{field} is invalid")
        try:
            parsed = float(value)
        except (TypeError, ValueError) as exc:
            raise MixActiveAuthorityError(f"{field} is invalid") from exc
        if not math.isfinite(parsed) or parsed < 0:
            raise MixActiveAuthorityError(f"{field} is invalid")
        return parsed

    @staticmethod
    def _finite_positive_wall(value: Any, *, field: str) -> float:
        parsed = MixActiveTimeAuthority._finite_nonnegative(value, field=field)
        if parsed <= 0:
            raise MixActiveAuthorityError(f"{field} is invalid")
        return parsed

    @property
    def snapshot(self) -> Optional[MixActiveAuthoritySnapshot]:
        return self._snapshot

    @property
    def elapsed_s(self) -> float:
        return float(self._snapshot.elapsed_s) if self._snapshot is not None else 0.0

    def _document(self, snapshot: MixActiveAuthoritySnapshot) -> dict[str, Any]:
        return {
            "version": self.VERSION,
            "session_id": snapshot.session_id,
            "elapsed_s": float(snapshot.elapsed_s),
            "active": bool(snapshot.active),
            "last_wall_s": snapshot.last_wall_s,
            "terminal_reason": snapshot.terminal_reason,
        }

    def _persist(self) -> None:
        snapshot = self._snapshot
        if snapshot is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(f".{self.path.name}.tmp")
        try:
            with open(tmp, "w", encoding="utf-8") as handle:
                json.dump(self._document(snapshot), handle, ensure_ascii=False, sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, self.path)
            try:
                dir_fd = os.open(str(self.path.parent), os.O_RDONLY)
            except OSError:
                dir_fd = None
            if dir_fd is not None:
                try:
                    os.fsync(dir_fd)
                finally:
                    os.close(dir_fd)
        finally:
            try:
                if tmp.exists():
                    tmp.unlink()
            except OSError:
                pass

    def _parse_document(self, raw: Any) -> MixActiveAuthoritySnapshot:
        if not isinstance(raw, dict) or raw.get("version") != self.VERSION:
            raise MixActiveAuthorityError("Mix active-time authority record is invalid")
        session_id = str(raw.get("session_id") or "").strip()
        if not session_id:
            raise MixActiveAuthorityError("Mix active-time authority session id is invalid")
        elapsed_s = self._finite_nonnegative(raw.get("elapsed_s"), field="elapsed_s")
        active = raw.get("active")
        if not isinstance(active, bool):
            raise MixActiveAuthorityError("Mix active-time authority active flag is invalid")
        last_wall_raw = raw.get("last_wall_s")
        if active:
            last_wall_s = self._finite_positive_wall(last_wall_raw, field="last_wall_s")
        else:
            last_wall_s = None
        terminal_raw = raw.get("terminal_reason")
        terminal_reason = None if terminal_raw in (None, "") else str(terminal_raw)
        return MixActiveAuthoritySnapshot(
            session_id=session_id,
            elapsed_s=elapsed_s,
            active=active,
            last_wall_s=last_wall_s,
            terminal_reason=terminal_reason,
        )

    def load(self, session_id: str) -> MixActiveAuthoritySnapshot:
        wanted = str(session_id or "").strip()
        if not wanted:
            raise MixActiveAuthorityError("Mix active-time session id is required")
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                raw = json.load(handle)
        except FileNotFoundError as exc:
            raise MixActiveAuthorityError("Mix active-time authority record is missing") from exc
        except (OSError, json.JSONDecodeError) as exc:
            raise MixActiveAuthorityError("Mix active-time authority record is unreadable") from exc
        snapshot = self._parse_document(raw)
        if snapshot.session_id != wanted:
            raise MixActiveAuthorityError("Mix active-time authority session mismatch")
        self._snapshot = snapshot
        self._anchor_mono = None
        return snapshot

    def begin(self, session_id: str, *, active: bool = False) -> MixActiveAuthoritySnapshot:
        session = str(session_id or "").strip()
        if not session:
            raise MixActiveAuthorityError("Mix active-time session id is required")
        now_wall = float(self._wall_time())
        self._snapshot = MixActiveAuthoritySnapshot(
            session_id=session,
            elapsed_s=0.0,
            active=bool(active),
            last_wall_s=now_wall if active else None,
        )
        self._anchor_mono = float(self._monotonic()) if active else None
        self._persist()
        return self._snapshot

    def _require(self, session_id: str) -> MixActiveAuthoritySnapshot:
        session = str(session_id or "").strip()
        if self._snapshot is None:
            return self.load(session)
        if self._snapshot.session_id != session:
            raise MixActiveAuthorityError("Mix active-time authority session mismatch")
        return self._snapshot

    def observe(self, session_id: str, *, active: bool) -> MixActiveAuthoritySnapshot:
        snapshot = self._require(session_id)
        now_mono = float(self._monotonic())
        now_wall = float(self._wall_time())
        elapsed = float(snapshot.elapsed_s)

        if snapshot.active:
            if self._anchor_mono is not None:
                delta = now_mono - self._anchor_mono
                if not math.isfinite(delta) or delta < 0:
                    raise MixActiveAuthorityError("monotonic Mix clock moved backwards")
            else:
                if snapshot.last_wall_s is None:
                    raise MixActiveAuthorityError("active Mix record has no durable wall anchor")
                delta = now_wall - float(snapshot.last_wall_s)
                if not math.isfinite(delta) or delta < 0:
                    raise MixActiveAuthorityError("durable Mix wall clock moved backwards")
            elapsed += delta

        self._snapshot = MixActiveAuthoritySnapshot(
            session_id=snapshot.session_id,
            elapsed_s=elapsed,
            active=bool(active),
            last_wall_s=now_wall if active else None,
            terminal_reason=snapshot.terminal_reason,
        )
        self._anchor_mono = now_mono if active else None
        self._persist()
        return self._snapshot

    def set_inactive(self, session_id: str) -> MixActiveAuthoritySnapshot:
        snapshot = self._require(session_id)
        if not snapshot.active:
            self._anchor_mono = None
            return snapshot
        return self.observe(session_id, active=False)

    def mark_terminal(self, session_id: str, reason: str) -> MixActiveAuthoritySnapshot:
        snapshot = self._require(session_id)
        if snapshot.active:
            snapshot = self.observe(session_id, active=False)
        self._snapshot = MixActiveAuthoritySnapshot(
            session_id=snapshot.session_id,
            elapsed_s=snapshot.elapsed_s,
            active=False,
            last_wall_s=None,
            terminal_reason=str(reason or "MIX_TERMINAL"),
        )
        self._anchor_mono = None
        self._persist()
        return self._snapshot


class MixActiveAuthorityMixin:
    """Controller mixin that replaces Mix wall-time with durable active time."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._mix_active_authority = MixActiveTimeAuthority()
        self._mix_active_restore_error: Optional[str] = None

    def _mix_authority_session_id(self) -> str:
        context = self.recovery_trace_context
        session_id = str(context.get("session_id") or "").strip()
        if not session_id:
            raise MixActiveAuthorityError("Mix session identity is unavailable")
        return session_id

    def _begin_trace_identity(self) -> None:
        super()._begin_trace_identity()
        if self.current_stage == self.STAGE_MIX:
            self._mix_active_authority.begin(self._mix_authority_session_id(), active=False)

    def _enter_mix(self, *args: Any, **kwargs: Any) -> None:
        super()._enter_mix(*args, **kwargs)
        self._mix_active_authority.begin(self._mix_authority_session_id(), active=False)

    def try_restore_session(self, voltage: float, current: float, ah: float):
        ok, message = super().try_restore_session(voltage, current, ah)
        if not ok:
            return ok, message

        source_mix = self.current_stage == self.STAGE_MIX
        pause = getattr(self, "_v2_cooling_pause", None)
        if self.current_stage == self.STAGE_COOLING and isinstance(pause, dict):
            source_mix = str(pause.get("source_stage") or "") == self.STAGE_MIX
        if not source_mix:
            return ok, message

        try:
            self._mix_active_authority.load(self._mix_authority_session_id())
        except MixActiveAuthorityError as exc:
            self._mix_active_restore_error = str(exc)
            self.current_stage = self.STAGE_DONE
            self.finish_timer_start = None
            self._clear_restored_targets()
            self._v2_target_voltage_v = None
            return False, f"MIX_ACTIVE_AUTHORITY_RESTORE_REJECTED: {exc}"
        return ok, message

    def _apply_authoritative_decision(self, *args: Any, **kwargs: Any):
        stage_before = kwargs.get("stage_before")
        if stage_before != self.STAGE_MIX:
            return super()._apply_authoritative_decision(*args, **kwargs)

        timestamp_s = float(kwargs.get("timestamp_s") or 0.0)
        session_id = self._mix_authority_session_id()
        snapshot = self._mix_active_authority._require(session_id)
        saved_stage_start = self.stage_start_time
        self.stage_start_time = timestamp_s - float(snapshot.elapsed_s)
        try:
            decision = super()._apply_authoritative_decision(*args, **kwargs)
        finally:
            if self.current_stage == stage_before:
                self.stage_start_time = saved_stage_start

        if decision is not None and str(getattr(decision, "reason", "")) == "MIX_TIMEOUT":
            self._mix_active_authority.mark_terminal(session_id, "MIX_TIMEOUT")
        return decision

    async def tick(self, *args: Any, **kwargs: Any):
        stage_before = self.current_stage
        output_raw = kwargs.get("output_is_on") if "output_is_on" in kwargs else (
            args[5] if len(args) > 5 else None
        )
        session_id: Optional[str] = None
        if stage_before == self.STAGE_MIX:
            session_id = self._mix_authority_session_id()
            # Unknown Output cannot prove an inactive HV interval. Conservatively
            # charge it as active; runtime telemetry safety independently fails closed.
            output_state = self._normalize_output_on(output_raw)
            self._mix_active_authority.observe(session_id, active=(output_state is not False))

        result = await super().tick(*args, **kwargs)

        if session_id is not None and self.current_stage != self.STAGE_MIX:
            try:
                self._mix_active_authority.set_inactive(session_id)
            except MixActiveAuthorityError:
                pass
        elif stage_before != self.STAGE_MIX and self.current_stage == self.STAGE_MIX:
            # The transition action keeps/turns Output ON. Start the live anchor now;
            # this may slightly over-count if hardware enable lands later, never extend.
            session_id = self._mix_authority_session_id()
            try:
                self._mix_active_authority.observe(session_id, active=True)
            except MixActiveAuthorityError:
                self._mix_active_authority.begin(session_id, active=True)
        return result
