"""Persistence for the operator pause timestamp.

This module owns only the small pause sidecar document. It does not decide
whether a pause may be resumed or perform any actuator operation.
"""

from __future__ import annotations

import json
import logging
import math
import os
import tempfile
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class OperatorPauseState:
    """The persisted wall-clock start time of an operator pause, if any."""

    started_at: float | None = None

    def active(self) -> bool:
        return self.started_at is not None

    def to_document(self) -> dict[str, float]:
        if self.started_at is None:
            return {}
        return {"started_at": self.started_at}

    def save(self, path: str | os.PathLike[str]) -> bool:
        """Atomically persist this state, fsyncing the temporary file first."""
        if not self.active():
            return self.clear(path)

        target = os.fspath(path)
        parent = os.path.dirname(os.path.abspath(target))
        temporary_path: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=parent,
                prefix=f".{os.path.basename(target)}.", suffix=".tmp",
                delete=False,
            ) as stream:
                temporary_path = stream.name
                json.dump(self.to_document(), stream, allow_nan=False)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary_path, target)
            temporary_path = None
        except OSError:
            raise
        finally:
            if temporary_path is not None:
                try:
                    os.unlink(temporary_path)
                except OSError:
                    pass
        return True

    def clear(self, path: str | os.PathLike[str] | None = None) -> bool:
        """Clear memory and optionally remove the one supplied sidecar."""
        if path is not None:
            try:
                os.remove(path)
            except FileNotFoundError:
                pass
        self.started_at = None
        return True

    @classmethod
    def load(cls, path: str | os.PathLike[str]) -> "OperatorPauseState":
        """Read a compatible sidecar; malformed data safely yields unpaused."""
        try:
            with open(path, "r", encoding="utf-8") as stream:
                raw: Any = json.load(stream)
        except FileNotFoundError:
            return cls()
        except (OSError, UnicodeError, json.JSONDecodeError) as ex:
            logger.warning("Ignoring invalid operator pause state: %s", ex)
            return cls()

        value = raw.get("started_at") if isinstance(raw, dict) else None
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            logger.warning("Ignoring invalid operator pause state")
            return cls()
        timestamp = float(value)
        if not math.isfinite(timestamp) or timestamp <= 0:
            logger.warning("Ignoring invalid operator pause state")
            return cls()
        return cls(started_at=timestamp)
