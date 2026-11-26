"""Request-scoped observation of an already-issued Native Output command.

This module does not dispatch commands or retain receipts beyond the current
async context. The transaction owner decides whether an observed candidate is
accepted and may expose it only after its existing checks complete.
"""
from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Optional

from .command_receipt import OutputCommandReceipt


@dataclass
class _Observation:
    receipt: Optional[OutputCommandReceipt] = None


_CURRENT: ContextVar[Optional[_Observation]] = ContextVar(
    "rd6018_output_command_receipt_observation", default=None
)


def begin_observation() -> tuple[_Observation, Token]:
    """Install a fresh candidate slot and return its reset token."""
    observation = _Observation()
    return observation, _CURRENT.set(observation)


def reset_observation(token: Token) -> None:
    _CURRENT.reset(token)


def observe_applied_on(receipt: object) -> None:
    """Capture only the exact typed APPLIED receipt from the active request."""
    current = _CURRENT.get()
    if (current is not None and isinstance(receipt, OutputCommandReceipt)
            and receipt.requested_target is True
            and receipt.terminal_status == "APPLIED"
            and type(receipt.observed_r18) is int and receipt.observed_r18 == 1):
        current.receipt = receipt
