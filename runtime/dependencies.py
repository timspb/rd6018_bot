"""Infrastructure dependency container for the future V3 composition root."""

from __future__ import annotations

from dataclasses import dataclass
import logging
import time
from typing import Any, Callable, Optional


@dataclass
class RuntimeDependencies:
    """Explicit passive infrastructure references owned by ``RuntimeApp``.

    Phase 3B supplies references only.  It does not import or construct current
    production integrations, and it deliberately has no controller, UI,
    Telegram, output, lease, or ESP-control slot.
    """

    config: Optional[Any] = None
    storage: Optional[Any] = None
    persistence: Optional[Any] = None
    hass: Optional[Any] = None
    logger: logging.Logger = logging.getLogger("rd6018.runtime")
    clock: Callable[[], float] = time.time
    program_registry: Optional[Any] = None
