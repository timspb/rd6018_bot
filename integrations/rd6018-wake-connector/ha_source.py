"""Strict read-only Home Assistant source for the standalone Wake connector."""
from __future__ import annotations

import json
import math
import os
import re
import ssl
import stat
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType
from typing import Any, Protocol

URL_ENV = "RD6018_WAKE_HA_URL"
TOKEN_ENV = "RD6018_WAKE_HA_TOKEN"
MAX_RESPONSE_BYTES = 65536
MAX_SESSION_BYTES = 65536
DEFAULT_SESSION_MAX_AGE_S = 86400
HTTP_TIMEOUT_S = 5.0
ENTITY_RE = re.compile(r"^(sensor|binary_sensor)\.[a-z0-9_]+$")
_ENTITY_KEYS = {
    "voltage": "voltage", "current": "current", "temperature_internal": "temp_int",
    "temperature_external": "temp_ext", "battery_voltage": "battery_voltage",
    "input_voltage": "input_voltage", "output_state": "output_state",
    "configured_voltage": "configured_voltage", "configured_current": "configured_current",
    "ovp": "ovp", "ocp": "ocp", "protection_code": "protection_code",
    "regulation_code": "regulation_code", "autonomous_mode": "autonomous_mode",
}
_PAYLOAD_KEYS = {
    "voltage": "voltage_v", "current": "current_a", "temperature_internal": "temperature_internal_c",
    "temperature_external": "temperature_external_c", "battery_voltage": "battery_voltage_v",
    "input_voltage": "input_voltage_v", "configured_voltage": "configured_voltage_v",
    "configured_current": "configured_current_a", "ovp": "ovp_v", "ocp": "ocp_a",
}
_SAFE_STAGE = {"Main Charge", "Mix Mode", "Десульфатация", "Охлаждение",
               "Безопасное ожидание", "Подготовка", "Done"}
_SAFE_PROFILES = {"EFB", "CA/CA", "AGM", "GEL", "OTHER"}
_GUARD_FAULT_PREFIXES = (
    "ambiguous_or_wrong_proposal_ack", "proposal_ack_timeout", "stale_readback",
    "invalid_", "missing_or_invalid_readback", "programmed_current_readback_mismatch",
    "desulfation_return_", "new_main_epoch_", "clock_rollback",
)


class SourceError(ValueError):
    """Safe, credential-free source failure."""


@dataclass(frozen=True)
class HAConfig:
    base_url: str
    token: str

    @classmethod
    def from_env(cls, environ: dict[str, str] | None = None) -> "HAConfig":
        env = os.environ if environ is None else environ
        url, token = env.get(URL_ENV), env.get(TOKEN_ENV)
        if (not isinstance(url, str) or not url or not isinstance(token, str) or not token
                or token != token.strip() or any(ord(ch) < 33 or ord(ch) > 126 for ch in token)
                or len(token) > 4096):
            raise SourceError("dedicated read-only HA credentials are unavailable")
        try:
            parsed = urllib.parse.urlsplit(url)
            port = parsed.port
        except ValueError:
            raise SourceError("HA base URL is invalid") from None
        if (any(ord(ch) <= 32 or ord(ch) > 126 for ch in url)
                or parsed.scheme not in {"https", "http"} or not parsed.hostname or parsed.username
                or parsed.password or parsed.query or parsed.fragment or parsed.path not in {"", "/"}
                or (port is not None and not 1 <= port <= 65535)):
            raise SourceError("HA base URL is invalid")
        return cls(url.rstrip("/"), token)


def load_entity_allowlist(ha_yaml: Path) -> dict[str, str]:
    """Read only the entities block from canonical ha102 YAML, without YAML execution."""
    try:
        text = Path(ha_yaml).read_text(encoding="utf-8")
    except OSError:
        raise SourceError("canonical HA entity configuration unavailable") from None
    entities: dict[str, str] = {}
    active = False
    for line in text.splitlines():
        if line == "entities:":
            active = True
            continue
        if active and line and not line[0].isspace() and not line.lstrip().startswith("#"):
            break
        if active:
            match = re.fullmatch(r"  ([a-z][a-z0-9_]*):\s*([a-z0-9_.]+)\s*", line)
            if match:
                key, entity = match.groups()
                if key in _ENTITY_KEYS.values() and ENTITY_RE.fullmatch(entity):
                    entities[key] = entity
    missing = set(_ENTITY_KEYS.values()) - set(entities)
    if missing:
        raise SourceError("canonical HA sensor allowlist is incomplete")
    selected = {field: entities[key] for field, key in _ENTITY_KEYS.items()}
    if len(set(selected.values())) != len(selected):
        raise SourceError("canonical HA sensor allowlist contains duplicate entity IDs")
    return selected


