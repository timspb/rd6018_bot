"""Pure D090/D106 proof DTO and shared validation error type.

This module intentionally has no transaction, platform, transport, or hardware
dependencies so read-only proof consumers remain importable on Windows.
"""
from __future__ import annotations

import math
import time
from typing import NamedTuple


class TransactionError(RuntimeError):
    """A fail-closed D090 transaction or D106 proof validation error."""


class TrialOffProof(NamedTuple):
    """Independent physical authority proof; it never performs a device action."""
    captured_at_epoch: float
    autonomous: bool
    lease_armed: bool
    lease_remaining_s: float
    lease_ttl_s: int
    protection_code: int
    modbus_age_s: float
    set_voltage_v: float
    set_current_a: float
    challenge: str

    def validate(self) -> None:
        numbers = (self.captured_at_epoch, self.lease_remaining_s,
                   self.modbus_age_s, self.set_voltage_v, self.set_current_a)
        if any(type(x) not in (int, float) or not math.isfinite(x) for x in numbers):
            raise TransactionError("trial proof has invalid numeric readings")
        if (type(self.autonomous) is not bool or type(self.lease_armed) is not bool
                or type(self.lease_ttl_s) is not int
                or type(self.protection_code) is not int
                or type(self.challenge) is not str or len(self.challenge) < 16):
            raise TransactionError("trial proof has invalid edge types/challenge")
        if not (0 <= time.time() - self.captured_at_epoch <= 30):
            raise TransactionError("trial edge proof stale or in the future")
        if (self.autonomous or self.lease_armed or self.lease_remaining_s != 0
                or self.lease_ttl_s != 900 or self.protection_code != 0
                or not 0 <= self.modbus_age_s <= 20
                or not 0 <= self.set_voltage_v <= 15.5
                or self.set_current_a < 0):
            raise TransactionError("trial edge state is not safe OFF/unmanaged")
