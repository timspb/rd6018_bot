"""Independent, OFF-only HA/native adapter for the detached D061 stop hook.

This module is deliberately separate from the production composition.  It uses
the node104 transport API directly and has no Output ON or setpoint operation.
"""
from __future__ import annotations

import asyncio
import math
import time
from dataclasses import dataclass
from typing import Any, Callable



@dataclass(frozen=True)
class HardwareOffProof:
    ha_off: bool
    native_off: bool
    protection_normal: bool
    lease_disarmed: bool
    lease_generation: int


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _integer(value: Any) -> int | None:
    number = _number(value)
    return int(number) if number is not None and number.is_integer() else None


def _fresh(meta: Any, key: str, max_age_s: float) -> bool:
    row = meta.get(key) if isinstance(meta, dict) else None
    age = _number(row.get("age_s")) if isinstance(row, dict) else None
    return bool(isinstance(row, dict) and row.get("status") == "ok"
                and age is not None and 0 <= age <= max_age_s)


def _is_off(live: Any, max_age_s: float) -> bool:
    if not isinstance(live, dict):
        return False
    meta = live.get("_meta")
    output = _number(live.get("output_state_code_v2"))
    voltage, current = _number(live.get("voltage")), _number(live.get("current"))
    required = ("output_state_code_v2", "voltage", "current", "protection_code",
                "ovp_readback_v2", "ocp_readback_v2")
    if not all(_fresh(meta, key, max_age_s) for key in required):
        return False
    protection = _number(live.get("protection_code"))
    ovp, ocp = _number(live.get("ovp_readback_v2")), _number(live.get("ocp_readback_v2"))
    # Raw protection NORMAL is code 0; configured protection must remain present
    # and positive.  This check never writes or attempts to repair a setting.
    return (output == 0 and voltage is not None and abs(voltage) <= 0.02
            and current is not None and abs(current) <= 0.02
            and protection == 0 and ovp is not None and ovp > 0
            and ocp is not None and ocp > 0)


def _state(entity: str, report: Any, max_age_s: float) -> Any:
    value, meta = report
    if not isinstance(meta, dict) or meta.get("status") != "ok":
        raise RuntimeError(f"edge {entity} report unavailable")
    actual = str(meta.get("native_type") or "")
    binary = entity in {"safety_lease_armed", "safety_lease_tripped", "safety_boot_quarantine"}
    expected_type = "BinarySensorState" if binary else "SensorState"
    if actual and actual != expected_type:
        raise RuntimeError(f"edge {entity} native entity type mismatch")
    # ESPHome binary sensors publish on state changes only. Generation and
    # Modbus SensorState telemetry supply independently fresh liveness.
    if not binary:
        age = _number(meta.get("age_s"))
        if age is None or not 0 <= age <= max_age_s:
            raise RuntimeError(f"edge {entity} report stale")
    return value


