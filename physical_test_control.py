"""Local-only physical validation control plane.

The server is deliberately small and disabled by default.  It runs in the
production bot event loop and delegates every stateful operation to the
already-installed production managers/coordinator.  A separate client can
only submit the typed operations defined below over a filesystem-protected
Unix-domain socket.
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


class PhysicalTestControlError(RuntimeError):
    """A request was rejected without changing production state."""


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
        if not isinstance(operation, str) or operation not in _OPS:
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
                else:
                    self._require_fields(request, {"op"})
                    result = await self._verified_stop()
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
        return live.get("switch") == "on" and float(live.get("output_state_code_v2")) == 1.0

    @staticmethod
    def _is_off(live: Dict[str, Any]) -> bool:
        return live.get("switch") == "off" and float(live.get("output_state_code_v2")) == 0.0

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

    async def _adopt_battery(self, battery_id: Any) -> Dict[str, Any]:
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
        result = await adopt(preview)
        return {
            "adopted": bool(result),
            "battery_id": record.identity.battery_id,
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


def install_physical_test_control(app: Any) -> PhysicalTestControl:
    """Attach one disabled-by-default controller to the existing app object."""

    existing = getattr(app, "physical_test_control", None)
    if isinstance(existing, PhysicalTestControl):
        return existing
    control = PhysicalTestControl(app)
    app.physical_test_control = control
    return control
