from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

from .models import ConnectionConfig, PhysicalTransportConfig, RDConfig
from .validation import require_mapping, validate_connection, validate_rd


def load_yaml(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    try:
        with source.open(encoding="utf-8") as handle:
            value = yaml.safe_load(handle)
    except OSError as exc:
        raise ValueError(f"Unable to load configuration {source}: {exc}") from exc
    return dict(require_mapping(value, str(source)))


@dataclass(frozen=True)
class ConfigBundle:
    transports: dict[str, PhysicalTransportConfig]
    rd: RDConfig
    charge: dict[str, Any]
    safety: dict[str, Any]
    runtime: dict[str, Any]
    connectors: dict[str, dict[str, Any]] | None = None
    bench: dict[str, Any] | None = None
    manual: dict[str, Any] | None = None
    default_connector: str = ""


def _connection(data: dict[str, Any], label: str, *, required: bool = True) -> ConnectionConfig:
    connection = dict(require_mapping(data.get("connection"), label))
    if label == "esp128":
        connection["host"] = os.getenv("ESPHOME_API_HOST", connection.get("host", ""))
        raw_port = os.getenv("ESPHOME_API_PORT")
        if raw_port:
            try:
                connection["port"] = int(raw_port)
            except ValueError as exc:
                raise ValueError("ESPHOME_API_PORT must be an integer") from exc
    elif label == "ha102":
        raw_url = os.getenv("HA_URL", "").strip()
        if raw_url:
            parsed = urlparse(raw_url)
            if not parsed.hostname:
                raise ValueError("HA_URL must contain a hostname")
            connection["host"] = parsed.hostname
            connection["port"] = parsed.port or (443 if parsed.scheme == "https" else 80)
            connection["tls"] = parsed.scheme == "https"
    if not required and (not connection.get("host") or not connection.get("port")):
        return ConnectionConfig("", 0, connection.get("token_env"), connection.get("key_env"), bool(connection.get("tls", False)), bool(connection.get("encrypted", False)))
    validate_connection(connection, label)
    return ConnectionConfig(
        connection["host"], connection["port"], connection.get("token_env"),
        connection.get("key_env"), bool(connection.get("tls", False)), bool(connection.get("encrypted", False)),
    )


def load_config(root: str | Path) -> ConfigBundle:
    base = Path(root)
    connector_data = load_yaml(base / "physical" / "connectors.yaml")
    selected_connector = str(connector_data.get("default_connector", ""))
    selected_transport = ""
    selected_definition = dict((connector_data.get("connectors") or {}).get(selected_connector, {}))
    selected_profile = str(selected_definition.get("profile", ""))
    if selected_profile:
        selected_transport = str(load_yaml(base / "physical" / f"{selected_profile}.yaml").get("transport_profile", ""))
    transport_data = load_yaml(base / "physical" / "transports.yaml")
    transports = {}
    for name, entry in dict(require_mapping(transport_data.get("transports"), "transports")).items():
        item = dict(require_mapping(entry, f"transport {name}"))
        profile = str(item.get("profile", name))
        profile_data = load_yaml(base / "physical" / f"{profile}.yaml")
        transports[name] = PhysicalTransportConfig(name, str(profile_data["type"]), bool(item.get("enabled", False)), int(item.get("priority", 0)), _connection(profile_data, profile, required=name == selected_transport), dict(profile_data.get("entities", {})))
    rd_values = validate_rd(load_yaml(base / "physical" / "rd6018.yaml"))
    return ConfigBundle(
        transports, RDConfig(**rd_values), load_yaml(base / "charge" / "recipes.yaml"),
        load_yaml(base / "safety" / "safety_limits.yaml"), load_yaml(base / "runtime" / "runtime.yaml"),
        dict(connector_data.get("connectors", {})),
        load_yaml(base / "physical" / "bench.yaml"),
        load_yaml(base / "charge" / "manual.yaml"),
        str(connector_data.get("default_connector", "")),
    )
