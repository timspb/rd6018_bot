"""Dependency container shape for the future V3 composition root."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class RuntimeDependencies:
    """Explicit dependency slots; all integrations remain unconfigured in 3A.

    The slots document the future wiring boundary without constructing or
    importing any production dependency.  They are intentionally passive.
    """

    hass_client: Optional[Any] = None
    storage: Optional[Any] = None
    controller: Optional[Any] = None
    safety: Optional[Any] = None
    ownership: Optional[Any] = None
    telegram: Optional[Any] = None
    output: Optional[Any] = None
