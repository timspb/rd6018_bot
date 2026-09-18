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


def _connection(data: dict[str, Any], label: str) -> ConnectionConfig:
    connection = dict(require_mapping(data.get("connection"), label))
    validate_connection(connection, label)
    host = str(connection.get("host", "") or "")
    port = int(connection.get("port", 0) or 0)
    tls = bool(connection.get("tls", False))
    url_env = connection.get("url_env")
    if url_env:
        raw_url = os.getenv(str(url_env), "").strip()
        if raw_url:
            parsed = urlparse(raw_url)
            host = parsed.hostname or ""
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
            tls = parsed.scheme == "https"
    else:
        host_env = connection.get("host_env")
        port_env = connection.get("port_env")
        if host_env:
            host = os.getenv(str(host_env), "").strip()
        if port_env:
            raw_port = os.getenv(str(port_env), "").strip()
            try:
                port = int(raw_port) if raw_port else 0
            except ValueError:
                port = 0
    return ConnectionConfig(
        host, port, connection.get("token_env"), connection.get("key_env"), tls,
        bool(connection.get("encrypted", False)), connection.get("url_env"),
        connection.get("host_env"), connection.get("port_env"),
    )


def load_config(root: str | Path) -> ConfigBundle:
    base = Path(root)
    transport_data = load_yaml(base / "physical" / "transports.yaml")
    transports = {}
    for name, entry in dict(require_mapping(transport_data.get("transports"), "transports")).items():
        item = dict(require_mapping(entry, f"transport {name}"))
        profile = str(item.get("profile", name))
        profile_data = load_yaml(base / "physical" / f"{profile}.yaml")
        transports[name] = PhysicalTransportConfig(name, str(profile_data["type"]), bool(item.get("enabled", False)), int(item.get("priority", 0)), _connection(profile_data, profile), dict(profile_data.get("entities", {})))
    rd_values = validate_rd(load_yaml(base / "physical" / "rd6018.yaml"))
    return ConfigBundle(
        transports, RDConfig(**rd_values), load_yaml(base / "charge" / "recipes.yaml"),
        load_yaml(base / "safety" / "safety_limits.yaml"), load_yaml(base / "runtime" / "runtime.yaml"),
        dict(load_yaml(base / "physical" / "connectors.yaml").get("connectors", {})),
        load_yaml(base / "physical" / "bench.yaml"),
        load_yaml(base / "charge" / "manual.yaml"),
    )
