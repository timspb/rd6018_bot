from __future__ import annotations

import asyncio
import json
import math
import os
import tempfile
import time
import uuid
from dataclasses import dataclass, replace
from enum import Enum
from typing import Any, Optional

from aiogram import F
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from edge_live_adoption import EdgeLiveAdoption
from manual_mode import ManualChargeRequest, ManualSessionState
from operator_confirmation import ConfirmationStore
from pb_domain import BatteryChemistry
from rd6018_telemetry import ProtectionStatus, finite_float, resolve_protection
from runtime_safety import RuntimeSafetyError, _binary
from v2_battery_catalog import list_batteries
from v2_ui import battery_button_label


ADOPTION_POLL_S = 5.0
ADOPTION_SETPOINT_TOLERANCE = 0.06


class ManagedAdoptionState(str, Enum):
    IDLE = "idle"
    ADOPTION_PENDING = "adoption_pending"
    ACTIVE = "active"
    OFF_PENDING = "off_pending"
    INTERRUPTED = "interrupted"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True)
class ManagedAdoptionFingerprint:
    set_voltage_v: float
    set_current_a: float
    ovp_v: float
    ocp_a: float


@dataclass(frozen=True)
class ManagedAdoptionPreview:
    token: str
    battery_id: str
    chemistry: BatteryChemistry
    capacity_ah: float
    fingerprint: ManagedAdoptionFingerprint


