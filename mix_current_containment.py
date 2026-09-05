from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from charge_logic import SESSION_FILE


class MixContainmentError(RuntimeError):
    pass


@dataclass(frozen=True)
class MixContainmentPolicy:
    """A calibrated result supplied by future physical characterization.

    No production headroom is provided by default.  The mechanism therefore has no
    actuator authority until a battery/path-specific calibration explicitly supplies
    ``containment_headroom_a`` greater than the finish/reversal evidence margin.
    """

    containment_headroom_a: Optional[float] = None

    def calibrated_headroom_a(self) -> Optional[float]:
        value = self.containment_headroom_a
        if value is None:
            return None
        if isinstance(value, bool):
            raise MixContainmentError("containment headroom is invalid")
        parsed = float(value)
        if not math.isfinite(parsed) or parsed <= 0:
            raise MixContainmentError("containment headroom is invalid")
        return parsed

    @property
    def calibrated(self) -> bool:
        return self.calibrated_headroom_a() is not None


@dataclass(frozen=True)
class MixContainmentState:
    session_id: str
    ceiling_a: float
    initial_programmed_ceiling_a: float
    signal_censored: bool = False


@dataclass(frozen=True)
class MixContainmentDecision:
    state: MixContainmentState
    changed: bool
    actuator_authority: bool
    reason: str


class MixCurrentContainment:
    """Durable monotonic current-authority ratchet for Mix.

    This class intentionally computes and persists containment authority only. It does
    not write RD6018 setpoints or OCP. Protected-write integration remains disabled
    until real RD/HA characterization establishes headroom, measurement floor and safe
    OCP sequencing.
    """

    VERSION = 1

    def __init__(
        self,
        policy: Optional[MixContainmentPolicy] = None,
        path: Optional[str | os.PathLike[str]] = None,
    ) -> None:
        self.policy = policy or MixContainmentPolicy()
        self.path = Path(path or f"{SESSION_FILE}.mix-current-containment.json")
        self._state: Optional[MixContainmentState] = None

    @staticmethod
    def _positive_current(value: Any, *, field: str) -> float:
        if isinstance(value, bool):
            raise MixContainmentError(f"{field} is invalid")
        try:
            parsed = float(value)
        except (TypeError, ValueError) as exc:
            raise MixContainmentError(f"{field} is invalid") from exc
        if not math.isfinite(parsed) or parsed <= 0:
            raise MixContainmentError(f"{field} is invalid")
        return parsed

    @property
    def state(self) -> Optional[MixContainmentState]:
        return self._state

    def _persist(self) -> None:
        state = self._state
        if state is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(f".{self.path.name}.tmp")
        document = {
            "version": self.VERSION,
            "session_id": state.session_id,
            "ceiling_a": state.ceiling_a,
            "initial_programmed_ceiling_a": state.initial_programmed_ceiling_a,
            "signal_censored": state.signal_censored,
        }
        try:
            with open(tmp, "w", encoding="utf-8") as handle:
                json.dump(document, handle, ensure_ascii=False, sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, self.path)
        finally:
            try:
                if tmp.exists():
                    tmp.unlink()
            except OSError:
                pass

    def begin(self, session_id: str, *, programmed_ceiling_a: float) -> MixContainmentState:
        session = str(session_id or "").strip()
        if not session:
            raise MixContainmentError("Mix containment session id is required")
        ceiling = self._positive_current(programmed_ceiling_a, field="programmed_ceiling_a")
        self._state = MixContainmentState(
            session_id=session,
            ceiling_a=ceiling,
            initial_programmed_ceiling_a=ceiling,
        )
        self._persist()
        return self._state

    def load(self, session_id: str) -> MixContainmentState:
        wanted = str(session_id or "").strip()
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                raw = json.load(handle)
        except FileNotFoundError as exc:
            raise MixContainmentError("Mix containment state is missing") from exc
        except (OSError, json.JSONDecodeError) as exc:
            raise MixContainmentError("Mix containment state is unreadable") from exc
        if not isinstance(raw, dict) or raw.get("version") != self.VERSION:
            raise MixContainmentError("Mix containment state is invalid")
        session = str(raw.get("session_id") or "").strip()
        if not wanted or session != wanted:
            raise MixContainmentError("Mix containment session mismatch")
        ceiling = self._positive_current(raw.get("ceiling_a"), field="ceiling_a")
        initial = self._positive_current(
            raw.get("initial_programmed_ceiling_a"), field="initial_programmed_ceiling_a"
        )
        if ceiling > initial + 1e-9:
            raise MixContainmentError("persisted Mix current authority was enlarged")
        censored = raw.get("signal_censored", False)
        if not isinstance(censored, bool):
            raise MixContainmentError("signal_censored is invalid")
        self._state = MixContainmentState(session, ceiling, initial, censored)
        return self._state

    def _require(self, session_id: str) -> MixContainmentState:
        session = str(session_id or "").strip()
        if self._state is None:
            return self.load(session)
        if self._state.session_id != session:
            raise MixContainmentError("Mix containment session mismatch")
        return self._state

    def tighten(
        self,
        session_id: str,
        *,
        programmed_ceiling_a: float,
        confirmed_imin_a: float,
    ) -> MixContainmentDecision:
        state = self._require(session_id)
        programmed = self._positive_current(programmed_ceiling_a, field="programmed_ceiling_a")
        imin = self._positive_current(confirmed_imin_a, field="confirmed_imin_a")

        # A later call can never enlarge authority even if another layer accidentally
        # presents a larger programmed current than the one that began this session.
        hard_programmed = min(programmed, state.initial_programmed_ceiling_a, state.ceiling_a)
        headroom = self.policy.calibrated_headroom_a()
        if headroom is None:
            return MixContainmentDecision(
                state=state,
                changed=False,
                actuator_authority=False,
                reason="calibration_required",
            )

        candidate = min(hard_programmed, state.ceiling_a, imin + headroom)
        candidate = self._positive_current(candidate, field="adaptive_ceiling_a")
        changed = candidate < state.ceiling_a - 1e-9
        if changed:
            self._state = MixContainmentState(
                session_id=state.session_id,
                ceiling_a=candidate,
                initial_programmed_ceiling_a=state.initial_programmed_ceiling_a,
                signal_censored=state.signal_censored,
            )
            self._persist()
            state = self._state
        return MixContainmentDecision(
            state=state,
            changed=changed,
            actuator_authority=True,
            reason="tightened" if changed else "already_at_or_below_calibrated_ceiling",
        )

    def mark_current_ceiling_reached(self, session_id: str) -> MixContainmentState:
        """Record caller-proven censoring without inventing a current tolerance."""
        state = self._require(session_id)
        if state.signal_censored:
            return state
        self._state = MixContainmentState(
            session_id=state.session_id,
            ceiling_a=state.ceiling_a,
            initial_programmed_ceiling_a=state.initial_programmed_ceiling_a,
            signal_censored=True,
        )
        self._persist()
        return self._state
