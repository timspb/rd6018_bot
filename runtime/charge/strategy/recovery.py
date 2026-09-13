"""Recovery budget and return-to-Main boundary."""

from __future__ import annotations

from dataclasses import dataclass

from ..intent import ChargeIntent


@dataclass
class RecoveryRuntimeState:
    attempts: int = 0


@dataclass(frozen=True)
class RecoveryPolicyConfig:
    attempt_budget: int
    recovery_voltage: float
    recovery_current: float
    recovery_stage: str = "recovery"
    main_stage: str = "main"
    mix_stage: str = "mix"
    exhausted_stage: str = "main"
    exhausted_action: str = "mix"

    def __post_init__(self) -> None:
        if self.attempt_budget < 0 or self.recovery_voltage <= 0 or self.recovery_current <= 0:
            raise ValueError("recovery recipe is invalid")
        if self.exhausted_action not in {"mix", "remain_main"}:
            raise ValueError("recovery exhausted_action must be mix or remain_main")


class RecoveryPolicy:
    def __init__(self, config: RecoveryPolicyConfig, state: RecoveryRuntimeState | None = None) -> None:
        self.config = config
        self.state = state or RecoveryRuntimeState()

    def on_plateau(self, main_voltage: float, main_current: float) -> ChargeIntent:
        if self.state.attempts < self.config.attempt_budget:
            self.state.attempts += 1
            return ChargeIntent(self.config.recovery_voltage, self.config.recovery_current, self.config.recovery_stage, False, "MAIN_PLATEAU_RECOVERY")
        if self.config.exhausted_action == "remain_main":
            return ChargeIntent(main_voltage, main_current, self.config.exhausted_stage, False, "RECOVERY_EXHAUSTED_MAIN")
        return ChargeIntent(main_voltage, main_current, self.config.mix_stage, False, "RECOVERY_EXHAUSTED_MIX")

    def return_to_main(self, main_voltage: float, main_current: float) -> ChargeIntent:
        return ChargeIntent(main_voltage, main_current, self.config.main_stage, False, "RECOVERY_RETURN_MAIN")
