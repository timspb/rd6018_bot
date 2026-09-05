from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Optional


DESTRUCTIVE_CONFIRMATION_TTL_S = 5 * 60.0


@dataclass(frozen=True)
class ConfirmationGrant:
    token: str
    issued_at: float


class ConfirmationStore:
    """One-shot, chat/user-scoped authorization for destructive Telegram actions.

    Session identity is supplied by the caller.  This store adds the two properties
    that a long-lived inline button cannot provide by itself: bounded operator-intent
    freshness and binding to the chat in which the confirmation was issued.  Entries
    are process-local on purpose, so a bot restart always invalidates pending intent.
    """

    def __init__(self, *, ttl_s: float = DESTRUCTIVE_CONFIRMATION_TTL_S) -> None:
        ttl = float(ttl_s)
        if not 0.0 < ttl < float("inf"):
            raise ValueError("confirmation ttl_s must be finite and positive")
        self.ttl_s = ttl
        self._grants: dict[tuple[int, int], ConfirmationGrant] = {}

    @staticmethod
    def callback_identity(call: Any) -> Optional[tuple[int, int]]:
        message = getattr(call, "message", None)
        if message is None:
            return None
        user = getattr(call, "from_user", None)
        user_id = int(getattr(user, "id", 0) or 0)
        if user_id <= 0:
            return None

        chat = getattr(message, "chat", None)
        raw_chat_id = getattr(chat, "id", None)
        if raw_chat_id is None:
            # Test doubles and older compatibility adapters may not expose chat.
            # Keep such a grant scoped to this exact in-memory message object rather
            # than falling back to user-only authorization.
            chat_id = id(message)
        else:
            chat_id = int(raw_chat_id)
            if chat_id == 0:
                return None
        return chat_id, user_id

    def issue(
        self,
        *,
        chat_id: int,
        user_id: int,
        token: str,
        now: Optional[float] = None,
    ) -> None:
        issued_at = time.monotonic() if now is None else float(now)
        self._grants[(int(chat_id), int(user_id))] = ConfirmationGrant(
            token=str(token),
            issued_at=issued_at,
        )

    def issue_for_call(
        self,
        call: Any,
        token: str,
        *,
        now: Optional[float] = None,
    ) -> bool:
        identity = self.callback_identity(call)
        if identity is None:
            return False
        chat_id, user_id = identity
        self.issue(chat_id=chat_id, user_id=user_id, token=token, now=now)
        return True

    def cancel(self, *, chat_id: int, user_id: int) -> None:
        self._grants.pop((int(chat_id), int(user_id)), None)

    def cancel_for_call(self, call: Any) -> bool:
        identity = self.callback_identity(call)
        if identity is None:
            return False
        chat_id, user_id = identity
        self.cancel(chat_id=chat_id, user_id=user_id)
        return True

    def consume(
        self,
        *,
        chat_id: int,
        user_id: int,
        now: Optional[float] = None,
    ) -> Optional[str]:
        grant = self._grants.pop((int(chat_id), int(user_id)), None)
        if grant is None:
            return None
        current = time.monotonic() if now is None else float(now)
        age = current - grant.issued_at
        if age < 0.0 or age > self.ttl_s:
            return None
        return grant.token

    def consume_for_call(
        self,
        call: Any,
        *,
        now: Optional[float] = None,
    ) -> Optional[str]:
        identity = self.callback_identity(call)
        if identity is None:
            return None
        chat_id, user_id = identity
        return self.consume(chat_id=chat_id, user_id=user_id, now=now)
