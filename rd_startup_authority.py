from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Optional


class RdStartupAuthorityGate:
    """Keep managed actuator authority closed until edge mode is reconciled.

    D065 makes the ESP edge bit authoritative for AUTONOMOUS operation. A transiently
    unavailable Home Assistant/edge snapshot at process startup therefore cannot be
    treated as either managed or autonomous permission. Existing rd_control_mode
    wrappers already block every normal bot actuator while ``edge_autonomous`` is true;
    this gate deliberately uses that conservative state as a provisional lock until a
    fresh explicit edge mode is observed and any stale managed startup authority has
    been contained.

    The lock is not a claim that the edge is autonomous. ``candidate_autonomous`` keeps
    the observed edge truth separate from the provisional software block.
    """

    def __init__(self, manager: Any) -> None:
        self.manager = manager
        self.guard = manager.guard
        self.candidate_autonomous: Optional[bool] = None
        self.managed_recovery_complete = False
        self.reconciliation_complete = False
        self.reconciliation_error = ""
        self._original_observe = manager._observe_edge_mode
        self._original_return_pb = manager.return_pb_control
        self._install_observation_gate()
        self._install_clean_return_gate()

    @staticmethod
    def parse_explicit(raw: Any) -> Optional[bool]:
        if not isinstance(raw, dict):
            return None
        value = raw.get("autonomous_mode")
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if value == 1:
                return True
            if value == 0:
                return False
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"on", "true", "1"}:
                return True
            if normalized in {"off", "false", "0"}:
                return False
        return None

    def _install_observation_gate(self) -> None:
        gate = self

        def observe(live: Any) -> None:
            candidate = gate.parse_explicit(live)
            if candidate is None:
                # Unknown is not a mode transition. Keep the current conservative lock.
                return
            gate.candidate_autonomous = candidate
            if candidate:
                gate._original_observe(live)
                gate.managed_recovery_complete = False
                gate.reconciliation_complete = True
                gate.reconciliation_error = ""
                return
            if gate.managed_recovery_complete:
                gate._original_observe(live)
                return
            # A fresh managed edge observation is necessary but not sufficient after a
            # process restart: D061/D062/diagnostic durable state may still require OFF
            # containment. Keep every normal bot actuator behind the existing
            # edge_autonomous software block until reconcile_managed() completes.
            gate.manager._edge_autonomous = True

        self.manager._observe_edge_mode = observe

    def _install_clean_return_gate(self) -> None:
        gate = self

        async def return_pb_control() -> bool:
            was_hands_off = bool(getattr(gate.manager, "hands_off", False))
            result = bool(await gate._original_return_pb())
            # The underlying HANDS_OFF -> PB transaction requires fresh confirmed OFF,
            # clears stale AUTO restore authority, and never resumes an old session.
            # That explicit clean boundary is sufficient to reopen ordinary managed
            # starts even if the process originally booted while AUTONOMOUS/unreachable.
            if result and was_hands_off and bool(getattr(gate.manager, "pb_managed", False)):
                gate.mark_managed_recovered()
            return result

        self.manager.return_pb_control = return_pb_control

    def hold_unresolved(self, reason: str = "edge authority unresolved") -> None:
        self.candidate_autonomous = None
        self.managed_recovery_complete = False
        self.reconciliation_complete = False
        self.reconciliation_error = str(reason)
        self.manager._edge_autonomous = True

    def mark_autonomous(self) -> None:
        self.candidate_autonomous = True
        self.managed_recovery_complete = False
        self.reconciliation_complete = True
        self.reconciliation_error = ""
        self.manager._edge_autonomous = True

    def mark_managed_recovered(self) -> None:
        self.candidate_autonomous = False
        self.managed_recovery_complete = True
        self.reconciliation_complete = True
        self.reconciliation_error = ""
        self.manager._edge_autonomous = False

    async def reconcile_managed(
        self,
        recover: Callable[[], Awaitable[bool]],
        *,
        retry_s: float = 5.0,
    ) -> str:
        """Resolve edge authority and contain stale managed startup state once.

        Read failures/unknown entity values are retried read-only while bot authority is
        blocked. Once a managed edge is positively observed, the supplied recovery
        transaction runs. A failed recovery is *not* blindly retried because it may
        already have crossed an Output-OFF uncertainty boundary; authority stays blocked
        and an operator/restart can resolve the incident without creating an OFF storm.
        """

        delay = max(1.0, float(retry_s))
        self.hold_unresolved()
        while True:
            try:
                raw = await self.guard._raw_live()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.hold_unresolved(f"edge authority read failed: {type(exc).__name__}: {exc}")
                await asyncio.sleep(delay)
                continue

            candidate = self.parse_explicit(raw)
            if candidate is None:
                self.hold_unresolved("edge autonomous authority missing/unavailable")
                await asyncio.sleep(delay)
                continue
            if candidate:
                self._original_observe(raw)
                self.mark_autonomous()
                return "autonomous"

            # Preserve the provisional actuator lock while stale managed durable state
            # is reconciled. Do not call the gated observer here: its purpose is exactly
            # to keep this lock closed until recovery returns positive evidence.
            self.candidate_autonomous = False
            self.manager._edge_autonomous = True
            try:
                recovered = bool(await recover())
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.reconciliation_error = (
                    f"managed startup recovery failed: {type(exc).__name__}: {exc}"
                )
                self.reconciliation_complete = False
                return "blocked"
            if not recovered:
                self.reconciliation_error = "managed startup recovery did not prove containment"
                self.reconciliation_complete = False
                return "blocked"

            self.mark_managed_recovered()
            return "managed"


def install_rd_startup_authority_gate(manager: Any) -> RdStartupAuthorityGate:
    existing = getattr(manager, "_rd_startup_authority_gate", None)
    if isinstance(existing, RdStartupAuthorityGate):
        return existing
    gate = RdStartupAuthorityGate(manager)
    manager._rd_startup_authority_gate = gate
    return gate
