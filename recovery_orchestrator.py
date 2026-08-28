from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from battery_registry import BatteryRecord, get_battery
from legacy_recipe_adapter import LegacyRecipeAuthorization, authorize_legacy_target
from pb_domain import ChargeContext, ChargeIntent
from recipe_output import RecipeEnableResult, enable_authorized_recipe_target
from recovery_runtime import RecoveryRuntime


@dataclass(frozen=True)
class RecoveryStartResult:
    started: bool
    reason: str
    authorization: Optional[LegacyRecipeAuthorization] = None
    enable_result: Optional[RecipeEnableResult] = None


class RecoveryOrchestrator:
    """Coordinate a physical battery, recipe envelope, safe output and evidence runtime.

    This is the application boundary for the V2 path. Telegram handlers should not
    independently select chemistry limits, program RD6018 and start telemetry tracking.
    """

    def __init__(self, output_adapter, *, runtime: Optional[RecoveryRuntime] = None) -> None:
        self.output_adapter = output_adapter
        self.runtime = runtime or RecoveryRuntime()
        self._authorization: Optional[LegacyRecipeAuthorization] = None

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
        if self.runtime.active:
            return RecoveryStartResult(False, "recovery session already active")

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
            return RecoveryStartResult(
                False,
                authorization.reason,
                authorization=authorization,
            )

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

        try:
            await self.runtime.start(
                battery_id=battery_id,
                started_at=float(started_at),
                intent=intent,
                condition_before=record.lifecycle.condition,
            )
        except Exception:
            # Output was enabled but evidence ownership could not be established.
            # Fail closed: never leave an untracked recovery output active.
            await self.output_adapter.turn_off()
            raise

        self._authorization = authorization
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
            await self.output_adapter.turn_off()
        self.runtime.abort()
        self._authorization = None
