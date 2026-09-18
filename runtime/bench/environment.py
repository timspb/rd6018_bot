"""Fail-closed validation for the runtime environment of a physical bench run."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping
from urllib.parse import urlparse

from runtime.config import ConfigBundle


BENCH_ROLE_ENV = "RD_ENV_ROLE"
BENCH_ROLES = frozenset({"bench", "test"})


@dataclass(frozen=True)
class BenchEnvironmentValidation:
    allowed: bool
    role: str
    missing_environment: tuple[str, ...]
    reasons: tuple[str, ...]


def validate_bench_environment(
    config: ConfigBundle,
    *,
    environ: Mapping[str, str] | None = None,
    read_only_connectivity: bool = False,
    readback_valid: bool = False,
) -> BenchEnvironmentValidation:
    """Validate mutation prerequisites without opening or changing hardware."""
    env = os.environ if environ is None else environ
    role = str(env.get(BENCH_ROLE_ENV, "")).strip().lower()
    missing: list[str] = []
    reasons: list[str] = []

    if role not in BENCH_ROLES:
        missing.append(BENCH_ROLE_ENV)
        reasons.append("runtime_environment_is_not_explicitly_bench_or_test")

    for transport_name in ("ha102", "esp128"):
        transport = config.transports.get(transport_name)
        if transport is None or not transport.enabled:
            reasons.append(f"required_transport_unavailable:{transport_name}")
            continue
        connection = transport.connection
        if connection.url_env:
            endpoint = str(env.get(connection.url_env, "")).strip()
            if not endpoint:
                missing.append(connection.url_env)
            else:
                parsed = urlparse(endpoint)
                if not parsed.hostname or parsed.port is not None and not 1 <= parsed.port <= 65535:
                    reasons.append(f"runtime_endpoint_invalid:{transport_name}")
        elif connection.host_env or connection.port_env:
            for endpoint_env in (connection.host_env, connection.port_env):
                if endpoint_env and not str(env.get(endpoint_env, "")).strip():
                    missing.append(endpoint_env)
            if connection.host_env and connection.port_env:
                host = str(env.get(connection.host_env, "")).strip()
                raw_port = str(env.get(connection.port_env, "")).strip()
                try:
                    port = int(raw_port)
                except ValueError:
                    port = 0
                if host and not 1 <= port <= 65535:
                    reasons.append(f"runtime_endpoint_invalid:{transport_name}")
        elif not connection.host or not 1 <= connection.port <= 65535:
            reasons.append(f"runtime_endpoint_not_runtime_owned:{transport_name}")
        credential_env = connection.token_env or connection.key_env
        if credential_env and not str(env.get(credential_env, "")).strip():
            missing.append(credential_env)

    bench = config.bench or {}
    required_numeric = ("voltage_margin_v", "current_a", "on_hold_seconds")
    if any(key not in bench for key in required_numeric):
        reasons.append("safe_bench_profile_incomplete")
    else:
        try:
            if float(bench["voltage_margin_v"]) <= 0:
                reasons.append("safe_bench_voltage_margin_invalid")
            if float(bench["current_a"]) <= 0:
                reasons.append("safe_bench_current_invalid")
            if float(bench["on_hold_seconds"]) < 10:
                reasons.append("safe_bench_on_hold_too_short")
        except (TypeError, ValueError):
            reasons.append("safe_bench_profile_non_numeric")

    if not read_only_connectivity:
        reasons.append("read_only_connectivity_not_verified")
    if not readback_valid:
        reasons.append("read_only_hardware_readback_not_verified")

    unique_missing = tuple(dict.fromkeys(missing))
    unique_reasons = tuple(dict.fromkeys(reasons))
    return BenchEnvironmentValidation(
        allowed=not unique_missing and not unique_reasons,
        role=role,
        missing_environment=unique_missing,
        reasons=unique_reasons,
    )


__all__ = [
    "BENCH_ROLE_ENV",
    "BENCH_ROLES",
    "BenchEnvironmentValidation",
    "validate_bench_environment",
]
