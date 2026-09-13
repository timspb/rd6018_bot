from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ConnectionConfig:
    host: str
    port: int
    token_env: str | None = None
    key_env: str | None = None
    tls: bool = False
    encrypted: bool = False


@dataclass(frozen=True)
class PhysicalTransportConfig:
    name: str
    type: str
    enabled: bool
    priority: int
    connection: ConnectionConfig


@dataclass(frozen=True)
class RDConfig:
    max_voltage_v: float
    max_current_a: float
    max_power_w: float
