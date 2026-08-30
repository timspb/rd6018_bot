from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from battery_registry import BatteryRecord, get_battery
from legacy_recipe_adapter import LegacyRecipeAuthorization, authorize_legacy_target
from pb_domain import ChargeContext, ChargeIntent
from recipe_output import RecipeEnableResult, enable_authorized_recipe_target
from recovery_runtime import RecoveryRuntime


class RecoveryOutputOffUnconfirmed(RuntimeError):
    """Recovery software state may not retire while physical Output OFF is unproved."""


@dataclass(frozen=True)
class RecoveryStartResult:
    started: bool
    reason: str
    authorization: Optional[LegacyRecipeAuthorization] = None
    enable_result: Optional[RecipeEnableResult] = None


class RecoveryOrchestrator:
    """Coordinate battery context, recipe authorization, safe output and V2 evidence.

    Once a protected enable succeeds, the orchestrator retains containment authority
    until either the runtime is active or physical Output OFF has been positively
    confirmed. A failed/raised OFF command may therefore never be converted into an
    inactive software state that would permit another start on an uncertain live output.
    """

    def __init__(self, output_adapter, *, runtime: Optional[RecoveryRuntime] = None) -> None:
        self.output_adapter = output_adapter
        self.runtime = runtime or RecoveryRuntime()
        self._authorization: Optional[LegacyRecipeAuthorization] = None

    @property
    def containment_active(self) -> bool:
        """True while this object still owns a possibly energized recovery output."""
        return self._authorization is not None

    async def _load_context(self, battery_id: str, intent: ChargeIntent) -> tuple[BatteryRecord, ChargeContext]:
        record = await get_battery(battery_id)
        if record is None:
            raise KeyError(f"unknown battery_id: {battery_id}")
        context = ChargeContext(
            identity=record.identity,
            intent=intent,
            condition=record.lifecycle.condition,
        )
        return record, context

    async def _confirm_output_off(self, *, context: str) -> None:
        """Return only after the adapter positively confirms Output OFF."""
        try:
            confirmed = bool(await self.output_adapter.turn_off())
        except Exception as exc:
            raise RecoveryOutputOffUnconfirmed(
                f"{context}: output OFF raised {type(exc).__name__}: {exc}"
            ) from exc
        if not confirmed:
            raise RecoveryOutputOffUnconfirmed(
                f"{context}: output OFF was not confirmed"
            )

    async def start_target(
        self,
        *,
        battery_id: str,
        intent: ChargeIntent,
        stage: str,
        target_voltage_v: float,
        target_current_a: float,
        started_at: float,
        expert_high_voltage: bool = False,
        custom_voltage_ceiling_v: Optional[float] = None,
        readback_delay_s: float = 0.0,
    ) -> RecoveryStartResult:
        if self.runtime.active or self.containment_active:
            return RecoveryStartResult(False, "recovery session/containment already active")

        try:
            record, context = await self._load_context(battery_id, intent)
        except KeyError as exc:
            return RecoveryStartResult(False, str(exc))

        authorization = authorize_legacy_target(
            context,
            stage=stage,
            target_voltage_v=target_voltage_v,
            target_current_a=target_current_a,
            expert_high_voltage=expert_high_voltage,
            custom_voltage_ceiling_v=custom_voltage_ceiling_v,
        )
        if not authorization.allowed:
            return RecoveryStartResult(False, authorization.reason, authorization=authorization)

        enable_result = await enable_authorized_recipe_target(
            self.output_adapter,
            authorization,
            readback_delay_s=readback_delay_s,
        )
        if not enable_result.enabled:
            return RecoveryStartResult(
                False,
                enable_result.reason,
                authorization=authorization,
                enable_result=enable_result,
            )

        # Safe enable has succeeded: from this point forward software must retain an
        # owner until either RecoveryRuntime starts or Output OFF is positively proved.
        self._authorization = authorization
        try:
            await self.runtime.start(
                battery_id=battery_id,
                started_at=float(started_at),
                intent=intent,
                condition_before=record.lifecycle.condition,
            )
        except Exception as exc:
            try:
                await self._confirm_output_off(context="recovery runtime start failed")
            except RecoveryOutputOffUnconfirmed as off_exc:
                # Deliberately retain _authorization so a subsequent start is blocked.
                raise off_exc from exc
            self._authorization = None
            raise

        return RecoveryStartResult(
            True,
            f"started {authorization.envelope.recipe_id}",
            authorization=authorization,
            enable_result=enable_result,
        )

    def observe(
        self,
        *,
        timestamp_s: float,
        stage: str,
        voltage_v: float,
        current_a: float,
        temp_c: float,
        is_cv: bool,
        is_cc: Optional[bool] = None,
        target_voltage_v: Optional[float] = None,
        ah: Optional[float] = None,
        output_is_on: Optional[bool] = True,
    ):
        return self.runtime.observe(
            timestamp_s=timestamp_s,
            stage=stage,
            voltage_v=voltage_v,
            current_a=current_a,
            temp_c=temp_c,
            is_cv=is_cv,
            is_cc=is_cc,
            target_voltage_v=target_voltage_v,
            ah=ah,
            output_is_on=output_is_on,
        )

    async def complete(self, **kwargs):
        evidence = await self.runtime.complete(**kwargs)
        self._authorization = None
        return evidence

    async def abort(self, *, turn_output_off: bool = True) -> None:
        if turn_output_off:
            # Do not retire runtime/authorization until physical OFF is confirmed.
            await self._confirm_output_off(context="recovery abort")
        self.runtime.abort()
        self._authorization = None
