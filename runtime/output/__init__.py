"""Output execution contracts; no physical adapter is included."""

from .adapter import MockOutputAdapter, OutputAdapter
from .decision import OutputDecision
from .exceptions import InvalidOutputIntent
from .intent import OutputAction, SafeOutputIntent

__all__ = [
    "MockOutputAdapter", "OutputAdapter", "OutputDecision", "InvalidOutputIntent",
    "OutputAction", "SafeOutputIntent",
]
