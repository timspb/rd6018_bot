"""File adapter for the legacy Manual V2 session document."""

from __future__ import annotations

import json
import logging
import os
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any


_LOGGER = logging.getLogger(__name__)


def read_manual_session_document(path: str | Path) -> dict | None:
    """Read an unvalidated Manual session JSON mapping, or return ``None``."""
    try:
        with open(path, "r", encoding="utf-8") as handle:
            document = json.load(handle)
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        _LOGGER.warning("Unable to read Manual session document %s: %s", path, exc)
        return None

    if not isinstance(document, Mapping):
        _LOGGER.warning("Manual session document %s has a non-mapping JSON root", path)
        return None
    return dict(document)


def _best_effort_fsync_directory(directory: Path) -> None:
    """Persist a rename where directory descriptors and fsync are supported."""
    if not hasattr(os, "O_DIRECTORY"):
        return
    descriptor = None
    try:
        descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
        os.fsync(descriptor)
    except (OSError, AttributeError, NotImplementedError):
        pass
    finally:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass


def write_manual_session_document(
    path: str | Path, document: Mapping[str, Any]
) -> None:
    """Atomically write the supplied mapping using the legacy JSON format."""
    if not isinstance(document, Mapping):
        raise TypeError("Manual session document must be a mapping")

    target = Path(path)
    payload = json.dumps(dict(document), ensure_ascii=False, indent=2)
    descriptor = None
    temporary_path = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
        )
        temporary_path = Path(temporary_name)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            descriptor = None  # fdopen now owns and closes it.
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, target)
        _best_effort_fsync_directory(target.parent)
    finally:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass
        if temporary_path is not None:
            try:
                temporary_path.unlink()
            except OSError:
                pass

