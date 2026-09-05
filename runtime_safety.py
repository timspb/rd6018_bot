from __future__ import annotations

import asyncio
import logging
import math
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, Optional

from charge_logic import MAX_STAGE_CURRENT
from config import MAX_VOLTAGE, MIN_INPUT_VOLTAGE, TEMP_INT_PRECRITICAL
from rd6018_telemetry import _parse_iso_timestamp
from safe_output import SafetyPolicy


logger = logging.getLogger("rd6018")


class RuntimeSafetyError(RuntimeError):
    """A live RD6018 operation could not be proved safe."""


class OutputOffNotConfirmed(RuntimeSafetyError):
    """The software requested OFF but could not prove that the output is OFF."""


@dataclass(frozen=True)
class _OutputEvidence:
    state: Optional[bool]
    source_key: str
    heartbeat_epoch: Optional[float]
    requires_fresh_heartbeat: bool


def _finite(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _binary(value: Any) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if value == 1:
            return True
        if value == 0:
            return False
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"on", "true", "1"}:
            return True
        if normalized in {"off", "false", "0"}:
            return False
    return None


class RuntimeSafetyGuard:
    """Fail-closed safety boundary around the live Home Assistant adapter.

    The legacy Telegram runtime intentionally stays intact, but all hardware calls go
    through one HassClient instance.  Wrapping that instance here fixes three unsafe
    classes without depending on every caller remembering to check return values:

    * incomplete/unavailable safety telemetry may never be converted to numeric zero
      while a charge session is active;
    * protection/setpoint changes while the output is ON are read back and must keep
      a valid OVP/OCP envelope;
    * an OFF command is successful only after the physical switch entity confirms OFF.

    The guard never invents a charge transition or a recipe.  It only blocks or turns
    the output off when the existing actuator contract cannot be proved safe.
    """

    # ESPHome polls the RD6018 register-18 state every 5 seconds. A 12-second
    # bounded window spans two possible polls and leaves margin for HA transport;
    # it is deliberately centralized here rather than expressed as retry magic.
    OFF_CONFIRMATION_WINDOW_S = 12.0
    OFF_CONFIRMATION_POLL_S = 0.50
    OFF_CONFIRMATION_MAX_RETRIES = 1
    OFF_CONFIRMATION_CLOCK_SKEW_S = 1.0
    READBACK_VERIFY_ATTEMPTS = 8
    READBACK_VERIFY_DELAY_S = 0.20
    READBACK_TOLERANCE = 0.08
    PROTECTION_MARGIN = 0.05
    ORPHAN_OUTPUT_GRACE_S = 45.0
    NOTIFY_REPEAT_S = 10 * 60.0

    def __init__(self, app: Any) -> None:
        self.app = app
        self.hass = app.hass
        self.policy = SafetyPolicy()

        # Capture the actual adapter methods before replacing instance attributes.
        self._raw_get_all_live: Callable[[], Awaitable[Dict[str, Any]]] = self.hass.get_all_live
        self._raw_turn_on = self.hass.turn_on
        self._raw_turn_off = self.hass.turn_off
        self._raw_set_voltage = self.hass.set_voltage
        self._raw_set_current = self.hass.set_current
        self._raw_set_ovp = self.hass.set_ovp
        self._raw_set_ocp = self.hass.set_ocp

        self._off_lock = asyncio.Lock()
        self._off_unconfirmed = False
        self._orphan_output_seen_at: Optional[float] = None
        self._last_notice_key: Optional[str] = None
        self._last_notice_at = 0.0

    def install(self) -> "RuntimeSafetyGuard":
        if getattr(self.hass, "_runtime_safety_guard", None) is not None:
            return getattr(self.hass, "_runtime_safety_guard")

        self.hass.get_all_live = self.get_all_live
        self.hass.turn_on = self.turn_on
        self.hass.turn_off = self.turn_off
        self.hass.set_voltage = self.set_voltage
        self.hass.set_current = self.set_current
        self.hass.set_ovp = self.set_ovp
        self.hass.set_ocp = self.set_ocp
        self.hass._runtime_safety_guard = self
        return self

    @property
    def controller_active(self) -> bool:
        return bool(getattr(self.app.charge_controller, "is_active", False))

    def _recipe_voltage_ceiling(self) -> float:
        controller = self.app.charge_controller
        try:
            envelope = controller._recipe_envelope()
        except Exception:
            envelope = None
        if envelope is not None:
            try:
                ceiling = float(envelope.voltage_ceiling_v)
                if math.isfinite(ceiling) and ceiling > 0:
                    return min(ceiling, self.policy.absolute_voltage_ceiling_v)
            except (TypeError, ValueError):
                pass
        return min(float(MAX_VOLTAGE), self.policy.absolute_voltage_ceiling_v)

    def _notify(self, key: str, message: str) -> None:
        now = time.monotonic()
        if self._last_notice_key == key and now - self._last_notice_at < self.NOTIFY_REPEAT_S:
            return
        self._last_notice_key = key
        self._last_notice_at = now
        try:
            self.app._charge_notify(message)
        except Exception:
            pass

    async def _raw_live(self) -> Dict[str, Any]:
        live = await self._raw_get_all_live()
        return live if isinstance(live, dict) else {}

    @staticmethod
    def _output_evidence(live: Dict[str, Any]) -> _OutputEvidence:
        """Return canonical Output value and its source heartbeat.

        V2 register-18 is authoritative whenever it is present. In that mode a
        missing heartbeat is not silently replaced with the public actuator switch:
        an old cached value cannot confirm a new OFF command.
        """

        meta = live.get("_meta")
        metadata = meta.get("output_state_code_v2") if isinstance(meta, dict) else None
        code = _finite(live.get("output_state_code_v2"))
        if code is not None:
            state = False if code == 0 else True if code == 1 else None
            if not isinstance(metadata, dict) and isinstance(meta, dict):
                switch_meta = meta.get("switch")
                if isinstance(switch_meta, dict) and switch_meta.get("source_key") == "output_state_code_v2":
                    metadata = switch_meta
            heartbeat = None
            if isinstance(metadata, dict):
                heartbeat = _parse_iso_timestamp(metadata.get("last_reported"))
                if heartbeat is None:
                    heartbeat = _parse_iso_timestamp(metadata.get("last_updated"))
            return _OutputEvidence(state, "output_state_code_v2", heartbeat, True)

        metadata = meta.get("switch") if isinstance(meta, dict) else None
        heartbeat = None
        if isinstance(metadata, dict):
            heartbeat = _parse_iso_timestamp(metadata.get("last_reported"))
            if heartbeat is None:
                heartbeat = _parse_iso_timestamp(metadata.get("last_updated"))
        return _OutputEvidence(_binary(live.get("switch")), "switch", heartbeat, heartbeat is not None)

    def _is_post_command(
        self,
        evidence: _OutputEvidence,
        before: Optional[_OutputEvidence],
        command_start_epoch: float,
    ) -> bool:
        if not evidence.requires_fresh_heartbeat:
            return True
        if evidence.heartbeat_epoch is None:
            return False
        if before is not None and before.source_key == evidence.source_key and before.heartbeat_epoch is not None:
            return (
                evidence.heartbeat_epoch > before.heartbeat_epoch
                and evidence.heartbeat_epoch >= command_start_epoch - self.OFF_CONFIRMATION_CLOCK_SKEW_S
            )
        # If no pre-command heartbeat existed, the first usable report must still
        # belong to the command epoch (allowing only small clock skew).
        return evidence.heartbeat_epoch >= command_start_epoch - 1.0

    async def _verify_switch_off(
        self,
        *,
        before: Optional[_OutputEvidence],
        command_start_monotonic: float,
        command_start_epoch: float,
        entity_id: Optional[str],
    ) -> bool:
        deadline = command_start_monotonic + max(0.0, float(self.OFF_CONFIRMATION_WINDOW_S))
        retries = 0
        while True:
            try:
                live = await self._raw_live()
            except Exception as exc:
                logger.warning("Output OFF confirmation read failed: %s", exc)
                live = {}

            evidence = self._output_evidence(live)
            post_command = self._is_post_command(evidence, before, command_start_epoch)
            if evidence.state is False and post_command:
                heartbeat = (
                    "none"
                    if evidence.heartbeat_epoch is None
                    else f"{evidence.heartbeat_epoch:.3f}"
                )
                logger.info(
                    "Output OFF confirmed: source=%s heartbeat_epoch=%s post_command=true",
                    evidence.source_key,
                    heartbeat,
                )
                return True

            if (
                evidence.state is True
                and post_command
                and retries < int(self.OFF_CONFIRMATION_MAX_RETRIES)
            ):
                retries += 1
                logger.warning(
                    "Output OFF retry %d/%d: fresh %s heartbeat still reports ON",
                    retries,
                    int(self.OFF_CONFIRMATION_MAX_RETRIES),
                    evidence.source_key,
                )
                try:
                    await self._raw_turn_off(entity_id)
                except Exception as exc:
                    logger.warning("Output OFF retry %d failed: %s", retries, exc)

            remaining = deadline - time.monotonic()
            if remaining <= 0.0:
                return False
            await asyncio.sleep(min(float(self.OFF_CONFIRMATION_POLL_S), remaining))

    async def _ensure_output_off(self, reason: str, entity_id: Optional[str] = None) -> bool:
        async with self._off_lock:
            before: Optional[_OutputEvidence] = None
            try:
                before = self._output_evidence(await self._raw_live())
            except Exception as exc:
                logger.warning("Output OFF pre-command read failed: %s", exc)

            command_start_monotonic = time.monotonic()
            command_start_epoch = time.time()
            command_ok = False
            try:
                command_ok = bool(await self._raw_turn_off(entity_id))
            except Exception:
                command_ok = False
            logger.info(
                "Output OFF command issued: reason=%s accepted=%s",
                reason,
                command_ok,
            )

            if await self._verify_switch_off(
                before=before,
                command_start_monotonic=command_start_monotonic,
                command_start_epoch=command_start_epoch,
                entity_id=entity_id,
            ):
                self._off_unconfirmed = False
                logger.info("Output OFF verification complete: reason=%s", reason)
                return True

            self._off_unconfirmed = True
            self._notify(
                "off_unconfirmed",
                "🚨 <b>АВАРИЯ ЗАЩИТЫ:</b> команда Output OFF не подтверждена. "
                "Бот блокирует дальнейшее включение. Проверьте RD6018/HA и при необходимости "
                "отключите выход или питание вручную.",
            )
            detail = "OFF command accepted but switch state was not confirmed" if command_ok else "OFF command failed and switch state was not confirmed"
            raise OutputOffNotConfirmed(f"{reason}: {detail}")

    def _critical_telemetry_error(self, live: Dict[str, Any], *, require_programming: bool) -> Optional[str]:
        numeric = (
            "battery_voltage",
            "current",
            "temp_ext",
            "temp_int",
            "input_voltage",
        )
        for key in numeric:
            if _finite(live.get(key)) is None:
                return f"required telemetry {key} is missing/unavailable"

        for key in ("switch", "ovp_triggered", "ocp_triggered"):
            if _binary(live.get(key)) is None:
                return f"required telemetry {key} is missing/unavailable"

        battery_v = _finite(live.get("battery_voltage"))
        assert battery_v is not None
        if not (self.policy.min_battery_voltage_v <= battery_v <= self.policy.max_battery_voltage_v):
            return f"battery voltage is implausible: {battery_v:.3f}V"

        if require_programming:
            for key in ("set_voltage", "set_current", "ovp", "ocp"):
                if _finite(live.get(key)) is None:
                    return f"live protection/readback {key} is missing/unavailable"
        return None

    def _runtime_envelope_error(self, live: Dict[str, Any]) -> Optional[str]:
        # A real OVP/OCP trip is deliberately returned to the existing runtime so it
        # can log the exact hardware event and execute its normal hard-stop path.
        if _binary(live.get("ovp_triggered")) or _binary(live.get("ocp_triggered")):
            return None

        input_v = _finite(live.get("input_voltage"))
        if input_v is None or input_v < float(MIN_INPUT_VOLTAGE):
            return f"input voltage {input_v!r}V is below {MIN_INPUT_VOLTAGE:.1f}V"

        set_v = _finite(live.get("set_voltage"))
        set_i = _finite(live.get("set_current"))
        ovp = _finite(live.get("ovp"))
        ocp = _finite(live.get("ocp"))
        actual_i = _finite(live.get("current"))
        if None in (set_v, set_i, ovp, ocp, actual_i):
            return "programming/readback became invalid while output was ON"
        assert set_v is not None and set_i is not None and ovp is not None and ocp is not None and actual_i is not None

        recipe_ceiling = self._recipe_voltage_ceiling()
        if set_v > recipe_ceiling + self.READBACK_TOLERANCE:
            return f"set voltage {set_v:.3f}V exceeds recipe ceiling {recipe_ceiling:.3f}V"
        if set_v > self.policy.absolute_voltage_ceiling_v + self.READBACK_TOLERANCE:
            return f"set voltage {set_v:.3f}V exceeds absolute ceiling"
        if set_i <= 0 or set_i > float(MAX_STAGE_CURRENT) + self.READBACK_TOLERANCE:
            return f"set current {set_i:.3f}A exceeds runtime envelope"
        if actual_i > self.policy.absolute_ocp_ceiling_a + self.READBACK_TOLERANCE:
            return f"measured current {actual_i:.3f}A exceeds absolute runtime envelope"
        if ovp > self.policy.absolute_ovp_ceiling_v + self.READBACK_TOLERANCE:
            return f"OVP {ovp:.3f}V exceeds absolute protection ceiling"
        if ocp > self.policy.absolute_ocp_ceiling_a + self.READBACK_TOLERANCE:
            return f"OCP {ocp:.3f}A exceeds absolute protection ceiling"
        if ovp + self.READBACK_TOLERANCE < set_v + self.PROTECTION_MARGIN:
            return f"OVP {ovp:.3f}V does not protect set voltage {set_v:.3f}V"
        if ocp + self.READBACK_TOLERANCE < set_i + self.PROTECTION_MARGIN:
            return f"OCP {ocp:.3f}A does not protect set current {set_i:.3f}A"
        return None

    @staticmethod
    def _current_evidence(live: Dict[str, Any]) -> Optional[float]:
        return _finite(live.get("set_current"))

    async def _fail_closed(self, key: str, reason: str, *, output_state: Optional[bool]) -> None:
        self._notify(
            key,
            f"🛑 <b>Защита V2:</b> {reason}. "
            "Автоматическое управление приостановлено до валидной телеметрии/защиты.",
        )
        # If ON is confirmed, or the switch itself is unavailable while an active
        # controller may still be driving the PSU, attempt an immediate verified OFF.
        if output_state is True or (output_state is None and self.controller_active):
            await self._ensure_output_off(reason)
        raise RuntimeSafetyError(reason)

    async def get_all_live(self) -> Dict[str, Any]:
        live = await self._raw_live()
        output_state = _binary(live.get("switch"))
        safety_relevant = self.controller_active or output_state is True or self._off_unconfirmed
        if not safety_relevant:
            self._orphan_output_seen_at = None
            return live

        error = self._critical_telemetry_error(live, require_programming=output_state is True)
        if error is not None:
            await self._fail_closed("telemetry_invalid", error, output_state=output_state)

        # Input undervoltage is a runtime safety condition as well as a start gate.
        input_v = _finite(live.get("input_voltage"))
        if input_v is not None and input_v < float(MIN_INPUT_VOLTAGE):
            await self._fail_closed(
                "input_voltage_low",
                f"входное напряжение {input_v:.1f}V < {MIN_INPUT_VOLTAGE:.1f}V",
                output_state=output_state,
            )

        if output_state is False:
            self._off_unconfirmed = False
            self._orphan_output_seen_at = None
            return live

        if output_state is True and not self.controller_active:
            now = time.monotonic()
            if self._orphan_output_seen_at is None:
                # One data_logger pass is allowed so a valid persisted session can be
                # restored after a bot restart.  An unmanaged output may not remain ON.
                self._orphan_output_seen_at = now
                return live
            if now - self._orphan_output_seen_at >= self.ORPHAN_OUTPUT_GRACE_S:
                await self._fail_closed(
                    "unmanaged_output",
                    "RD6018 output остаётся ON без активной/восстановленной сессии",
                    output_state=True,
                )
            return live

        if output_state is True:
            envelope_error = self._runtime_envelope_error(live)
            if envelope_error is not None:
                await self._fail_closed("runtime_envelope", envelope_error, output_state=True)

        return live

    async def turn_off(self, entity_id: Optional[str] = None) -> bool:
        return await self._ensure_output_off("requested output shutdown", entity_id)

    async def turn_on(self, entity_id: Optional[str] = None) -> bool:
        if self._off_unconfirmed:
            try:
                if _binary((await self._raw_live()).get("switch")) is False:
                    self._off_unconfirmed = False
                else:
                    raise OutputOffNotConfirmed("previous OFF command is still unconfirmed")
            except OutputOffNotConfirmed:
                raise
            except Exception as exc:
                raise OutputOffNotConfirmed("previous OFF command is still unconfirmed") from exc

        try:
            enabled = bool(await self._raw_turn_on(entity_id))
        except Exception:
            # A failed/exceptional enable is safe only if OFF can be proved afterwards.
            await self._ensure_output_off("turn-on raised before safe state was confirmed", entity_id)
            raise

        if not enabled:
            await self._ensure_output_off("turn-on failed", entity_id)
            return False

        live = await self._raw_live()
        output_state = _binary(live.get("switch"))
        error = self._critical_telemetry_error(live, require_programming=True)
        if error is None:
            error = self._runtime_envelope_error(live)
        if output_state is not True or error is not None:
            await self._ensure_output_off(error or "turn-on switch state was not confirmed", entity_id)
            if error is not None:
                raise RuntimeSafetyError(error)
            return False
        return True

    async def _output_state_raw(self) -> Optional[bool]:
        try:
            return _binary((await self._raw_live()).get("switch"))
        except Exception:
            return None

    async def _verify_numeric(self, key: str, expected: float) -> bool:
        for attempt in range(self.READBACK_VERIFY_ATTEMPTS):
            if attempt:
                await asyncio.sleep(self.READBACK_VERIFY_DELAY_S)
            try:
                live = await self._raw_live()
                observed = (
                    self._current_evidence(live)
                    if key == "set_current"
                    else _finite(live.get(key))
                )
            except Exception:
                observed = None
            if observed is not None and abs(observed - expected) <= self.READBACK_TOLERANCE:
                return True
        return False

    async def _setter_failed(self, name: str, value: float, output_state: Optional[bool]) -> bool:
        reason = f"{name}({value:.3f}) could not be programmed/read back"
        if output_state is True or (output_state is None and self.controller_active):
            await self._ensure_output_off(reason)
            raise RuntimeSafetyError(reason)
        return False

    async def set_ovp(self, value: float) -> bool:
        requested = _finite(value)
        output_state = await self._output_state_raw()
        if requested is None or requested <= 0 or requested > self.policy.absolute_ovp_ceiling_v:
            return await self._setter_failed("OVP", float(value), output_state)
        ok = bool(await self._raw_set_ovp(requested))
        if not ok:
            return await self._setter_failed("OVP", requested, output_state)
        if output_state is True and not await self._verify_numeric("ovp", requested):
            return await self._setter_failed("OVP readback", requested, output_state)
        return True

    async def set_ocp(self, value: float) -> bool:
        requested = _finite(value)
        output_state = await self._output_state_raw()
        if requested is None or requested <= 0 or requested > self.policy.absolute_ocp_ceiling_a:
            return await self._setter_failed("OCP", float(value), output_state)
        ok = bool(await self._raw_set_ocp(requested))
        if not ok:
            return await self._setter_failed("OCP", requested, output_state)
        if output_state is True and not await self._verify_numeric("ocp", requested):
            return await self._setter_failed("OCP readback", requested, output_state)
        return True

    async def set_voltage(self, value: float) -> bool:
        requested = _finite(value)
        output_state = await self._output_state_raw()
        ceiling = self._recipe_voltage_ceiling()
        if requested is None or requested < 0 or requested > ceiling + 1e-9:
            return await self._setter_failed("voltage", float(value), output_state)

        if output_state is True:
            live = await self._raw_live()
            ovp = _finite(live.get("ovp"))
            if ovp is None or ovp + self.READBACK_TOLERANCE < requested + self.PROTECTION_MARGIN:
                await self._ensure_output_off("voltage raise attempted without confirmed OVP margin")
                raise RuntimeSafetyError("voltage setpoint blocked: OVP margin is not confirmed")

        ok = bool(await self._raw_set_voltage(requested))
        if not ok:
            return await self._setter_failed("voltage", requested, output_state)
        if output_state is True and not await self._verify_numeric("set_voltage", requested):
            return await self._setter_failed("voltage readback", requested, output_state)
        return True

    async def set_current(self, value: float) -> bool:
        requested = _finite(value)
        output_state = await self._output_state_raw()
        if requested is None or requested <= 0 or requested > float(MAX_STAGE_CURRENT) + 1e-9:
            return await self._setter_failed("current", float(value), output_state)

        if output_state is True:
            live = await self._raw_live()
            ocp = _finite(live.get("ocp"))
            if ocp is None or ocp + self.READBACK_TOLERANCE < requested + self.PROTECTION_MARGIN:
                await self._ensure_output_off("current raise attempted without confirmed OCP margin")
                raise RuntimeSafetyError("current setpoint blocked: OCP margin is not confirmed")

        ok = bool(await self._raw_set_current(requested))
        if not ok:
            return await self._setter_failed("current", requested, output_state)
        if output_state is True and not await self._verify_numeric("set_current", requested):
            return await self._setter_failed("current readback", requested, output_state)
        return True


def install_runtime_safety(app: Any) -> RuntimeSafetyGuard:
    existing = getattr(app.hass, "_runtime_safety_guard", None)
    if isinstance(existing, RuntimeSafetyGuard):
        return existing
    guard = RuntimeSafetyGuard(app)
    guard.install()
    app.runtime_safety_guard = guard
    return guard