class GetTransport(Protocol):
    def get(self, url: str, headers: dict[str, str], timeout: float,
            context: ssl.SSLContext, max_bytes: int) -> bytes: ...


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class UrllibGetTransport:
    def get(self, url: str, headers: dict[str, str], timeout: float,
            context: ssl.SSLContext, max_bytes: int) -> bytes:
        request = urllib.request.Request(url, headers=headers, method="GET")
        try:
            opener = urllib.request.build_opener(
                _NoRedirect(), urllib.request.HTTPSHandler(context=context))
            with opener.open(request, timeout=timeout) as response:
                length = response.headers.get("Content-Length")
                if length is not None and int(length) > max_bytes:
                    raise SourceError("HA response exceeded size limit")
                body = response.read(max_bytes + 1)
        except SourceError:
            raise
        except (OSError, urllib.error.URLError, ValueError):
            raise SourceError("HA read request failed") from None
        if len(body) > max_bytes:
            raise SourceError("HA response exceeded size limit")
        return body


_SNAPSHOT_SEAL = object()


@dataclass(frozen=True)
class SourceSnapshot:
    """Adapter-attested, sanitized values; never constructed from arbitrary source labels."""
    captured_at: float
    values: Any
    freshness_known: bool
    freshness_s: float | None
    _seal: object = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "values", MappingProxyType(dict(self.values)))

    @property
    def provenance(self) -> str:
        return "ha102_rest_read_only_adapter" if self._seal is _SNAPSHOT_SEAL else "untrusted"

    @classmethod
    def _from_adapter(cls, captured_at: float, values: dict[str, Any],
                      freshness_known: bool, freshness_s: float | None) -> "SourceSnapshot":
        return cls(captured_at, values, freshness_known, freshness_s, _SNAPSHOT_SEAL)


class HAReadOnlyClient:
    def __init__(self, config: HAConfig, entities: dict[str, str], *,
                 transport: GetTransport | None = None, timeout_s: float = HTTP_TIMEOUT_S,
                 max_response_bytes: int = MAX_RESPONSE_BYTES,
                 session_path: Path = Path("/var/lib/rd6018-bot/charge_session.json"),
                 session_max_age_s: int = DEFAULT_SESSION_MAX_AGE_S):
        if not 1 <= timeout_s <= 30 or not 1024 <= max_response_bytes <= MAX_RESPONSE_BYTES:
            raise ValueError("HA client limits are invalid")
        if (not entities or any(type(v) is not str or not ENTITY_RE.fullmatch(v) for v in entities.values())
                or len(set(entities.values())) != len(entities)):
            raise ValueError("HA entity allowlist must contain unique sensor-domain IDs")
        if set(entities) != set(_ENTITY_KEYS):
            raise ValueError("HA entity allowlist does not match the read-only schema")
        self.config, self.entities = config, dict(entities)
        self.session_path = Path(session_path)
        if type(session_max_age_s) is not int or not 60 <= session_max_age_s <= 604800:
            raise ValueError("session metadata age limit is invalid")
        self.session_max_age_s = session_max_age_s
        self.transport = transport or UrllibGetTransport()
        self.timeout_s, self.max_response_bytes = timeout_s, max_response_bytes

    def _read_state(self, entity_id: str) -> dict[str, Any]:
        if entity_id not in self.entities.values() or not ENTITY_RE.fullmatch(entity_id):
            raise SourceError("entity is outside the read-only allowlist")
        url = self.config.base_url + "/api/states/" + urllib.parse.quote(entity_id, safe=".")
        raw = self.transport.get(url, {"Authorization": "Bearer " + self.config.token,
                                       "Accept": "application/json"}, self.timeout_s,
                                ssl.create_default_context(), self.max_response_bytes)
        if type(raw) is not bytes or len(raw) > self.max_response_bytes:
            raise SourceError("HA response exceeded size limit")
        try:
            data = json.loads(raw)
        except (TypeError, ValueError):
            raise SourceError("HA returned invalid state data") from None
        if type(data) is not dict or data.get("entity_id") != entity_id or type(data.get("attributes")) is not dict:
            raise SourceError("HA state identity is invalid")
        return data

    def read_snapshot(self, *, now: float | None = None) -> SourceSnapshot:
        now = time.time() if now is None else now
        values: dict[str, Any] = {}
        latest_reported: list[float] = []
        for field, entity in self.entities.items():
            state = self._read_state(entity)
            raw_state = state.get("state")
            parsed: Any = raw_state
            if field in {"voltage", "current", "temperature_internal", "temperature_external",
                         "battery_voltage", "input_voltage", "configured_voltage", "configured_current", "ovp", "ocp"}:
                if type(raw_state) is not str:
                    continue
                try:
                    parsed = float(raw_state)
                except (TypeError, ValueError):
                    continue
                if not math.isfinite(parsed):
                    continue
                limits = {
                    "voltage": (0.0, 70.0), "current": (-1.0, 25.0),
                    "temperature_internal": (-40.0, 150.0), "temperature_external": (-40.0, 150.0),
                    "battery_voltage": (0.0, 70.0), "input_voltage": (0.0, 100.0),
                    "configured_voltage": (0.0, 70.0), "configured_current": (0.0, 25.0),
                    "ovp": (0.0, 75.0), "ocp": (0.0, 25.0),
                }
                low, high = limits[field]
                if not low <= parsed <= high:
                    continue
            elif field == "output_state":
                if type(raw_state) is not str or not re.fullmatch(
                        r"(?:[0-9]{1,3}|on|off)", raw_state, re.IGNORECASE):
                    continue
                parsed = raw_state.lower()
            elif field == "autonomous_mode":
                if type(raw_state) is not str or raw_state not in {"on", "off"}:
                    continue
                parsed = raw_state == "on"
            else:
                if type(raw_state) is not str or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,32}", raw_state):
                    continue
                parsed = raw_state
            output_key = "output_state_code" if field == "output_state" else _PAYLOAD_KEYS.get(field, field)
            values[output_key] = parsed
            reported = _parse_time(state.get("last_reported"))
            # Older HA releases may lack last_reported; last_updated is a deliberately
            # conservative fallback and is explicitly marked as fallback evidence.
            if reported is None:
                reported = _parse_time(state.get("last_updated"))
            if reported is not None and reported <= now + 5:
                latest_reported.append(reported)
        required = {"voltage_v", "current_a", "temperature_internal_c",
                    "temperature_external_c", "output_state_code"}
        if not required.issubset(values):
            raise SourceError("HA core telemetry set is incomplete")
        freshness_known = len(latest_reported) == len(self.entities)
        freshness = max(0.0, now - min(latest_reported)) if freshness_known else None
        values["freshness_known"] = freshness_known
        if freshness_known and freshness is not None:
            values["freshness_s"] = freshness
        values.update(_read_session_metadata(self.session_path, now, self.session_max_age_s))
        return SourceSnapshot._from_adapter(now, values, freshness_known, freshness)


