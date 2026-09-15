"""Pure logical charge session lifecycle."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class SessionStatus(str, Enum):
    IDLE = "idle"
    ACTIVE = "active"
    PAUSED = "paused"
    STOPPED = "stopped"


@dataclass(frozen=True)
class SessionSnapshot:
    session_id: str | None
    status: SessionStatus
    profile: str | None = None


class SessionManager:
    """Own only logical lifecycle; no persistence or actuator authority."""

    def __init__(self) -> None:
        self._snapshot = SessionSnapshot(None, SessionStatus.IDLE)

    @property
    def snapshot(self) -> SessionSnapshot:
        return self._snapshot

    def start(self, session_id: str, profile: str) -> SessionSnapshot:
        if self._snapshot.status in {SessionStatus.ACTIVE, SessionStatus.PAUSED}:
            raise ValueError("charge session already active")
        if not session_id or not profile:
            raise ValueError("session_id and profile are required")
        self._snapshot = SessionSnapshot(session_id, SessionStatus.ACTIVE, profile)
        return self._snapshot

    def pause(self) -> SessionSnapshot:
        if self._snapshot.status is not SessionStatus.ACTIVE:
            raise ValueError("only an active session can be paused")
        self._snapshot = SessionSnapshot(self._snapshot.session_id, SessionStatus.PAUSED, self._snapshot.profile)
        return self._snapshot

    def resume(self) -> SessionSnapshot:
        if self._snapshot.status is not SessionStatus.PAUSED:
            raise ValueError("only a paused session can be resumed")
        self._snapshot = SessionSnapshot(self._snapshot.session_id, SessionStatus.ACTIVE, self._snapshot.profile)
        return self._snapshot

    def stop(self) -> SessionSnapshot:
        self._snapshot = SessionSnapshot(self._snapshot.session_id, SessionStatus.STOPPED, self._snapshot.profile)
        return self._snapshot