class HardwareOffAdapter:
    """A fresh-instance adapter; factories make all effects injectable in tests."""

    def __init__(self, *, config: Any, ha_factory: Callable[[Any, Any], Any],
                 native_factory: Callable[[Any, Any], Any], timeout_s: float = 10.0,
                 phase_timeout_s: float = 3.0, max_age_s: float = 8.0,
                 monotonic: Callable[[], float] = time.monotonic):
        self.config, self.ha_factory, self.native_factory = config, ha_factory, native_factory
        self.timeout_s, self.phase_timeout_s, self.max_age_s = timeout_s, phase_timeout_s, max_age_s
        self.monotonic = monotonic

    async def _phase(self, awaitable: Any, deadline: float, name: str) -> Any:
        remaining = min(self.phase_timeout_s, deadline - self.monotonic())
        if remaining <= 0:
            if hasattr(awaitable, "close"):
                awaitable.close()
            raise TimeoutError(f"D061 {name}: lifecycle deadline expired")
        try:
            return await asyncio.wait_for(awaitable, timeout=remaining)
        except asyncio.TimeoutError as exc:
            raise TimeoutError(f"D061 {name}: phase deadline expired") from exc

    async def run(self) -> HardwareOffProof:
        deadline = self.monotonic() + self.timeout_s
        ha = self.ha_factory(self.config.transports["ha102"], self.config.rd)
        native = self.native_factory(self.config.transports["esp128"], self.config.rd)
        try:
            # Connection/discovery is read-only.  Commands are each OFF-only;
            # both are attempted even if the first channel fails.
            command_errors = []
            for name, transport in (("HA discovery", ha), ("native discovery", native)):
                try:
                    await self._phase(transport.discover(), deadline, name)
                except Exception as exc:
                    command_errors.append(f"{name}: {type(exc).__name__}")
            for name, transport in (("HA OFF", ha), ("native OFF", native)):
                try:
                    await self._phase(transport.disable_output(), deadline, name)
                except BaseException as exc:
                    command_errors.append(f"{name}: {exc}")

            # Acknowledgement is not proof.  Require distinct fresh reports and
            # bounded retries while the shared stop-hook deadline remains.
            proven = False
            while self.monotonic() < deadline:
                try:
                    ha_live = await self._phase(ha.get_live_values(), deadline, "HA readback")
                    native_live = await self._phase(native.get_live_values(), deadline, "native readback")
                    if _is_off(ha_live, self.max_age_s) and _is_off(native_live, self.max_age_s):
                        proven = True
                        break
                except (RuntimeError, TimeoutError, asyncio.TimeoutError):
                    pass
                await asyncio.sleep(min(0.15, max(0.0, deadline - self.monotonic())))
            if not proven:
                detail = "; ".join(command_errors)
                raise RuntimeError("fresh independent HA/native verified-OFF proof unavailable" +
                                   (f" ({detail})" if detail else ""))

            # The exact deployed image has no get_physical_output_report or
            # get_button_info.  Use subscribed states plus ButtonInfo inventory.
            initial_armed = None
            for object_id, expected in (("safety_lease_armed", None),
                                        ("safety_lease_tripped", False),
                                        ("safety_boot_quarantine", False),
                                        ("safety_lease_generation", None),
                                        ("safety_modbus_age", None)):
                val, meta = await self._phase(native.get_entity_state(object_id), deadline,
                                              f"edge {object_id}")
                val = _state(object_id, (val, meta), self.max_age_s)
                if object_id == "safety_lease_armed":
                    initial_armed = val
                if expected is not None and val is not expected:
                    raise RuntimeError(f"edge {object_id} is not in required state")
                if (expected is None and object_id != "safety_lease_armed"
                        and _number(val) is None):
                    raise RuntimeError(f"edge {object_id} is invalid")
                if object_id == "safety_lease_armed" and type(val) is not bool:
                    raise RuntimeError("edge armed state is invalid")
                if object_id == "safety_lease_generation":
                    generation = _integer(val)
                    if generation is None:
                        raise RuntimeError("edge lease generation is invalid")
                elif object_id == "safety_modbus_age":
                    age = _number(val)
                    if age is None or age < 0 or age > 20:
                        raise RuntimeError("edge Modbus heartbeat is stale")

            # Retain the pre-command armed value from a fresh report.  An
            # already-disarmed lease is a valid idempotent stop-hook state.
            armed_before, armed_meta = await self._phase(native.get_entity_state("safety_lease_armed"), deadline,
                                                          "edge armed confirmation")
            was_armed = _state("safety_lease_armed", (armed_before, armed_meta), self.max_age_s)
            if was_armed is not initial_armed:
                raise RuntimeError("edge armed state changed during stop preflight")
            if was_armed is not False and was_armed is not True:
                raise RuntimeError("edge armed state is invalid")
            button = next((item for item in native.entities
                           if str(getattr(item, "object_id", "")) == "safety_lease_disarm"
                           and type(item).__name__ == "ButtonInfo"), None)
            if was_armed is True and (button is None or native.client is None):
                raise RuntimeError("native safety_lease_disarm ButtonInfo unavailable")
            # Invocation can be ambiguous.  We do not retry blindly; verify the
            # resulting fresh state and generation (generation may stay same when
            # already disarmed, which is handled by pre-command armed check).
            if was_armed:
                native.client.button_command(int(button.key), int(button.device_id))
            disarm_error = None
            try:
                armed, armed_meta = await self._phase(native.get_entity_state("safety_lease_armed"), deadline,
                                                      "post-disarm armed readback")
                gen, gen_meta = await self._phase(native.get_entity_state("safety_lease_generation"), deadline,
                                                  "post-disarm generation readback")
                expected_generation = generation  # ESP disarm leaves generation unchanged
                post_generation = _integer(_state("safety_lease_generation",
                                                  (gen, gen_meta), self.max_age_s))
                if (_state("safety_lease_armed", (armed, armed_meta), self.max_age_s) is not False
                        or post_generation != expected_generation):
                    raise RuntimeError("edge lease disarm acknowledgement/readback mismatch")
            except BaseException as exc:
                disarm_error = exc
            if disarm_error:
                # An ambiguous command must remain a visible failure. A second
                # independent OFF pass contains Output but cannot manufacture ACK.
                for transport in (ha, native):
                    try:
                        await self._phase(transport.disable_output(), deadline, "ambiguous disarm containment OFF")
                    except BaseException:
                        pass
                raise RuntimeError("edge disarm outcome ambiguous; OFF containment requested") from disarm_error
            return HardwareOffProof(True, True, True, True, expected_generation)
        finally:
            for transport in (native, ha):
                close = getattr(transport, "close", None)
                if callable(close):
                    try:
                        await asyncio.wait_for(close(), timeout=max(0.05, min(1.0, deadline - self.monotonic())))
                    except BaseException:
                        pass


async def emergency_off(*, config_root: str, timeout_s: float = 10.0) -> HardwareOffProof:
    """Load pinned node config and invoke only the independent OFF adapter."""
    from pathlib import Path
    from runtime.config import load_config
    from runtime.physical.transports.esp128 import ESPHomeTransport
    from runtime.physical.transports.ha102 import HA102Transport
    root = Path(config_root).resolve(strict=True)
    expected = Path("/opt/services/rd6018-bot/app/config").resolve()
    if root != expected:
        raise RuntimeError("D061 stop helper requires exact node104 deployed config path")
    import os
    override = os.environ.get("RD6018_CONFIG_DIR", "").strip()
    if override and Path(override).resolve() != expected:
        raise RuntimeError("RD6018_CONFIG_DIR conflicts with pinned node104 config path")
    config = load_config(root)
    if not config.transports["ha102"].connection.host or not config.transports["esp128"].connection.host:
        raise RuntimeError("D061 stop helper requires configured node104 HA and ESP hosts")
    return await HardwareOffAdapter(config=config, ha_factory=HA102Transport,
        native_factory=ESPHomeTransport, timeout_s=timeout_s).run()
