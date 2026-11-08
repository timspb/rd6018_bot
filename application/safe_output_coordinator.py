"""Canonical verified-output enable transaction, invoked by established ExecutionPort."""
from __future__ import annotations

import asyncio
import logging
from time import perf_counter
from typing import FrozenSet, Optional

from runtime.safety.output_policy import (
    EnableResult, OutputAdapter, OutputRequest, SafetyDecision, SafetySupervisor,
    SafetyViolation, TelemetrySnapshot, snapshot_from_live,
)

logger = logging.getLogger("rd6018")
PROGRAMMED_READBACK_TIMEOUT_S = 10.0


class SafeOutputCoordinator:
    """Fail-closed output enable sequence with setpoint readback."""

    def __init__(
        self,
        adapter: OutputAdapter,
        supervisor: Optional[SafetySupervisor] = None,
        *,
        readback_delay_s: float = 0.0,
        readback_timeout_s: float = PROGRAMMED_READBACK_TIMEOUT_S,
        readback_poll_interval_s: float = 0.25,
    ) -> None:
        self.adapter = adapter
        self.supervisor = supervisor or SafetySupervisor()
        self.readback_delay_s = max(0.0, readback_delay_s)
        self.readback_timeout_s = max(0.0, readback_timeout_s)
        self.readback_poll_interval_s = max(0.01, readback_poll_interval_s)

    async def _force_off(self) -> bool:
        try:
            return bool(await self.adapter.turn_off())
        except Exception:
            return False

    async def _failure(
        self,
        violations: FrozenSet[SafetyViolation],
        detail: str,
        *,
        force_off: bool,
    ) -> EnableResult:
        merged = set(violations)
        if force_off and not await self._force_off():
            merged.add(SafetyViolation.OUTPUT_OFF_UNCONFIRMED)
            detail = f"{detail}; output OFF was not confirmed"
        logger.warning(
            "Safe output enable failed: %s [%s]",
            detail,
            ",".join(sorted(v.value for v in merged)),
        )
        return EnableResult(False, frozenset(merged), detail)

    async def _wait_for_programmed_readback(
        self,
        request: OutputRequest,
    ) -> tuple[Optional[TelemetrySnapshot], SafetyDecision]:
        if self.readback_delay_s:
            await asyncio.sleep(self.readback_delay_s)

        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.readback_timeout_s
        last_mismatch = SafetyDecision(
            False,
            frozenset({SafetyViolation.READBACK_MISMATCH}),
            "programmed values were not observed",
        )
        last_exception: Optional[Exception] = None

        while True:
            programmed: Optional[TelemetrySnapshot] = None
            try:
                programmed_live = await self.adapter.get_all_live()
                programmed = snapshot_from_live(
                    programmed_live,
                    require_programming_freshness=True,
                )
                last_exception = None
            except Exception as exc:
                last_exception = exc

            if programmed is not None:
                second_preflight = self.supervisor.preflight(request, programmed)
                if not second_preflight.allowed:
                    return programmed, second_preflight

                verified = self.supervisor.verify_programmed(request, programmed)
                if verified.allowed:
                    return programmed, verified
                last_mismatch = verified

            now = loop.time()
            if now >= deadline:
                if programmed is None:
                    detail = "programmed readback telemetry missing/invalid"
                    if last_exception is not None:
                        detail += f": {type(last_exception).__name__}: {last_exception}"
                    return None, SafetyDecision(
                        False,
                        frozenset({SafetyViolation.TELEMETRY_INVALID}),
                        detail,
                    )
                return programmed, last_mismatch

            await asyncio.sleep(min(self.readback_poll_interval_s, max(0.0, deadline - now)))

    async def confirm_programmed_readback(
        self,
        request: OutputRequest,
    ) -> tuple[Optional[TelemetrySnapshot], SafetyDecision]:
        """Wait for canonical programmed V2 evidence before any Output ON."""
        return await self._wait_for_programmed_readback(request)

    async def enable(self, request: OutputRequest) -> EnableResult:
        try:
            live = await self.adapter.get_all_live()
        except Exception as exc:
            return EnableResult(
                False,
                frozenset({SafetyViolation.TELEMETRY_INVALID}),
                f"pre-enable telemetry failed: {type(exc).__name__}: {exc}",
            )
        before = snapshot_from_live(live, require_programming_freshness=False)
        if before is None:
            return EnableResult(
                False,
                frozenset({SafetyViolation.TELEMETRY_INVALID}),
                "required live telemetry is missing or invalid",
            )

        decision = self.supervisor.preflight(request, before)
        if not decision.allowed:
            return EnableResult(False, decision.violations, decision.detail)

        operations = []
        if request.ovp_v is not None:
            operations.append(("ovp", self.adapter.set_ovp, request.ovp_v))
        if request.ocp_a is not None:
            operations.append(("ocp", self.adapter.set_ocp, request.ocp_a))
        operations.extend((
            ("voltage", self.adapter.set_voltage, request.voltage_v),
            ("current", self.adapter.set_current, request.current_a),
        ))
        for name, setter, value in operations:
            stage_started = perf_counter()
            try:
                ok = await setter(value)
            except Exception as exc:
                return await self._failure(
                    frozenset({SafetyViolation.PROGRAMMING_FAILED}),
                    f"failed to program {name}={value:.3f}: {type(exc).__name__}: {exc}",
                    force_off=True,
                )
            logger.info("START_TIMING set_%s_ms=%.1f", name, (perf_counter() - stage_started) * 1000)
            if not ok:
                return await self._failure(
                    frozenset({SafetyViolation.PROGRAMMING_FAILED}),
                    f"failed to program {name}={value:.3f}",
                    force_off=True,
                )

        stage_started = perf_counter()
        _programmed, readback = await self.confirm_programmed_readback(request)
        logger.info("START_TIMING programmed_readback_ms=%.1f", (perf_counter() - stage_started) * 1000)
        if not readback.allowed:
            return await self._failure(readback.violations, readback.detail, force_off=True)

        stage_started = perf_counter()
        try:
            enabled = await self.adapter.turn_on()
        except Exception as exc:
            return await self._failure(
                frozenset({SafetyViolation.OUTPUT_ENABLE_FAILED}),
                f"output enable raised {type(exc).__name__}: {exc}",
                force_off=True,
            )
        logger.info("START_TIMING output_on_ms=%.1f", (perf_counter() - stage_started) * 1000)
        if not enabled:
            return await self._failure(
                frozenset({SafetyViolation.OUTPUT_ENABLE_FAILED}),
                "output enable command returned false",
                force_off=True,
            )

        if self.readback_delay_s:
            await asyncio.sleep(self.readback_delay_s)
        stage_started = perf_counter()
        try:
            final_live = await self.adapter.get_all_live()
        except Exception as exc:
            return await self._failure(
                frozenset(
                    {
                        SafetyViolation.TELEMETRY_INVALID,
                        SafetyViolation.POST_ENABLE_VERIFY_FAILED,
                    }
                ),
                f"post-enable telemetry failed: {type(exc).__name__}: {exc}",
                force_off=True,
            )
        logger.info("START_TIMING final_readback_ms=%.1f", (perf_counter() - stage_started) * 1000)
        final = snapshot_from_live(
            final_live,
            require_programming_freshness=True,
        )
        if final is None:
            return await self._failure(
                frozenset({SafetyViolation.POST_ENABLE_VERIFY_FAILED}),
                "post-enable required telemetry is missing/invalid",
                force_off=True,
            )

        final_decision = self.supervisor.verify_live_output(request, final)
        if not final_decision.allowed:
            return await self._failure(
                final_decision.violations | frozenset({SafetyViolation.POST_ENABLE_VERIFY_FAILED}),
                final_decision.detail or "post-enable state is not safe/confirmed",
                force_off=True,
            )

        return EnableResult(True)
