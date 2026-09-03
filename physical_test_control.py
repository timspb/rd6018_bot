"""Local-only physical validation control plane.

The server is deliberately small and disabled by default. It runs in the
production bot event loop and delegates every stateful operation to the
already-installed production managers/coordinator. A separate client can
only submit the typed operations defined below over a filesystem-protected
Unix-domain socket.

The D061 fault operations are deterministic, one-shot validation hooks. They
never accept setpoints/entity IDs and never widen managed authority. They are
available only through this already opt-in Unix control plane.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import stat
import uuid
from dataclasses import asdict, is_dataclass
from enum import Enum
from typing import Any, Dict, Optional

from battery_registry import get_battery
from edge_safety_lease import EdgeSafetyLeaseError
from pb_domain import BatteryChemistry
from rd_managed_adoption import ManagedAdoptionPreview


DEFAULT_SOCKET_PATH = "/run/rd6018-bot-physical-test-control.sock"
ENV_ENABLE = "RD6018_PHYSICAL_TEST_CONTROL"
_BATTERY_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_OPS = {
    "status",
    "enter_hands_off_verified_off",
    "d061_adopt_battery",
    "d061_verified_stop",
}
_FAULT_OPS = {
    "d061_fault_toctou_precommand",
    "d061_fault_ambiguous_edge_ack",
    "d061_fault_raw_protection_unavailable",
}


class PhysicalTestControlError(RuntimeError):
    """A request was rejected without granting new production authority."""


def enabled_from_environment() -> bool:
    """Return the explicit opt-in flag; the safe default is disabled."""

    return os.getenv(ENV_ENABLE, "").strip().lower() in {"1", "true", "yes", "on"}


def _enum_value(value: Any) -> Any:
    return value.value if isinstance(value, Enum) else value


def _json_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return {key: _json_value(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


class PhysicalTestControl:
    """In-process dispatcher and AF_UNIX transport for physical validation."""

    def __init__(
        self,
        app: Any,
        *,
        socket_path: str = DEFAULT_SOCKET_PATH,
        enabled: Optional[bool] = None,
    ) -> None:
        self.app = app
        self.socket_path = str(socket_path)
        self.enabled = enabled_from_environment() if enabled is None else bool(enabled)
        self._server: Optional[asyncio.AbstractServer] = None
        self._operation_lock = asyncio.Lock()

    async def start(self) -> bool:
        """Bind only the opt-in Unix socket; never bind TCP."""

        if not self.enabled:
            return False
        if self._server is not None:
            return True

        if os.path.exists(self.socket_path):
            mode = os.stat(self.socket_path).st_mode
            if not stat.S_ISSOCK(mode):
                raise PhysicalTestControlError(
                    f"refusing to replace non-socket path: {self.socket_path}"
                )
            os.unlink(self.socket_path)

        self._server = await asyncio.start_unix_server(
            self._handle_client,
            path=self.socket_path,
            limit=8192,
        )
        os.chmod(self.socket_path, 0o600)
        return True

    async def stop(self) -> None:
        server, self._server = self._server, None
        if server is not None:
            server.close()
            await server.wait_closed()
        try:
            if os.path.exists(self.socket_path) and stat.S_ISSOCK(os.stat(self.socket_path).st_mode):
                os.unlink(self.socket_path)
        except FileNotFoundError:
            pass

    async def _handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        try:
            raw = await reader.readline()
            if not raw or len(raw) > 8192:
                response = self._error("malformed request")
            else:
                try:
                    request = json.loads(raw.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    response = self._error("malformed JSON request")
                else:
                    response = await self.dispatch(request)
            writer.write((json.dumps(response, ensure_ascii=True) + "\n").encode("utf-8"))
            await writer.drain()
        except Exception:
            # Transport failures must not leak details or mutate state.
            try:
                writer.write(b'{"ok":false,"error":"request failed"}\n')
                await writer.drain()
            except Exception:
                pass
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

    @staticmethod
    def _error(message: str) -> Dict[str, Any]:
        return {"ok": False, "error": str(message)}

    @staticmethod
    def _require_fields(request: Dict[str, Any], fields: set[str]) -> None:
        if set(request) != fields:
            raise PhysicalTestControlError("unexpected or missing request fields")

    async def dispatch(self, request: Any) -> Dict[str, Any]:
        """Dispatch one strictly typed request inside this process."""

        if not isinstance(request, dict):
            return self._error("request must be a JSON object")
        operation = request.get("op")
        if not isinstance(operation, str) or operation not in (_OPS | _FAULT_OPS):
            return self._error("unknown operation")

        try:
            async with self._operation_lock:
                if operation == "status":
                    self._require_fields(request, {"op"})
                    result = await self._status()
                elif operation == "enter_hands_off_verified_off":
                    self._require_fields(request, {"op"})
                    result = await self._enter_hands_off_verified_off()
                elif operation == "d061_adopt_battery":
                    self._require_fields(request, {"op", "battery_id"})
                    result = await self._adopt_battery(request["battery_id"])
                elif operation == "d061_verified_stop":
                    self._require_fields(request, {"op"})
                    result = await self._verified_stop()
                elif operation == "d061_fault_toctou_precommand":
                    self._require_fields(request, {"op", "battery_id"})
                    result = await self._fault_toctou_precommand(request["battery_id"])
                elif operation == "d061_fault_ambiguous_edge_ack":
                    self._require_fields(request, {"op", "battery_id"})
                    result = await self._fault_ambiguous_edge_ack(request["battery_id"])
                else:
                    self._require_fields(request, {"op"})
                    result = await self._fault_raw_protection_unavailable()
            return {"ok": True, "operation": operation, "result": _json_value(result)}
        except (PhysicalTestControlError, ValueError, TypeError) as exc:
            return self._error(str(exc))
        except Exception as exc:
            # Keep the protocol fail-closed while preserving a useful typed error.
            return self._error(f"operation rejected: {type(exc).__name__}: {exc}")

    async def _raw_live(self) -> Dict[str, Any]:
        guard = getattr(self.app, "runtime_safety_guard", None)
        reader = getattr(guard, "_raw_live", None)
        if not callable(reader):
            raise PhysicalTestControlError("raw safety reader unavailable")
        live = await reader()
        if not isinstance(live, dict):
            raise PhysicalTestControlError("raw safety reader returned invalid data")
        return live

    async def _lease_state(self) -> Any:
        guard = self.app.runtime_safety_guard
        lease = getattr(guard, "edge_safety_lease", None)
        reader = getattr(lease, "read_state", None)
        if not callable(reader):
            raise PhysicalTestControlError("edge lease reader unavailable")
        return await reader()

    @staticmethod
    def _is_on(live: Dict[str, Any]) -> bool:
        try:
            return live.get("switch") == "on" and float(live.get("output_state_code_v2")) == 1.0
        except (TypeError, ValueError):
            return False

    @staticmethod
    def _is_off(live: Dict[str, Any]) -> bool:
        try:
            return live.get("switch") == "off" and float(live.get("output_state_code_v2")) == 0.0
        except (TypeError, ValueError):
            return False

    @staticmethod
    def _fingerprint(value: Any) -> Optional[Dict[str, float]]:
        if value is None:
            return None
        return {
            "set_voltage_v": float(value.set_voltage_v),
            "set_current_a": float(value.set_current_a),
            "ovp_v": float(value.ovp_v),
            "ocp_a": float(value.ocp_a),
        }

    async def _status(self) -> Dict[str, Any]:
        live = await self._raw_live()
        lease = await self._lease_state()
        manager = self.app.rd_control_mode_manager
        adoption = self.app.rd_managed_live_adoption
        manual = self.app.manual_session_manager
        return {
            "rd_control_mode": _enum_value(manager.mode),
            "adoption_state": _enum_value(adoption.state),
            "manual_state": _enum_value(manual.state),
            "output": live.get("switch"),
            "output_state_code_v2": live.get("output_state_code_v2"),
            "fingerprint": self._fingerprint(getattr(adoption, "max_authority", None)),
            "current_authority": self._fingerprint(getattr(adoption, "current_authority", None)),
            "edge_lease": {
                "armed": lease.armed,
                "tripped": lease.tripped,
                "boot_quarantine": lease.boot_quarantine,
                "generation": lease.generation,
                "remaining_s": lease.remaining_s,
                "modbus_age_s": lease.modbus_age_s,
                "ttl_s": self.app.runtime_safety_guard.edge_safety_lease.config.lease_ttl_s,
            },
            "protection": {
                "code": live.get("protection_code"),
                "status": live.get("protection_status"),
                "age_s": live.get("_meta", {}).get("protection_code", {}).get("age_s"),
            },
            "freshness": {
                "output_age_s": live.get("_meta", {}).get("switch", {}).get("age_s"),
                "output_source_key": live.get("_meta", {}).get("switch", {}).get("source_key"),
            },
        }

    async def _enter_hands_off_verified_off(self) -> Dict[str, Any]:
        live = await self._raw_live()
        if not self._is_off(live):
            raise PhysicalTestControlError("HANDS_OFF requires positively confirmed Output OFF")
        manager = self.app.rd_control_mode_manager
        result = await manager.enter_hands_off()
        return {"entered": bool(result), "mode": _enum_value(manager.mode)}

    async def _preview_for_battery(self, battery_id: Any) -> tuple[Any, ManagedAdoptionPreview]:
        if not isinstance(battery_id, str) or not _BATTERY_ID_RE.fullmatch(battery_id):
            raise PhysicalTestControlError("battery_id is invalid")
        record = await get_battery(battery_id)
        if record is None:
            raise PhysicalTestControlError("battery is not present in registry")
        if record.identity.chemistry is BatteryChemistry.CUSTOM:
            raise PhysicalTestControlError("CUSTOM batteries are not allowed")

        manager = self.app.rd_control_mode_manager
        if not manager.hands_off:
            raise PhysicalTestControlError("D061 adoption requires durable/in-memory HANDS_OFF")
        live = await self._raw_live()
        if not self._is_on(live):
            raise PhysicalTestControlError("D061 adoption requires positively confirmed Output ON")

        coordinator = self.app.rd_managed_live_adoption
        fingerprint_fn = getattr(coordinator, "fingerprint_from_live", None)
        adopt = getattr(coordinator, "adopt", None)
        if not callable(fingerprint_fn) or not callable(adopt):
            raise PhysicalTestControlError("D061 coordinator unavailable")
        fingerprint = fingerprint_fn(live)
        if fingerprint is None:
            raise PhysicalTestControlError("D061 live fingerprint is unavailable")

        preview = ManagedAdoptionPreview(
            token=f"physical-test:{uuid.uuid4().hex}",
            battery_id=record.identity.battery_id,
            chemistry=record.identity.chemistry,
            capacity_ah=record.identity.nominal_capacity_ah,
            fingerprint=fingerprint,
        )
        return coordinator, preview

    async def _adopt_battery(self, battery_id: Any) -> Dict[str, Any]:
        coordinator, preview = await self._preview_for_battery(battery_id)
        result = await coordinator.adopt(preview)
        return {
            "adopted": bool(result),
            "battery_id": preview.battery_id,
            "authority": self._fingerprint(getattr(coordinator, "current_authority", None)),
        }

    async def _verified_stop(self) -> Dict[str, Any]:
        coordinator = self.app.rd_managed_live_adoption
        if not bool(getattr(coordinator, "active", False)):
            raise PhysicalTestControlError("d061_verified_stop requires active adopted Manual authority")
        stop = getattr(coordinator, "verified_stop", None)
        if not callable(stop):
            raise PhysicalTestControlError("D061 verified-stop API unavailable")
        result = await stop()
        live = await self._raw_live()
        if not self._is_off(live):
            raise PhysicalTestControlError("verified stop did not confirm Output OFF")
        return {"stopped": bool(result), "output": live.get("switch")}

    async def _fault_toctou_precommand(self, battery_id: Any) -> Dict[str, Any]:
        """Inject a synthetic second-read fingerprint change before edge command.

        No hardware value is written. The existing coordinator must reject the changed
        readback while ``command_may_have_executed`` is still false, preserve the
        external HANDS_OFF Output, and leave edge generation unchanged.
        """

        coordinator, preview = await self._preview_for_battery(battery_id)
        edge = getattr(coordinator, "edge", None)
        lease = getattr(edge, "lease", None)
        if edge is None or lease is None:
            raise PhysicalTestControlError("D061 edge adoption boundary unavailable")
        before = await lease.read_state()
        guard = coordinator.guard
        original_raw = guard._raw_live
        read_count = 0

        async def injected_raw_live() -> Dict[str, Any]:
            nonlocal read_count
            live = await original_raw()
            read_count += 1
            if read_count == 2:
                mutated = dict(live)
                try:
                    mutated["set_voltage"] = max(0.1, float(live["set_voltage"]) - 0.20)
                except (KeyError, TypeError, ValueError) as exc:
                    raise PhysicalTestControlError(
                        "cannot inject deterministic TOCTOU fingerprint"
                    ) from exc
                return mutated
            return live

        guard._raw_live = injected_raw_live
        try:
            try:
                await coordinator.adopt(preview)
            except Exception as exc:
                if bool(getattr(edge, "command_may_have_executed", False)):
                    raise PhysicalTestControlError(
                        "TOCTOU injection crossed the edge-command boundary"
                    ) from exc
                after = await lease.read_state()
                live_after = await original_raw()
                if int(after.generation) != int(before.generation):
                    raise PhysicalTestControlError(
                        "TOCTOU injection changed edge generation before command"
                    ) from exc
                if not self._is_on(live_after):
                    raise PhysicalTestControlError(
                        "TOCTOU pre-command rejection did not preserve external Output ON"
                    ) from exc
                return {
                    "rejected": True,
                    "reason": f"{type(exc).__name__}: {exc}",
                    "command_may_have_executed": False,
                    "generation_before": before.generation,
                    "generation_after": after.generation,
                    "output": live_after.get("switch"),
                    "hardware_writes_injected": 0,
                }
            raise PhysicalTestControlError("TOCTOU injection unexpectedly completed adoption")
        finally:
            guard._raw_live = original_raw

    async def _fault_ambiguous_edge_ack(self, battery_id: Any) -> Dict[str, Any]:
        """Send the real edge adopt command, then hide only its ACK readback window.

        The original edge command is issued. For exactly the configured positive-ACK
        reads, the lease returns the pre-command snapshot. The coordinator therefore
        enters its existing ambiguous-command verified-OFF containment. The wrapper is
        exhausted before containment disarm readback, so OFF/lease confirmation remains
        real rather than synthetic.
        """

        coordinator, preview = await self._preview_for_battery(battery_id)
        edge = getattr(coordinator, "edge", None)
        lease = getattr(edge, "lease", None)
        if edge is None or lease is None:
            raise PhysicalTestControlError("D061 edge adoption boundary unavailable")

        before = await lease.read_state()
        original_press = lease._press
        original_read_state = lease.read_state
        command_sent = False
        hidden_reads = 0

        async def injected_press(entity_id: str) -> bool:
            nonlocal command_sent, hidden_reads
            accepted = bool(await original_press(entity_id))
            if entity_id == edge.config.entity and accepted:
                command_sent = True
                hidden_reads = max(1, int(lease.config.ack_attempts))
            return accepted

        async def injected_read_state() -> Any:
            nonlocal hidden_reads
            if command_sent and hidden_reads > 0:
                hidden_reads -= 1
                return before
            return await original_read_state()

        lease._press = injected_press
        lease.read_state = injected_read_state
        try:
            try:
                await coordinator.adopt(preview)
            except Exception as exc:
                if not command_sent or not bool(getattr(edge, "command_may_have_executed", False)):
                    raise PhysicalTestControlError(
                        "ambiguous-ACK injection did not cross the edge-command boundary"
                    ) from exc
                live_after = await self._raw_live()
                lease_after = await original_read_state()
                if not self._is_off(live_after):
                    raise PhysicalTestControlError(
                        "ambiguous edge ACK did not complete verified-OFF containment"
                    ) from exc
                return {
                    "contained": True,
                    "reason": f"{type(exc).__name__}: {exc}",
                    "command_may_have_executed": True,
                    "generation_before": before.generation,
                    "generation_after": lease_after.generation,
                    "lease_armed": lease_after.armed,
                    "remaining_s": lease_after.remaining_s,
                    "output": live_after.get("switch"),
                }
            raise PhysicalTestControlError("ambiguous-ACK injection unexpectedly completed adoption")
        finally:
            lease._press = original_press
            lease.read_state = original_read_state

    async def _fault_raw_protection_unavailable(self) -> Dict[str, Any]:
        """Inject one synthetic raw register-16 availability failure while D061 is active.

        The physical HA protection entity is never altered. The already-installed D061
        renewal gate is forced to fail once, so the normal strict runtime must drive a
        verified Output OFF. The coordinator is then allowed one normal observer cycle
        to retire the now-OFF adopted authority and disarm its lease.
        """

        coordinator = self.app.rd_managed_live_adoption
        if not bool(getattr(coordinator, "active", False)):
            raise PhysicalTestControlError(
                "raw-protection fault injection requires active adopted Manual authority"
            )
        live_before = await self._raw_live()
        if not self._is_on(live_before):
            raise PhysicalTestControlError("raw-protection fault injection requires Output ON")
        edge = getattr(coordinator, "edge", None)
        gate = getattr(edge, "_require_raw_protection_normal", None)
        if edge is None or not callable(gate):
            raise PhysicalTestControlError("D061 raw-protection gate unavailable")

        async def unavailable() -> None:
            raise EdgeSafetyLeaseError(
                "physical-test injected raw RD6018 protection-code unavailable"
            )

        edge._require_raw_protection_normal = unavailable
        caught: Optional[Exception] = None
        try:
            try:
                await coordinator.guard.get_all_live()
            except Exception as exc:
                caught = exc
            if caught is None:
                raise PhysicalTestControlError(
                    "raw-protection injection did not trip strict runtime safety"
                )
        finally:
            edge._require_raw_protection_normal = gate

        # The normal adoption observer owns retirement after an externally/strictly
        # forced OFF. Give its real task one poll interval, then invoke the same public
        # observer method once if it has not yet consumed the OFF transition.
        deadline = asyncio.get_running_loop().time() + float(coordinator.poll_s) + 1.0
        while bool(getattr(coordinator, "active", False)) and asyncio.get_running_loop().time() < deadline:
            await asyncio.sleep(0.25)
        if bool(getattr(coordinator, "active", False)):
            await coordinator.observe_once()

        live_after = await self._raw_live()
        lease_after = await self._lease_state()
        if not self._is_off(live_after):
            raise PhysicalTestControlError(
                "raw-protection fault did not complete verified Output OFF"
            )
        if bool(lease_after.armed):
            raise PhysicalTestControlError(
                "raw-protection fault left edge lease armed after adopted authority retirement"
            )
        return {
            "contained": True,
            "reason": f"{type(caught).__name__}: {caught}",
            "output": live_after.get("switch"),
            "lease_armed": lease_after.armed,
            "remaining_s": lease_after.remaining_s,
            "adoption_state": _enum_value(coordinator.state),
        }


def install_physical_test_control(app: Any) -> PhysicalTestControl:
    """Attach one disabled-by-default controller to the existing app object."""

    existing = getattr(app, "physical_test_control", None)
    if isinstance(existing, PhysicalTestControl):
        return existing
    control = PhysicalTestControl(app)
    app.physical_test_control = control
    return control
