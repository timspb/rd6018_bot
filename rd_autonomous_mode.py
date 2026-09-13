from __future__ import annotations

import asyncio
from typing import Any, Optional

from aiogram import F
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from edge_autonomous_mode import EdgeAutonomousAuthority
from operator_confirmation import ConfirmationStore
from rd6018_telemetry import telemetry_freshness
from runtime_safety import RuntimeSafetyError, _binary


class RdAutonomousModeCoordinator:
    """Cross-layer BOT/HANDS_OFF <-> AUTONOMOUS operation transition.

    HANDS_OFF remains the software ownership boundary. AUTONOMOUS is an additional,
    explicit edge operation authority that permits the RD6018 to remain a generic PSU
    without HA/Wi-Fi/Telegram/managed-lease availability. Entry and exit are OFF-only.
    """

    def __init__(self, app: Any, manager: Any) -> None:
        self.app = app
        self.manager = manager
        self.guard = manager.guard
        lease = getattr(self.guard, "edge_safety_lease", None)
        if not bool(getattr(self.guard, "edge_lease_enforced", False)) or lease is None:
            self.edge: Optional[EdgeAutonomousAuthority] = None
        else:
            self.edge = EdgeAutonomousAuthority(lease)
        self._transition_lock = asyncio.Lock()

    def _require_edge(self) -> EdgeAutonomousAuthority:
        if self.edge is None:
            raise RuntimeSafetyError(
                "AUTONOMOUS unavailable: configured edge firmware authority is required"
            )
        return self.edge

    def _managed_session_active(self) -> bool:
        return bool(self.manager._managed_session_active())

    async def _require_output_off(self) -> dict[str, Any]:
        live = await self.guard._raw_live()
        self.manager._observe_edge_mode(live)
        try:
            fresh = bool(telemetry_freshness(live, ("switch",)).valid)
        except Exception:
            fresh = False
        state = _binary(live.get("switch"))
        if not fresh or state is not False:
            raise RuntimeSafetyError(
                "AUTONOMOUS transition requires fresh confirmed Output OFF; current RD state was not changed"
            )
        return live

    async def enter(self) -> bool:
        """Move managed-idle/HANDS_OFF into explicit persistent edge AUTONOMOUS."""
        async with self._transition_lock:
            if bool(getattr(self.guard, "_off_unconfirmed", False)):
                raise RuntimeSafetyError(
                    "AUTONOMOUS blocked: previous Output OFF remains unconfirmed"
                )
            if self._managed_session_active():
                raise RuntimeSafetyError(
                    "AUTONOMOUS blocked: stop/release the active managed session first"
                )
            await self._require_output_off()
            edge = self._require_edge()

            try:
                already_autonomous = await edge.read_autonomous()
            except Exception as exc:
                raise RuntimeSafetyError(
                    f"AUTONOMOUS blocked: edge authority read failed: {exc}"
                ) from exc

            if already_autonomous:
                self.manager._edge_autonomous = True
                if not self.manager.hands_off:
                    self.manager._write_mode(type(self.manager.mode).HANDS_OFF)
                    self.manager.mode = type(self.manager.mode).HANDS_OFF
                    self.manager._clear_stale_auto_restore_authority()
                return True

            # First cross the existing software ownership boundary. This verifies OFF,
            # positively disarms the managed dead-man and blocks all bot actuators. If
            # the later autonomous edge command is ambiguous, HANDS_OFF is retained;
            # software never rolls itself back to managed authority.
            if not self.manager.hands_off:
                await self.manager.enter_hands_off()

            try:
                await edge.enter()
            except Exception as exc:
                self.manager._edge_autonomous = False
                raise RuntimeSafetyError(
                    "RD remains HANDS_OFF, but AUTONOMOUS edge transition was not "
                    f"positively acknowledged: {exc}"
                ) from exc

            self.manager._edge_autonomous = True
            self.guard._orphan_output_seen_at = None
            return True

    async def exit(self) -> bool:
        """Return explicit AUTONOMOUS to managed-idle; Output must remain confirmed OFF."""
        async with self._transition_lock:
            if self._managed_session_active():
                raise RuntimeSafetyError(
                    "AUTONOMOUS exit blocked: stale managed software authority is active"
                )
            await self._require_output_off()
            edge = self._require_edge()
            try:
                autonomous = await edge.read_autonomous()
            except Exception as exc:
                raise RuntimeSafetyError(
                    f"AUTONOMOUS exit blocked: edge authority read failed: {exc}"
                ) from exc

            if autonomous:
                try:
                    await edge.exit()
                except Exception as exc:
                    self.manager._edge_autonomous = True
                    raise RuntimeSafetyError(
                        f"AUTONOMOUS exit was not positively acknowledged: {exc}"
                    ) from exc

            self.manager._edge_autonomous = False
            if not self.manager.hands_off:
                raise RuntimeSafetyError(
                    "AUTONOMOUS exit requires software HANDS_OFF ownership boundary"
                )
            await self.manager.return_pb_control()
            return True