def _parse_time(value: Any) -> float | None:
    if type(value) is not str:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return None
        return parsed.astimezone(timezone.utc).timestamp()
    except ValueError:
        return None


def _read_session_metadata(path: Path, now: float | None = None,
                           max_age_s: int = DEFAULT_SESSION_MAX_AGE_S) -> dict[str, Any]:
    fd = None
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        info = os.fstat(fd)
        now = time.time() if now is None else now
        age = now - info.st_mtime
        if (not stat.S_ISREG(info.st_mode) or info.st_size > MAX_SESSION_BYTES
                or age < -5 or age > max_age_s):
            return {}
        with os.fdopen(fd, "rb") as stream:
            fd = None
            data = stream.read(MAX_SESSION_BYTES + 1)
        if len(data) > MAX_SESSION_BYTES:
            return {}
        document = json.loads(data)
    except (OSError, ValueError, TypeError):
        return {}
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
    if type(document) is not dict:
        return {}
    result: dict[str, Any] = {}
    stage = document.get("stage")
    if type(stage) is str and stage in _SAFE_STAGE:
        result["stage"] = stage
        stage_start = document.get("stage_start_time")
        if type(stage_start) in (float, int) and math.isfinite(stage_start) and stage_start > 0:
            result["stage_occurrence_at"] = float(stage_start)
    raw_profile = document.get("profile")
    profile = raw_profile.strip().upper() if type(raw_profile) is str else ""
    if profile in _SAFE_PROFILES:
        result["profile"] = profile
    journal = document.get("main_current_guard_v1")
    if (type(journal) is dict and type(journal.get("journal_schema")) is int
            and journal.get("journal_schema") == 1 and type(journal.get("revision")) is int
            and type(journal.get("snapshot")) is dict):
        if "fault" in journal["snapshot"]:
            fault = journal["snapshot"].get("fault")
            fault_code = fault.get("code") if type(fault) is dict else fault
            if fault is None or fault_code == "":
                result["guard_state"] = "ok"
            elif type(fault_code) is str:
                result["guard_state"] = "fault"
                result["fault_code"] = (
                    "guard_readback_fault" if "readback" in fault_code else
                    "guard_timeout" if "timeout" in fault_code else
                    "guard_validation_fault" if any(fault_code.startswith(p) for p in _GUARD_FAULT_PREFIXES)
                    else "guard_fault"
                )
    return result
