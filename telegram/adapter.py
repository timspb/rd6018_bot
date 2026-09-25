"""Transport-neutral panel adapter; Telegram client is injected."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from application.intents import OperatorIntent
from application.operator_interface import OperatorInterface
from presentation.panel_renderer import render_panel
from .panel_store import PanelHandle, PanelStore


class PanelTransport(Protocol):
    async def edit(self, chat_id: int, message_id: int, text: str, actions: tuple[Any, ...]) -> Any: ...
    async def send(self, chat_id: int, text: str, actions: tuple[Any, ...]) -> Any: ...


class OperatorPanelAdapter:
    def __init__(self, interface: OperatorInterface, transport: PanelTransport) -> None:
        self.interface = interface
        self.transport = transport
        self._store = PanelStore()

    def handle(self, chat_id: int) -> PanelHandle | None:
        return self._store.get(chat_id)

    async def refresh(self, chat_id: int) -> PanelHandle:
        rendered = render_panel(await self.interface.get_operator_snapshot())
        actions = rendered.layout.actions
        handle = self._store.get(chat_id)
        if handle is not None and handle.kind == "text":
            await self.transport.edit(chat_id, handle.message_id, rendered.text, actions)
            return handle
        sent = await self.transport.send(chat_id, rendered.text, actions)
        message_id = int(getattr(sent, "message_id", sent))
        handle = PanelHandle(chat_id, message_id)
        self._store.put(handle)
        return handle
