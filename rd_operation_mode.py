from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class RdOwnership(str, Enum):
    """Who owns application-level RD6018 actuator authority."""

    BOT = "bot"
    EXTERNAL = "external"


class RdOperationMode(str, Enum):
    """How the RD6018 is expected to operate.

    AUTONOMOUS is a generic PSU mode. It is deliberately not a battery or Pb mode.
    """

    MANAGED = "managed"
    AUTONOMOUS = "autonomous"


@dataclass(frozen=True)
class RdOperatingState:
    """Pure domain state separating ownership from application operation.

    This module intentionally does not change runtime/ESPHome behavior. It gives
    later safety and edge work one explicit source of truth instead of inferring
    hardware policy from PB session state or Wi-Fi availability.
    """

    ownership: RdOwnership
    operation: RdOperationMode

    @classmethod
    def bot_managed(cls) -> "RdOperatingState":
        return cls(RdOwnership.BOT, RdOperationMode.MANAGED)

    @classmethod
    def external_autonomous(cls) -> "RdOperatingState":
        return cls(RdOwnership.EXTERNAL, RdOperationMode.AUTONOMOUS)

    @property
    def bot_actuation_allowed(self) -> bool:
        return (
            self.ownership is RdOwnership.BOT
            and self.operation is RdOperationMode.MANAGED
        )

    @property
    def pb_application_allowed(self) -> bool:
        return self.bot_actuation_allowed

    @property
    def control_plane_required(self) -> bool:
        return self.operation is RdOperationMode.MANAGED

    @property
    def managed_edge_lease_required(self) -> bool:
        return self.bot_actuation_allowed

    @property
    def external_temperature_required_by_mode(self) -> bool:
        """Only the current bot-managed Pb application requires temp_ext.

        Autonomous mode is load-agnostic: the connected device may be a battery,
        motor, electronics, heater, lamp, bench load, or anything else. Absence of
        temp_ext therefore cannot itself be an autonomous safety fault.
        """

        return self.pb_application_allowed

    @property
    def local_hardware_safety_required(self) -> bool:
        """Intrinsic PSU safety is never disabled by ownership/mode selection."""

        return True

    def validate_supported(self) -> None:
        """Reject combinations whose runtime contract has not been implemented yet."""

        supported = {
            (RdOwnership.BOT, RdOperationMode.MANAGED),
            (RdOwnership.EXTERNAL, RdOperationMode.AUTONOMOUS),
        }
        if (self.ownership, self.operation) not in supported:
            raise ValueError(
                "unsupported RD operating state: "
                f"ownership={self.ownership.value}, operation={self.operation.value}"
            )