class ManagedLiveAdoptionCoordinator:
    """D061 live HANDS_OFF -> PB_MANAGED adoption for an already-ON RD6018.

    This first managed adoption program is deliberately Manual-only. It takes no
    chemistry transition authority and performs no Output/V/I/OVP/OCP write at the
    adoption point. The observed live V/I/OVP/OCP become component-wise maximum
    authority. That authority can ratchet only downward; any out-of-band increase is a
    verified-OFF condition.

    The transaction is fail-closed around the edge handover:

      read-only HA preflight -> durable ADOPTION_PENDING -> edge live-adopt ACK ->
      fresh HA TOCTOU re-read -> prime software Manual authority -> durable PB_MANAGED.

    If the edge command may have executed but software cannot complete the transaction,
    the coordinator does not pretend the external session is untouched: it commits
    OFF_PENDING containment and requires verified Output OFF.
    """

    VERSION = 1

    def __init__(
        self,
        app: Any,
        manager: Any,
        *,
        state_file: str = "rd_managed_adoption_v2.json",
        poll_s: float = ADOPTION_POLL_S,
        edge: Optional[EdgeLiveAdoption] = None,
    ) -> None:
        self.app = app
        self.manager = manager
        self.guard = manager.guard
        self.manual = getattr(app, "manual_session_manager", None)
        if self.manual is None:
            raise RuntimeError("managed live adoption requires Manual session manager")
        lease = getattr(self.guard, "edge_safety_lease", None)
        self.edge = edge or (EdgeLiveAdoption(lease) if lease is not None else None)
        self.state_file = str(state_file)
        self.poll_s = max(1.0, float(poll_s))
        self.state = ManagedAdoptionState.IDLE
        self.session_id = ""
        self.battery_id = ""
        self.chemistry: Optional[BatteryChemistry] = None
        self.capacity_ah = 0.0
        self.max_authority: Optional[ManagedAdoptionFingerprint] = None
        self.current_authority: Optional[ManagedAdoptionFingerprint] = None
        self.started_at_s = 0.0
        self.last_status = ""
        self._task: Optional[asyncio.Task] = None
        self._restore()

    @property
    def active(self) -> bool:
        return self.state is ManagedAdoptionState.ACTIVE

    @property
    def off_pending(self) -> bool:
        return self.state is ManagedAdoptionState.OFF_PENDING

    def _document(self) -> dict[str, Any]:
        def fingerprint(value: Optional[ManagedAdoptionFingerprint]) -> Optional[dict[str, float]]:
            if value is None:
                return None
            return {
                "set_voltage_v": value.set_voltage_v,
                "set_current_a": value.set_current_a,
                "ovp_v": value.ovp_v,
                "ocp_a": value.ocp_a,
            }

        return {
            "version": self.VERSION,
            "state": self.state.value,
            "session_id": self.session_id,
            "battery_id": self.battery_id,
            "chemistry": self.chemistry.value if self.chemistry is not None else None,
            "capacity_ah": self.capacity_ah,
            "max_authority": fingerprint(self.max_authority),
            "current_authority": fingerprint(self.current_authority),
            "started_at_s": self.started_at_s,
            "last_status": self.last_status,
            "saved_at_s": time.time(),
        }

    def _persist(self) -> None:
        path = os.path.abspath(self.state_file)
        directory = os.path.dirname(path) or "."
        os.makedirs(directory, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(
            prefix=".rd-managed-adoption-",
            suffix=".tmp",
            dir=directory,
            text=True,
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(self._document(), handle, ensure_ascii=False, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_path, path)
            try:
                dir_fd = os.open(directory, os.O_RDONLY)
                try:
                    os.fsync(dir_fd)
                finally:
                    os.close(dir_fd)
            except OSError:
                pass
        finally:
            try:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
            except OSError:
                pass

    @staticmethod
    def _parse_fingerprint(raw: Any) -> Optional[ManagedAdoptionFingerprint]:
        if not isinstance(raw, dict):
            return None
        try:
            values = [
                float(raw["set_voltage_v"]),
                float(raw["set_current_a"]),
                float(raw["ovp_v"]),
                float(raw["ocp_a"]),
            ]
        except (KeyError, TypeError, ValueError):
            return None
        if not all(math.isfinite(value) for value in values):
            return None
        return ManagedAdoptionFingerprint(*values)

    def _restore(self) -> None:
        if not os.path.exists(self.state_file):
            return
        try:
            with open(self.state_file, "r", encoding="utf-8") as handle:
                raw = json.load(handle)
            if not isinstance(raw, dict) or int(raw.get("version")) != self.VERSION:
                return
            previous = ManagedAdoptionState(str(raw.get("state") or "idle"))
            self.session_id = str(raw.get("session_id") or "")
            self.battery_id = str(raw.get("battery_id") or "")
            chemistry = raw.get("chemistry")
            self.chemistry = BatteryChemistry(str(chemistry)) if chemistry else None
            self.capacity_ah = float(raw.get("capacity_ah") or 0.0)
            self.max_authority = self._parse_fingerprint(raw.get("max_authority"))
            self.current_authority = self._parse_fingerprint(raw.get("current_authority"))
            self.started_at_s = float(raw.get("started_at_s") or 0.0)
            if previous in {
                ManagedAdoptionState.ADOPTION_PENDING,
                ManagedAdoptionState.ACTIVE,
                ManagedAdoptionState.OFF_PENDING,
            }:
                self.state = ManagedAdoptionState.OFF_PENDING
                self.last_status = (
                    "process_restart: adopted live authority is not resumed; verified Output OFF pending"
                )
                self._persist()
            else:
                self.state = previous
                self.last_status = str(raw.get("last_status") or "")
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            self.state = ManagedAdoptionState.IDLE

    @staticmethod
    def fingerprint_from_live(live: dict[str, Any]) -> Optional[ManagedAdoptionFingerprint]:
        values = [
            finite_float(live.get("set_voltage")),
            finite_float(live.get("set_current")),
            finite_float(live.get("ovp")),
            finite_float(live.get("ocp")),
        ]
        if any(value is None for value in values):
            return None
        set_v, set_i, ovp, ocp = (float(value) for value in values if value is not None)
        if set_v <= 0 or set_i <= 0 or ovp <= 0 or ocp <= 0:
            return None
        return ManagedAdoptionFingerprint(set_v, set_i, ovp, ocp)

    @staticmethod
    def fingerprint_matches(
        expected: ManagedAdoptionFingerprint,
        actual: ManagedAdoptionFingerprint,
        *,
        tolerance: float = ADOPTION_SETPOINT_TOLERANCE,
    ) -> bool:
        return all(
            abs(a - b) <= float(tolerance)
            for a, b in (
                (expected.set_voltage_v, actual.set_voltage_v),
                (expected.set_current_a, actual.set_current_a),
                (expected.ovp_v, actual.ovp_v),
                (expected.ocp_a, actual.ocp_a),
            )
        )

    def _preflight_live(
        self,
        live: dict[str, Any],
        *,
        expected: Optional[ManagedAdoptionFingerprint] = None,
    ) -> ManagedAdoptionFingerprint:
        if _binary(live.get("switch")) is not True:
            raise RuntimeSafetyError("live adoption requires positively confirmed Output ON")

        critical = self.guard._critical_telemetry_error(live, require_programming=True)
        if critical is not None:
            raise RuntimeSafetyError(f"live adoption telemetry rejected: {critical}")
        freshness = self.guard._runtime_freshness_error(live, output_state=True)
        if freshness is not None:
            raise RuntimeSafetyError(f"live adoption freshness rejected: {freshness}")
        protection = resolve_protection(live)
        if protection.status is not ProtectionStatus.NORMAL:
            raise RuntimeSafetyError(
                f"live adoption requires normal RD protection state, got {protection.status.value}"
            )

        fingerprint = self.fingerprint_from_live(live)
        if fingerprint is None:
            raise RuntimeSafetyError(
                "live adoption requires positive V/I/OVP/OCP readback; disabled protections are not managed authority"
            )
        policy = self.guard.policy
        if fingerprint.set_voltage_v > policy.absolute_voltage_ceiling_v + ADOPTION_SETPOINT_TOLERANCE:
            raise RuntimeSafetyError("live adoption voltage exceeds managed absolute envelope")
        if fingerprint.set_current_a > policy.absolute_current_ceiling_a + ADOPTION_SETPOINT_TOLERANCE:
            raise RuntimeSafetyError("live adoption current exceeds managed absolute envelope")
        if fingerprint.ovp_v > policy.absolute_ovp_ceiling_v + ADOPTION_SETPOINT_TOLERANCE:
            raise RuntimeSafetyError("live adoption OVP exceeds managed absolute envelope")
        if fingerprint.ocp_a > policy.absolute_ocp_ceiling_a + ADOPTION_SETPOINT_TOLERANCE:
            raise RuntimeSafetyError("live adoption OCP exceeds managed absolute envelope")
        if fingerprint.ovp_v + ADOPTION_SETPOINT_TOLERANCE < fingerprint.set_voltage_v + policy.min_ovp_margin_v:
            raise RuntimeSafetyError("live adoption OVP does not protect the live voltage setpoint")
        if fingerprint.ocp_a + ADOPTION_SETPOINT_TOLERANCE < fingerprint.set_current_a + policy.min_ocp_margin_a:
            raise RuntimeSafetyError("live adoption OCP does not protect the live current setpoint")

        measured_v = finite_float(live.get("voltage"))
        measured_i = finite_float(live.get("current"))
        if measured_v is None or measured_i is None:
            raise RuntimeSafetyError("live adoption requires measured output voltage/current")
        if measured_v > fingerprint.ovp_v + ADOPTION_SETPOINT_TOLERANCE:
            raise RuntimeSafetyError("live measured voltage exceeds configured OVP")
        if measured_i > fingerprint.ocp_a + ADOPTION_SETPOINT_TOLERANCE:
            raise RuntimeSafetyError("live measured current exceeds configured OCP")

        if expected is not None and not self.fingerprint_matches(expected, fingerprint):
            raise RuntimeSafetyError(
                "live RD setpoints changed during adoption; authority was not transferred"
            )
        return fingerprint

    def _other_authority_active(self) -> Optional[str]:
        controller = getattr(self.app, "charge_controller", None)
        if controller is not None and bool(getattr(controller, "is_active", False)):
            return "AUTO controller is already active"
        if bool(getattr(self.manual, "is_active", False)):
            return "Manual controller is already active"
        observer = getattr(self.app, "rd_live_mix_observer", None)
        if observer is not None:
            raw = getattr(observer, "state", None)
            state = str(getattr(raw, "value", raw) or "")
            if state in {"active", "off_pending"}:
                return "HANDS_OFF Mix observer already owns safety/OFF authority"
        return None

    def _prime_manual_authority(
        self,
        preview: ManagedAdoptionPreview,
        fingerprint: ManagedAdoptionFingerprint,
    ) -> None:
        request = ManualChargeRequest(
            voltage_v=fingerprint.set_voltage_v,
            current_a=fingerprint.set_current_a,
            battery_id=preview.battery_id,
            capacity_ah=preview.capacity_ah,
            notes="D061 adopted-live Manual; no writes at adoption",
        )
        self.manual.request = request
        self.manual.state = ManualSessionState.ARMING
        self.manual.started_at = time.time()
        self.manual.paused_total_s = 0.0
        self.manual.cooling_started_at = None
        self.manual.stop_reason = "adoption_pending_edge_owned"
        reset = getattr(self.manual, "_reset_delta_tracking", None)
        if callable(reset):
            reset()
        if hasattr(self.manual, "reach_voltage_v"):
            self.manual.reach_voltage_v = None
        if hasattr(self.manual, "reach_current_a"):
            self.manual.reach_current_a = None
        if hasattr(self.manual, "_previous_voltage_v"):
            self.manual._previous_voltage_v = None
        if hasattr(self.manual, "_previous_current_a"):
            self.manual._previous_current_a = None
        self.manual._task = None
        self.manual._persist()

    def _retire_manual_software(self, reason: str, *, failed: bool) -> None:
        self.manual.stop_reason = str(reason)
        self.manual.cooling_started_at = None
        self.manual.state = ManualSessionState.FAILED if failed else ManualSessionState.STOPPED
        self.manual._task = None
        self.manual._persist()

    async def _verified_off(self, reason: str) -> bool:
        self.state = ManagedAdoptionState.OFF_PENDING
        self.last_status = f"{reason}: verified Output OFF pending"
        self._persist()
        try:
            if bool(getattr(self.manager, "hands_off", False)):
                await self.manager.operator_output_off(self.app.ENTITY_MAP.get("switch"))
            else:
                await self.app.hass.turn_off(self.app.ENTITY_MAP.get("switch"))
        except Exception as exc:
            self.last_status = f"{reason}: Output OFF unconfirmed: {type(exc).__name__}: {exc}"
            self._persist()
            return False

        lease = getattr(self.guard, "edge_safety_lease", None)
        if lease is not None:
            try:
                await lease.disarm()
            except Exception:
                pass
        self._retire_manual_software(reason, failed=True)
        self.state = ManagedAdoptionState.FAILED
        self.last_status = f"{reason}: Output verified OFF"
        self._persist()
        return True

    async def adopt(self, preview: ManagedAdoptionPreview) -> bool:
        async with self.manager._transition_lock:
            if self.active or self.off_pending:
                raise RuntimeSafetyError("managed live adoption already owns pending state")
            if not bool(getattr(self.manager, "hands_off", False)):
                raise RuntimeSafetyError("managed live adoption requires durable HANDS_OFF")
            if bool(getattr(self.guard, "_off_unconfirmed", False)):
                raise RuntimeSafetyError("managed live adoption blocked: previous Output OFF is unconfirmed")
            conflict = self._other_authority_active()
            if conflict is not None:
                raise RuntimeSafetyError(f"managed live adoption blocked: {conflict}")
            if self.edge is None:
                raise RuntimeSafetyError("managed live adoption requires the local edge lease")

            self.manager._release_in_progress = True
            edge_command_started = False
            try:
                first = await self.guard._raw_live()
                self._preflight_live(first, expected=preview.fingerprint)

                self.state = ManagedAdoptionState.ADOPTION_PENDING
                self.session_id = uuid.uuid4().hex
                self.battery_id = preview.battery_id
                self.chemistry = preview.chemistry
                self.capacity_ah = float(preview.capacity_ah)
                self.max_authority = preview.fingerprint
                self.current_authority = preview.fingerprint
                self.started_at_s = time.time()
                self.last_status = "read-only preflight passed; edge live ownership acquisition pending"
                self._persist()

                prepared = await self.edge.prepare()
                second = await self.guard._raw_live()
                self._preflight_live(second, expected=preview.fingerprint)

                edge_command_started = True
                await self.edge.adopt(expected_generation=prepared.generation)

                third = await self.guard._raw_live()
                fingerprint = self._preflight_live(third, expected=preview.fingerprint)
                self._prime_manual_authority(preview, fingerprint)

                # D061 is the only path allowed to cross HANDS_OFF -> PB_MANAGED while
                # Output is already ON. Edge ownership and a fresh TOCTOU readback are
                # both proven before the durable software authority boundary changes.
                self.manager._clear_stale_auto_restore_authority()
                self.manager._write_mode(type(self.manager.mode).PB_MANAGED)
                self.manager.mode = type(self.manager.mode).PB_MANAGED
                self.guard._orphan_output_seen_at = None

                self.manual.state = ManualSessionState.ACTIVE
                self.manual.stop_reason = ""
                self.manual._persist()
                self.current_authority = fingerprint
                self.state = ManagedAdoptionState.ACTIVE
                self.last_status = "live Output adopted as PB-managed Manual without setpoint/Output writes"
                self._persist()
                self._task = asyncio.create_task(
                    self._run(), name="rd6018-managed-live-adoption"
                )
                return True
            except Exception as exc:
                if edge_command_started:
                    await self._verified_off(
                        f"live_adoption_incomplete_after_edge_command:{type(exc).__name__}:{exc}"
                    )
                else:
                    self.state = ManagedAdoptionState.FAILED
                    self.last_status = f"live_adoption_preflight_failed:{type(exc).__name__}:{exc}"
                    self._persist()
                raise
            finally:
                self.manager._release_in_progress = False

    def _ratchet_request(self, authority: ManagedAdoptionFingerprint) -> None:
        request = getattr(self.manual, "request", None)
        if request is None:
            return
        if (
            abs(float(request.voltage_v) - authority.set_voltage_v) < 1e-9
            and abs(float(request.current_a) - authority.set_current_a) < 1e-9
        ):
            return
        self.manual.request = ManualChargeRequest(
            voltage_v=authority.set_voltage_v,
            current_a=authority.set_current_a,
            stop=request.stop,
            battery_id=request.battery_id,
            capacity_ah=request.capacity_ah,
            notes=request.notes,
        )
        self.manual._persist()

    def authorize_managed_write(self, field: str, value: float) -> None:
        if not self.active:
            return
        authority = self.current_authority
        if authority is None:
            raise RuntimeSafetyError("adopted-live authority readback is unavailable")
        requested = finite_float(value)
        if requested is None:
            raise RuntimeSafetyError("adopted-live write must be finite")
        ceiling = float(getattr(authority, field))
        if float(requested) > ceiling + ADOPTION_SETPOINT_TOLERANCE:
            raise RuntimeSafetyError(
                f"adopted-live {field} increase blocked: {float(requested):.3f} > {ceiling:.3f}"
            )

    def ratchet_after_managed_write(self, field: str, value: float) -> None:
        if not self.active or self.current_authority is None:
            return
        requested = finite_float(value)
        if requested is None:
            return
        old = self.current_authority
        current = replace(old, **{field: min(float(getattr(old, field)), float(requested))})
        self.current_authority = current
        self._ratchet_request(current)
        self.last_status = f"adopted-live authority ratcheted down: {field}={float(requested):.3f}"
        self._persist()

    async def _complete_external_off(self) -> None:
        lease = getattr(self.guard, "edge_safety_lease", None)
        if lease is not None:
            try:
                await lease.disarm()
            except Exception:
                pass
        self._retire_manual_software("adopted_live_output_off", failed=False)
        self.state = ManagedAdoptionState.COMPLETED
        self.last_status = "Output became OFF; adopted Manual authority retired"
        self._persist()

    async def observe_once(self) -> None:
        if not self.active:
            return
        if not bool(getattr(self.manager, "pb_managed", False)):
            await self._verified_off("adopted_live_lost_pb_managed_mode")
            return
        if not bool(getattr(self.manual, "is_active", False)):
            live = await self.guard._raw_live()
            if _binary(live.get("switch")) is False:
                await self._complete_external_off()
                return
            await self._verified_off("adopted_live_manual_authority_disappeared_while_on")
            return

        live = await self.app.hass.get_all_live()
        if _binary(live.get("switch")) is False:
            await self._complete_external_off()
            return
        fingerprint = self.fingerprint_from_live(live)
        authority = self.current_authority
        if fingerprint is None or authority is None:
            await self._verified_off("adopted_live_program_readback_lost")
            return

        increases = []
        for field in ("set_voltage_v", "set_current_a", "ovp_v", "ocp_a"):
            actual = float(getattr(fingerprint, field))
            ceiling = float(getattr(authority, field))
            if actual > ceiling + ADOPTION_SETPOINT_TOLERANCE:
                increases.append(f"{field}:{actual:.3f}>{ceiling:.3f}")
        if increases:
            await self._verified_off(
                "adopted_live_out_of_band_authority_increase:" + ",".join(increases)
            )
            return

        ratcheted = ManagedAdoptionFingerprint(
            set_voltage_v=min(authority.set_voltage_v, fingerprint.set_voltage_v),
            set_current_a=min(authority.set_current_a, fingerprint.set_current_a),
            ovp_v=min(authority.ovp_v, fingerprint.ovp_v),
            ocp_a=min(authority.ocp_a, fingerprint.ocp_a),
        )
        if ratcheted != authority:
            self.current_authority = ratcheted
            self._ratchet_request(ratcheted)
            self.last_status = "external setpoints/protections decreased; managed authority ratcheted down"
            self._persist()

        temp = finite_float(live.get("temp_ext_v2"))
        if temp is None:
            temp = finite_float(live.get("temp_ext"))
        if temp is not None and float(temp) >= float(self.guard.policy.pause_temp_c):
            # Unlike a freshly programmed Manual session, adopted-live authority never
            # automatically re-energizes after a thermal pause. OFF ends this adoption.
            await self._verified_off("adopted_live_temperature_pause_requires_fresh_restart")

    async def _run(self) -> None:
        try:
            while self.active:
                await self.observe_once()
                if not self.active:
                    break
                await asyncio.sleep(self.poll_s)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            if self.active:
                await self._verified_off(
                    f"adopted_live_runtime_error:{type(exc).__name__}:{exc}"
                )

    async def recover_startup(self) -> bool:
        if not self.off_pending:
            return True
        ok = await self._verified_off("adopted_live_restart_containment")
        if ok:
            self.state = ManagedAdoptionState.INTERRUPTED
            self.last_status = "restart containment completed; fresh operator adoption is required"
            self._persist()
        return ok


def _preview_text(preview: ManagedAdoptionPreview) -> str:
    fp = preview.fingerprint
    return (
        "<b>🔒 Забрать текущий Output под Pb-контроль</b>\n\n"
        f"АКБ: <code>{preview.battery_id}</code> · {preview.chemistry.value} · {preview.capacity_ah:g} Ah\n"
        "Программа: <b>Adopted Manual</b> — без AUTO/Mix-химии.\n"
        f"RD: {fp.set_voltage_v:.2f} V / {fp.set_current_a:.2f} A · "
        f"OVP {fp.ovp_v:.2f} / OCP {fp.ocp_a:.2f}\n\n"
        "На точке подхвата бот не пишет Output/V/I/OVP/OCP. Эти четыре live-readback "
        "становятся максимальной authority; дальше разрешено только уменьшение. "
        "Любое внешнее увеличение завершает adopted-сессию через verified Output OFF.\n\n"
        "После перезапуска такая live-сессия автоматически не продолжается."
    )


def install_managed_live_adoption(
    app: Any,
    manager: Any,
    *,
    install_ui: bool = True,
) -> ManagedLiveAdoptionCoordinator:
    existing = getattr(app, "rd_managed_live_adoption", None)
    if isinstance(existing, ManagedLiveAdoptionCoordinator):
        return existing

    coordinator = ManagedLiveAdoptionCoordinator(app, manager)
    app.rd_managed_live_adoption = coordinator

    # Compose a non-bypassable adopted authority gate around the already-installed
    # runtime-safety + RD ownership wrappers. It never enlarges ordinary Manual rights.
    hass = app.hass
    if not getattr(hass, "_rd_managed_live_adoption_wrapped", False):
        original_turn_on = hass.turn_on
        original_set_voltage = hass.set_voltage
        original_set_current = hass.set_current
        original_set_ovp = hass.set_ovp
        original_set_ocp = hass.set_ocp

        async def turn_on(entity_id: Optional[str] = None) -> bool:
            if coordinator.active or coordinator.off_pending:
                raise RuntimeSafetyError(
                    "adopted-live Manual cannot re-energize Output; start a fresh managed program"
                )
            return bool(await original_turn_on(entity_id))

        async def _write(field: str, value: float, fn: Any) -> bool:
            coordinator.authorize_managed_write(field, value)
            result = bool(await fn(value))
            if result:
                coordinator.ratchet_after_managed_write(field, value)
            return result

        async def set_voltage(value: float) -> bool:
            return await _write("set_voltage_v", value, original_set_voltage)

        async def set_current(value: float) -> bool:
            return await _write("set_current_a", value, original_set_current)

        async def set_ovp(value: float) -> bool:
            return await _write("ovp_v", value, original_set_ovp)

        async def set_ocp(value: float) -> bool:
            return await _write("ocp_a", value, original_set_ocp)

        hass.turn_on = turn_on
        hass.set_voltage = set_voltage
        hass.set_current = set_current
        hass.set_ovp = set_ovp
        hass.set_ocp = set_ocp
        hass._rd_managed_live_adoption_wrapped = True

    if not install_ui:
        return coordinator

    confirmations = ConfirmationStore()
    pending: dict[tuple[int, int], dict[str, Any]] = {}

    def identity(call: Any) -> Optional[tuple[int, int]]:
        return confirmations.callback_identity(call)

    import operator_hmi

    if not getattr(operator_hmi, "_rd_managed_adoption_keyboard_wrapped", False):
        original_keyboard = operator_hmi.build_operator_keyboard
        original_state = operator_hmi.build_operator_hmi_state

        def build_keyboard(app_arg: Any, state: Any) -> InlineKeyboardMarkup:
            markup = original_keyboard(app_arg, state)
            if (
                state.process_state is operator_hmi.HmiProcessState.HANDS_OFF
                and bool(state.output_on)
                and not coordinator.active
                and not coordinator.off_pending
            ):
                rows = [list(row) for row in markup.inline_keyboard]
                rows.insert(
                    1,
                    [
                        InlineKeyboardButton(
                            text="🔒 Забрать под Pb-контроль",
                            callback_data="rd_managed_adopt",
                        )
                    ],
                )
                return InlineKeyboardMarkup(inline_keyboard=rows)
            return markup

        def build_state(app_arg: Any, live: Any) -> Any:
            state = original_state(app_arg, live)
            if coordinator.active and state.authority is operator_hmi.HmiAuthority.MANUAL:
                return replace(
                    state,
                    title="RD6018 · MANUAL ПОДХВАЧЕН",
                    progress="Live adoption · исходные уставки — максимум, authority только вниз",
                )
            return state

        operator_hmi.build_operator_keyboard = build_keyboard
        operator_hmi.build_operator_hmi_state = build_state
        operator_hmi._rd_managed_adoption_keyboard_wrapped = True

    @app.router.callback_query(F.data == "rd_managed_adopt")
    async def _adopt_menu(call: Any) -> None:
        if not await app._check_chat_and_respond(call):
            return
        key = identity(call)
        if key is None:
            await call.answer("Не удалось привязать подтверждение к чату", show_alert=True)
            return
        if not manager.hands_off:
            await call.answer("Live adoption доступен только из HANDS_OFF", show_alert=True)
            return
        conflict = coordinator._other_authority_active()
        if conflict is not None:
            await call.answer(conflict, show_alert=True)
            return
        live = await coordinator.guard._raw_live()
        try:
            fingerprint = coordinator._preflight_live(live)
        except Exception as exc:
            await call.answer(str(exc), show_alert=True)
            return
        records = await list_batteries(limit=30)
        records = [
            record
            for record in records
            if record.identity.chemistry is not BatteryChemistry.CUSTOM
        ]
        if not records:
            await call.answer("Нет сохранённой Pb АКБ для привязки", show_alert=True)
            return
        pending[key] = {
            "nonce": uuid.uuid4().hex,
            "fingerprint": fingerprint,
            "records": records,
        }
        rows = [
            [
                InlineKeyboardButton(
                    text=battery_button_label(record),
                    callback_data=f"rd_managed_adopt_bat_{index}",
                )
            ]
            for index, record in enumerate(records)
        ]
        rows.append([InlineKeyboardButton(text="Отмена", callback_data="rd_managed_adopt_cancel")])
        await call.answer()
        await call.message.answer(
            "🔒 <b>Какую физическую АКБ сейчас держит RD6018?</b>\n"
            "Это read-only шаг: Output и уставки не меняются.",
            parse_mode=app.ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        )

    @app.router.callback_query(F.data.startswith("rd_managed_adopt_bat_"))
    async def _adopt_battery(call: Any) -> None:
        key = identity(call)
        item = pending.get(key) if key is not None else None
        if item is None:
            await call.answer("Предпросмотр устарел", show_alert=True)
            return
        try:
            index = int(str(call.data).rsplit("_", 1)[-1])
            record = item["records"][index]
        except (ValueError, IndexError):
            await call.answer("Выбор АКБ устарел", show_alert=True)
            return
        fp = item["fingerprint"]
        token = (
            f"d061:{item['nonce']}:{record.identity.battery_id}:"
            f"{fp.set_voltage_v:.3f}:{fp.set_current_a:.3f}:{fp.ovp_v:.3f}:{fp.ocp_a:.3f}"
        )
        preview = ManagedAdoptionPreview(
            token=token,
            battery_id=record.identity.battery_id,
            chemistry=record.identity.chemistry,
            capacity_ah=record.identity.nominal_capacity_ah,
            fingerprint=fp,
        )
        item["preview"] = preview
        await call.answer()
        await call.message.answer(
            _preview_text(preview),
            parse_mode=app.ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="Подтвердить АКБ/химию/Adopted Manual",
                            callback_data="rd_managed_adopt_confirm",
                        )
                    ],
                    [InlineKeyboardButton(text="Отмена", callback_data="rd_managed_adopt_cancel")],
                ]
            ),
        )

    @app.router.callback_query(F.data == "rd_managed_adopt_confirm")
    async def _adopt_confirm(call: Any) -> None:
        if not await app._check_chat_and_respond(call):
            return
        key = identity(call)
        item = pending.get(key) if key is not None else None
        preview = item.get("preview") if item is not None else None
        if not isinstance(preview, ManagedAdoptionPreview):
            await call.answer("Предпросмотр устарел", show_alert=True)
            return
        if not confirmations.issue_for_call(call, preview.token):
            await call.answer("Не удалось создать подтверждение", show_alert=True)
            return
        await call.answer()
        await call.message.answer(
            "⚠️ <b>Последнее подтверждение live adoption.</b>\n"
            "Следующая кнопка начнёт edge ownership transfer. До неё RD не менялся.",
            parse_mode=app.ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="ВЫПОЛНИТЬ ПОДХВАТ",
                            callback_data="rd_managed_adopt_execute",
                        )
                    ],
                    [InlineKeyboardButton(text="Отмена", callback_data="rd_managed_adopt_cancel")],
                ]
            ),
        )

    @app.router.callback_query(F.data == "rd_managed_adopt_execute")
    async def _adopt_execute(call: Any) -> None:
        if not await app._check_chat_and_respond(call):
            return
        key = identity(call)
        item = pending.get(key) if key is not None else None
        preview = item.get("preview") if item is not None else None
        granted = confirmations.consume_for_call(call)
        if not isinstance(preview, ManagedAdoptionPreview) or granted != preview.token:
            await call.answer(
                "Подтверждение отсутствует, истекло, использовано или относится к другой сессии",
                show_alert=True,
            )
            return
        try:
            await coordinator.adopt(preview)
        except Exception as exc:
            await call.answer(str(exc), show_alert=True)
            return
        pending.pop(key, None)
        await call.answer("Live Output принят под PB_MANAGED")
        await call.message.answer(
            "🔒 <b>Adopted Manual активен.</b>\n"
            "На точке adoption Output/V/I/OVP/OCP не переписывались. Локальный edge lease "
            "подтверждён, PB_MANAGED включён, текущие live-уставки стали максимумом authority.",
            parse_mode=app.ParseMode.HTML,
        )

    @app.router.callback_query(F.data == "rd_managed_adopt_cancel")
    async def _adopt_cancel(call: Any) -> None:
        key = identity(call)
        if key is not None:
            pending.pop(key, None)
        confirmations.cancel_for_call(call)
        await call.answer("Отменено; RD не изменён")

    return coordinator