def _filter_callback(markup: InlineKeyboardMarkup, callback: str) -> InlineKeyboardMarkup:
    return _filter_callbacks(markup, {callback})


def _filter_callbacks(
    markup: InlineKeyboardMarkup,
    blocked: set[str],
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for row in markup.inline_keyboard:
        kept = [
            button
            for button in row
            if str(getattr(button, "callback_data", "") or "") not in blocked
        ]
        if kept:
            rows.append(kept)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _append_unique(
    markup: InlineKeyboardMarkup,
    button: InlineKeyboardButton,
) -> InlineKeyboardMarkup:
    callback = str(button.callback_data or "")
    for row in markup.inline_keyboard:
        for existing in row:
            if callback and str(getattr(existing, "callback_data", "") or "") == callback:
                return markup
    return InlineKeyboardMarkup(
        inline_keyboard=[list(row) for row in markup.inline_keyboard] + [[button]]
    )


def install_rd_autonomous_mode(
    app: Any,
    manager: Any,
    *,
    install_ui: bool = True,
) -> RdAutonomousModeCoordinator:
    existing = getattr(app, "rd_autonomous_mode", None)
    if isinstance(existing, RdAutonomousModeCoordinator):
        return existing

    coordinator = RdAutonomousModeCoordinator(app, manager)
    app.rd_autonomous_mode = coordinator

    # Historical/stale HANDS_OFF buttons call manager.return_pb_control() directly.
    # Once explicit edge AUTONOMOUS is observed, that generic ownership callback must
    # never bypass the edge EXIT_AUTONOMOUS positive-ACK transaction.
    original_return_pb_control = manager.return_pb_control

    async def guarded_return_pb_control() -> bool:
        if manager.edge_autonomous:
            raise RuntimeSafetyError(
                "PB control restore blocked: edge AUTONOMOUS is active; use explicit AUTONOMOUS exit"
            )
        return bool(await original_return_pb_control())

    manager.return_pb_control = guarded_return_pb_control

    # The same stale-capability rule applies to the explicit HANDS_OFF Output-OFF
    # control. It intentionally bypasses the public HassClient wrappers so an operator
    # can contain a HANDS_OFF PSU, but that narrow capability must disappear once the
    # edge owns explicit AUTONOMOUS authority. Production RdControlModeManager exposes
    # this method; the callable check keeps reduced characterization harnesses compatible.
    original_operator_output_off = getattr(manager, "operator_output_off", None)
    if callable(original_operator_output_off):
        async def guarded_operator_output_off(entity_id: Optional[str] = None) -> bool:
            if manager.edge_autonomous:
                raise RuntimeSafetyError(
                    "RD AUTONOMOUS: bot Output OFF is disabled; use the physical RD6018 controls"
                )
            return bool(await original_operator_output_off(entity_id))

        manager.operator_output_off = guarded_operator_output_off

    if not install_ui:
        return coordinator

    confirmations = ConfirmationStore()

    @app.router.callback_query(F.data == "rd_autonomous_confirm")
    async def _confirm(call: Any) -> None:
        if not await app._check_chat_and_respond(call):
            return
        if not confirmations.issue_for_call(call, "enter-autonomous"):
            await call.answer("Не удалось привязать подтверждение", show_alert=True)
            return
        await call.answer()
        await call.message.answer(
            "⚠️ <b>Перевести RD6018 в АВТОНОМНЫЙ БП?</b>\n\n"
            "Требуется подтверждённый Output OFF. После перехода бот не управляет "
            "Output/V/I/OVP/OCP, Pb-сессии и внешний датчик температуры не являются "
            "authority. Потеря Wi-Fi/HA/Telegram не выключает БП сама по себе. "
            "Локальная intrinsic-защита ESP/RD остаётся активной.",
            parse_mode=app.ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(
                        text="🔌 ВКЛЮЧИТЬ АВТОНОМНЫЙ БП",
                        callback_data="rd_autonomous_execute",
                    )],
                    [InlineKeyboardButton(
                        text="Отмена",
                        callback_data="rd_autonomous_cancel",
                    )],
                ]
            ),
        )

    @app.router.callback_query(F.data == "rd_autonomous_cancel")
    async def _cancel(call: Any) -> None:
        confirmations.cancel_for_call(call)
        await call.answer("Отменено")

    @app.router.callback_query(F.data == "rd_autonomous_execute")
    async def _execute(call: Any) -> None:
        if not await app._check_chat_and_respond(call):
            return
        token = confirmations.consume_for_call(call)
        if token != "enter-autonomous":
            await call.answer("Подтверждение истекло", show_alert=True)
            return
        try:
            await coordinator.enter()
        except Exception as exc:
            await call.answer(str(exc), show_alert=True)
            return
        await call.answer("Автономный режим подтверждён edge")
        await call.message.answer(
            "🔌 <b>RD6018: АВТОНОМНЫЙ БП</b>\n"
            "Bot/Pb authority снята; режим сохранён на ESP и не зависит от домашнего Wi-Fi.",
            parse_mode=app.ParseMode.HTML,
        )

    @app.router.callback_query(F.data == "rd_autonomous_exit")
    async def _exit(call: Any) -> None:
        if not await app._check_chat_and_respond(call):
            return
        try:
            await coordinator.exit()
        except Exception as exc:
            await call.answer(str(exc), show_alert=True)
            return
        await call.answer("Управление боту возвращено")
        await call.message.answer(
            "🤖 <b>RD6018 снова под управлением бота.</b>\n"
            "Output остаётся подтверждённо OFF; старая Pb-сессия не возобновляется.",
            parse_mode=app.ParseMode.HTML,
        )

    return coordinator


