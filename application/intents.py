"""Operator intents. They are requests, never physical commands."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import inspect
from typing import Awaitable, Callable, Mapping

from runtime.ui.commands.models import CommandResult, CommandStatus, DomainIntent


class OperatorIntentKind(str, Enum):
    START_CHARGE = "start_charge"
    STOP_CHARGE = "stop_charge"
    PAUSE_CHARGE = "pause_charge"
    RESUME_CHARGE = "resume_charge"
    SELECT_CHARGE_PROFILE = "select_charge_profile"
    SHOW_GRAPH = "show_graph"
    SHOW_LOG = "show_log"
    SHOW_JOURNAL = "show_journal"  # compatibility name for older callers
    SHOW_DIAGNOSTICS = "show_diagnostics"
    REFRESH_PANEL = "refresh_panel"
    REFRESH = "refresh"  # compatibility name for older callers
    ACKNOWLEDGE = "acknowledge"


@dataclass(frozen=True)
class OperatorIntent:
    kind: OperatorIntentKind
    source: str
    user: str
    parameters: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.source.strip() or not self.user.strip():
            raise ValueError("source and user are required")


IntentRoute = Callable[[OperatorIntent], CommandResult | Awaitable[CommandResult]]


class IntentDispatcher:
    """Route only non-actuating operator intents.

    The dispatcher is deliberately not a controller facade.  A missing route
    produces an accepted routing result so the preserved callback can continue
    its existing presentation path; no runtime or actuator method is called.
    Explicit routes may be injected by a later application adapter.
    """

    READ_ONLY_KINDS = frozenset(
        {
            OperatorIntentKind.SHOW_LOG,
            OperatorIntentKind.SHOW_GRAPH,
            OperatorIntentKind.SHOW_DIAGNOSTICS,
            OperatorIntentKind.REFRESH_PANEL,
        }
    )

    def __init__(
        self,
        routes: Mapping[OperatorIntentKind, IntentRoute] | None = None,
        stop_handler: IntentRoute | None = None,
    ) -> None:
        self._routes = dict(routes or {})
        if stop_handler is not None:
            self._routes[OperatorIntentKind.STOP_CHARGE] = stop_handler

    async def dispatch(self, intent: OperatorIntent) -> CommandResult:
        if not isinstance(intent, OperatorIntent):
            return CommandResult(CommandStatus.REJECTED, "invalid_operator_intent")
        kind = intent.kind
        if kind is OperatorIntentKind.SHOW_JOURNAL:
            kind = OperatorIntentKind.SHOW_LOG
        elif kind is OperatorIntentKind.REFRESH:
            kind = OperatorIntentKind.REFRESH_PANEL
        routed_execution_kinds = {
            OperatorIntentKind.STOP_CHARGE,
            OperatorIntentKind.PAUSE_CHARGE,
            OperatorIntentKind.RESUME_CHARGE,
        }
        routed_selection_kinds = {OperatorIntentKind.SELECT_CHARGE_PROFILE}
        if kind not in self.READ_ONLY_KINDS and kind not in routed_execution_kinds and kind not in routed_selection_kinds:
            return CommandResult(CommandStatus.REJECTED, "execution_intent_not_migrated")
        if (kind in routed_execution_kinds or kind in routed_selection_kinds) and kind not in self._routes:
            return CommandResult(CommandStatus.REJECTED, f"{kind.value}_route_not_wired")
        normalized = OperatorIntent(kind, intent.source, intent.user, intent.parameters)
        route = self._routes.get(kind)
        if route is None:
            return CommandResult(
                CommandStatus.ACCEPTED,
                "routed_to_preserved_callback",
                DomainIntent(kind=kind.value, payload=dict(normalized.parameters)),
            )
        result = route(normalized)
        if inspect.isawaitable(result):
            result = await result
        return result
