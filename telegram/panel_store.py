"""Authoritative panel handle storage, independent of Telegram implementation."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PanelHandle:
    chat_id: int
    message_id: int
    kind: str = "text"


class PanelStore:
    def __init__(self) -> None:
        self._handles: dict[int, PanelHandle] = {}

    def get(self, chat_id: int) -> PanelHandle | None:
        return self._handles.get(chat_id)

    def put(self, handle: PanelHandle) -> None:
        self._handles[handle.chat_id] = handle

    def remove(self, chat_id: int) -> None:
        self._handles.pop(chat_id, None)
