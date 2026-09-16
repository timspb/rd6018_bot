"""Abstract pure-program boundary for V3 charge policies."""

from __future__ import annotations

from abc import ABC, abstractmethod
from .intent import ChargeIntent
from .measurements import Measurements
from .state import ChargeState


class ChargeProgram(ABC):
    """Evaluate data and return intent without owning integrations."""

    @abstractmethod
    def evaluate(
        self,
        state: ChargeState,
        measurements: Measurements,
    ) -> ChargeIntent:
        """Return a pure charge intent for the supplied snapshots."""
        raise NotImplementedError
