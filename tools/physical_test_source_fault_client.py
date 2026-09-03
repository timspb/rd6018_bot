"""Transport-only client for managed source-freshness physical faults."""

from __future__ import annotations

import argparse
import json
import socket
from typing import Any


DEFAULT_SOCKET = "/run/rd6018-bot-physical-test-control.sock"
OPERATIONS = {
    "d061_fault_stale_temp_source",
    "d061_fault_stale_output_source",
    "d061_fault_stale_vout_source",
    "d061_fault_missing_runtime_meta",
    "d062_fault_stale_regulation_source",
}


def request(socket_path: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Send one hard-coded source-fault request; no arbitrary HA fields are accepted."""

    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as channel:
        channel.settimeout(45.0)
        channel.connect(socket_path)
        channel.sendall((json.dumps(payload, ensure_ascii=True) + "\n").encode("utf-8"))
        response = b""
        while not response.endswith(b"\n"):
            chunk = channel.recv(8192)
            if not chunk:
                break
            response += chunk
    value = json.loads(response.decode("utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError("invalid control-plane response")
    return value


def main() -> None:
    parser = argparse.ArgumentParser(
        description="RD6018 local managed source-freshness fault client"
    )
    parser.add_argument("operation", choices=sorted(OPERATIONS))
    parser.add_argument("--socket", default=DEFAULT_SOCKET)
    args = parser.parse_args()
    print(
        json.dumps(
            request(args.socket, {"op": args.operation}),
            ensure_ascii=True,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
