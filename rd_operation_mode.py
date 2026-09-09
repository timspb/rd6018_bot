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
    """Pure domain state separating ownership from application operation.

    This module gives runtime and edge work one explicit source of truth instead of
    inferring hardware policy from Pb session state or Wi-Fi availability.
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


def operating_state_from_control_mode(mode: Any) -> RdOperatingState:
    """Map the existing durable control-mode contract onto the new domain model.

    The production state file currently persists ``pb_managed`` / ``hands_off``.
    Until persistence is migrated, this adapter only interprets the managed value.
    ``HANDS_OFF`` is an ownership-transfer state, not proof of autonomous operation;
    autonomous operation must come from the explicit edge authority below.

    - PB_MANAGED -> BOT + MANAGED

    Unknown/corrupt values and HANDS_OFF are rejected rather than being interpreted
    as autonomous.
    The caller may therefore retain the existing fail-closed PB_MANAGED recovery path.
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
    """Interpret only the explicit edge autonomous authority bit.

    A false or unavailable bit is deliberately fail-closed as managed.  The caller
    must not derive this value from HANDS_OFF, connectivity, or Pb session state.
    """

    if isinstance(autonomous, str):
        value = autonomous.strip().lower()
        if value in {"on", "true", "1"}:
            autonomous = True
        elif value in {"off", "false", "0", ""}:
            autonomous = False
        else:
            raise ValueError("unsupported edge autonomous authority value")
    if autonomous is True:
        return RdOperatingState.external_autonomous()
    if autonomous is False or autonomous is None:
        return RdOperatingState.bot_managed()
    raise ValueError("unsupported edge autonomous authority value")
