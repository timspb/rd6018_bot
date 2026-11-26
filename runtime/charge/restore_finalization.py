"""Finalization choreography for an accepted restored charge session."""

from __future__ import annotations

from typing import Any, Callable

from runtime.charge.session import RestoredSessionDocument
from runtime.charge.session_atomic import WriteStatus


def finalize_restored_session(
    host: Any,
    document: dict[str, Any],
    *,
    normalize_done_document: bool,
    normalize_terminal: Callable[..., bool],
    session_file: str,
    restored_terminal: bool,
    voltage: float,
    current: float,
    ah: float,
    canonical_preimage: bytes,
) -> None:
    """Run the legacy post-header restore steps in their original order.

    Exceptions and partial mutations intentionally propagate unchanged.
    """
    host._session_restore_enriched = False
    if normalize_done_document:
        normalize_terminal(host, document, session_file=session_file)
    host._session_restore_snapshot = RestoredSessionDocument.capture(document)
    result = host._save_session(
        voltage, current, ah, restore_expected_bytes=canonical_preimage,
    )
    status = result[0] if isinstance(result, tuple) and result else None
    if status is not WriteStatus.COMMITTED:
        status_label = getattr(status, "value", status)
        raise RuntimeError(f"restore canonical commit failed: {status_label!r}")
    host._session_restore_enriched = True
    host._stage_tracking_enabled = True
