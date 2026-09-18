from __future__ import annotations

from typing import Any, Mapping


def require_mapping(data: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(data, Mapping):
        raise ValueError(f"Invalid {label} configuration: expected a mapping.")
    return data


def require_number(data: Mapping[str, Any], key: str, label: str) -> float:
    value = data.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"Invalid {label} configuration: {key} is required and must be numeric.")
    return float(value)


def validate_rd(data: Mapping[str, Any]) -> dict[str, float]:
    label = "RD6018"
    voltage = require_number(data, "max_voltage_v", label)
    current = require_number(data, "max_current_a", label)
    power = require_number(data, "max_power_w", label)
    if not 0 < voltage <= 60:
        raise ValueError(f"Invalid RD6018 configuration: max_voltage_v={voltage:g}V exceeds allowed hardware range.")
    if not 0 < current <= 18:
        raise ValueError(f"Invalid RD6018 configuration: max_current_a={current:g}A exceeds allowed hardware range.")
    if not 0 < power <= voltage * current:
        raise ValueError(f"Invalid RD6018 configuration: max_power_w={power:g}W exceeds V*I envelope.")
    return {"max_voltage_v": voltage, "max_current_a": current, "max_power_w": power}


def validate_connection(data: Mapping[str, Any], label: str) -> None:
    host = data.get("host")
    port = data.get("port")
    url_env = data.get("url_env")
    host_env = data.get("host_env")
    port_env = data.get("port_env")
    direct_endpoint = isinstance(host, str) and bool(host.strip()) and isinstance(port, int) and not isinstance(port, bool)
    url_endpoint = isinstance(url_env, str) and bool(url_env.strip())
    split_endpoint = isinstance(host_env, str) and bool(host_env.strip()) and isinstance(port_env, str) and bool(port_env.strip())
    if not (direct_endpoint or url_endpoint or split_endpoint):
        raise ValueError(f"Invalid {label} configuration: connection must use runtime endpoint environment variables.")
    if direct_endpoint and not 1 <= port <= 65535:
        raise ValueError(f"Invalid {label} configuration: connection.port must be 1..65535.")
    for key in ("url_env", "host_env", "port_env"):
        if key in data and (not isinstance(data[key], str) or not data[key].strip()):
            raise ValueError(f"Invalid {label} configuration: {key} must name an environment variable.")
    if split_endpoint and isinstance(port_env, str) and not port_env.strip():
        raise ValueError(f"Invalid {label} configuration: port_env must name an environment variable.")
    for key in ("token_env", "key_env"):
        if key in data and (not isinstance(data[key], str) or not data[key].strip()):
            raise ValueError(f"Invalid {label} configuration: {key} must name an environment variable.")
