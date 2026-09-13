from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

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


def _connection(data: dict[str, Any], label: str) -> ConnectionConfig:
    connection = dict(require_mapping(data.get("connection"), label))
    validate_connection(connection, label)
    return ConnectionConfig(
        connection["host"], connection["port"], connection.get("token_env"),
        connection.get("key_env"), bool(connection.get("tls", False)), bool(connection.get("encrypted", False)),
    )


def load_config(root: str | Path) -> ConfigBundle:
    base = Path(root)
    transport_data = load_yaml(base / "physical" / "transports.yaml")
    transports = {}
    for name, entry in dict(require_mapping(transport_data.get("transports"), "transports")).items():
        item = dict(require_mapping(entry, f"transport {name}"))
        profile = str(item.get("profile", name))
        profile_data = load_yaml(base / "physical" / f"{profile}.yaml")
        transports[name] = PhysicalTransportConfig(name, str(profile_data["type"]), bool(item.get("enabled", False)), int(item.get("priority", 0)), _connection(profile_data, profile))
    rd_values = validate_rd(load_yaml(base / "physical" / "rd6018.yaml"))
    return ConfigBundle(
        transports, RDConfig(**rd_values), load_yaml(base / "charge" / "recipes.yaml"),
        load_yaml(base / "safety" / "safety_limits.yaml"), load_yaml(base / "runtime" / "runtime.yaml"),
    )
