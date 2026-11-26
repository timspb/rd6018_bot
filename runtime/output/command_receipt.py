"""Neutral immutable contract for terminal RD Output command evidence.

The physical transport creates this receipt; the safety and application layers
consume it. Keeping the value type outside runtime.physical prevents the
application boundary from depending on a concrete transport implementation.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class OutputCommandReceipt:
    """Immutable terminal identity returned by the canonical OutputOwner."""

    request_id: str
    requested_target: bool
    terminal_status: str
    observed_r18: int
    terminal_completed_monotonic: float
    connection_generation: int
    raw_terminal_identity: str
