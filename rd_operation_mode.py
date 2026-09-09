from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


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
    """Pure domain state separating ownership from application operation."""

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
        """Only the current bot-managed Pb application requires temp_ext."""
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


def operating_state_from_control_mode(mode: Any) -> RdOperatingState:
    """Map only explicit legacy managed authority onto the operation model.

    `HANDS_OFF` is ownership transfer, not proof of autonomous operation. Unknown,
    corrupt, or HANDS_OFF values are rejected rather than granting another authority.
    """
    raw = getattr(mode, "value", mode)
    value = str(raw or "").strip().lower()
    if value == "pb_managed":
        return RdOperatingState.bot_managed()
    if value == "hands_off":
        raise ValueError(
            "HANDS_OFF is ownership transfer; explicit edge autonomous authority required"
        )
    raise ValueError(f"unsupported legacy RD control mode: {value or '<empty>'}")


def operating_state_from_edge_authority(autonomous: Any) -> RdOperatingState:
    """Interpret only an explicit edge autonomous authority bit.

    Explicit true -> EXTERNAL/AUTONOMOUS.
    Explicit false -> BOT/MANAGED candidate.

    Missing, empty, `unknown`, `unavailable`, malformed or otherwise non-explicit
    evidence raises instead of granting bot actuation. Runtime may then retain its
    provisional passive/fail-closed boundary until a real edge report arrives.
    """
    if isinstance(autonomous, str):
        value = autonomous.strip().lower()
        if value in {"on", "true", "1"}:
            autonomous = True
        elif value in {"off", "false", "0"}:
            autonomous = False
        else:
            raise ValueError("unsupported edge autonomous authority value")
    if autonomous is True:
        return RdOperatingState.external_autonomous()
    if autonomous is False:
        return RdOperatingState.bot_managed()
    raise ValueError("unsupported edge autonomous authority value")
