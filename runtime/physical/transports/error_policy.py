"""Classify transport outages without reclassifying safety verification faults.

Pure exception policy consumed by the existing RD6018 runtime and physical
transport clients. This module does not execute commands or authorize Output.
A future BW600 adapter must establish its own validated device evidence;
do not infer a second device's physical OFF from these exception predicates.
"""
from __future__ import annotations

import aiohttp


def _is_physical_transport_error(exc: BaseException) -> bool:
    """Identify an edge-link failure without classifying safety faults as network loss."""
    # A bare TimeoutError is ambiguous: it can be a local safety verification
    # timeout rather than an ESPHome transport failure. Only transport-specific
    # exception classes are classified here.
    if isinstance(exc, (ConnectionError, aiohttp.ClientError)):
        return True
    text = str(exc).lower()
    return any(
        marker in text
        for marker in (
            "not connected to rd6018-controller",
            "connection refused",
            "connection reset",
            "connection closed",
            "cannot connect",
            "clientconnector",
            "connection timeout",
            "request timeout",
            "transport outage",
        )
    )


def _is_recoverable_link_boundary_error(exc: BaseException) -> bool:
    """Preserve an active session when an accepted edge command loses readback."""
    text = str(exc).lower()
    return _is_physical_transport_error(exc) or (
        "off command accepted" in text
        and "switch state was not confirmed" in text
    )
