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
    source_transport: object | None = None
    source_client: object | None = None


_CURRENT: ContextVar[Optional[_Observation]] = ContextVar(
    "rd6018_output_command_receipt_observation", default=None
)


def begin_observation() -> tuple[_Observation, Token]:
    """Install a fresh candidate slot and return its reset token."""
    observation = _Observation()
    return observation, _CURRENT.set(observation)


def reset_observation(token: Token) -> None:
    _CURRENT.reset(token)


def observe_applied_on(receipt: object, *, source_transport: object = None, source_client: object = None) -> None:
    """Capture only the exact typed APPLIED receipt from the active request."""
    current = _CURRENT.get()
    if (current is not None and isinstance(receipt, OutputCommandReceipt)
            and receipt.requested_target is True
            and receipt.terminal_status == "APPLIED"
            and type(receipt.observed_r18) is int and receipt.observed_r18 == 1):
        current.receipt = receipt
        current.source_transport = source_transport
        current.source_client = source_client


def observe_applied_off(receipt: object, *, source_transport: object = None, source_client: object = None) -> None:
    """Capture only the exact typed APPLIED OFF receipt in the active request."""
    current = _CURRENT.get()
    if (current is not None and isinstance(receipt, OutputCommandReceipt)
            and receipt.requested_target is False
            and receipt.terminal_status == "APPLIED"
            and type(receipt.observed_r18) is int and receipt.observed_r18 == 0):
        current.receipt = receipt
        current.source_transport = source_transport
        current.source_client = source_client


def same_observation_origin(receipt: OutputCommandReceipt, *, source_transport: object,
                            source_client: object) -> bool:
    """Require actual transport and client object identity from the one ON command.

    Per-client connection_generation alone cannot link a receipt to its producer
    and observer session. The scope is reset by its ExecutionPort request in
    ``finally``.
    """
    current = _CURRENT.get()
    return bool(
        current is not None
        and current.receipt is receipt
        and current.source_transport is source_transport
        and source_client is not None
        and current.source_client is source_client
    )