def install_rd_autonomous_final_hmi(app: Any, coordinator: RdAutonomousModeCoordinator) -> None:
    """Compose the global Bot/Autonomous switch after Output-truth normalization.

    This is also the last stale-capability barrier. A Telegram keyboard rendered before
    AUTONOMOUS was selected must not leave Pb adoption/Mix controls as live capabilities,
    and the HANDS_OFF Mix observer must not acquire future-OFF authority in AUTONOMOUS.
    """
    if bool(getattr(app, "_rd_autonomous_final_hmi_installed", False)):
        return

    import operator_hmi as hmi
    from operator_output_truth import output_known

    observer = getattr(app, "rd_live_mix_observer", None)
    if observer is not None and not bool(getattr(observer, "_autonomous_start_guarded", False)):
        original_observer_start = observer.start

        async def guarded_observer_start(*args: Any, **kwargs: Any) -> Any:
            if coordinator.manager.edge_autonomous:
                raise RuntimeSafetyError(
                    "HANDS_OFF Mix observer is disabled while edge AUTONOMOUS is active"
                )
            return await original_observer_start(*args, **kwargs)

        observer.start = guarded_observer_start
        observer._autonomous_start_guarded = True

    original = hmi.build_operator_keyboard

    def build_keyboard(app_arg: Any, state: Any) -> InlineKeyboardMarkup:
        markup = original(app_arg, state)
        manager = coordinator.manager

        if manager.edge_autonomous:
            # AUTONOMOUS is a generic PSU state. Remove every Pb/adoption/ownership
            # affordance that can be inherited from the underlying HANDS_OFF HMI. The
            # only ownership transition exposed here is the explicit OFF-only edge exit.
            markup = _filter_callbacks(
                markup,
                {
                    "rd_hands_off_disable",
                    "rd_hands_off_output_off",
                    "rd_managed_adopt",
                    "rd_managed_mix",
                    "rd_live_mix",
                    "rd_ownership_adopt",
                    "rd_ownership_hands_off",
                    "rd_hands_off_release_confirm",
                    "charge_modes",
                    "power_toggle",
                    "menu_off",
                },
            )
            if output_known(state) and not bool(getattr(state, "output_on", False)):
                return _append_unique(
                    markup,
                    InlineKeyboardButton(
                        text="🤖 Вернуть управление боту",
                        callback_data="rd_autonomous_exit",
                    ),
                )
            return markup

        if (
            manager.pb_managed
            and getattr(state, "process_state", None) is hmi.HmiProcessState.IDLE
            and output_known(state)
            and not bool(getattr(state, "output_on", False))
        ):
            return _append_unique(
                markup,
                InlineKeyboardButton(
                    text="🔌 Автономный БП",
                    callback_data="rd_autonomous_confirm",
                ),
            )
        return markup

    hmi.build_operator_keyboard = build_keyboard
    app._rd_autonomous_final_hmi_installed = True
