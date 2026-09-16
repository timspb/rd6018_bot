"""Transport-only client for OFF-only AUTONOMOUS physical validation."""
from __future__ import annotations

import argparse
import json
import socket
from typing import Any

DEFAULT_SOCKET = "/run/rd6018-bot-physical-test-control.sock"
OPERATIONS = {
    "status": "autonomous_status",
    "enter": "enter_autonomous_verified_off",
    "exit": "exit_autonomous_verified_off",
}


def request(socket_path: str, operation: str) -> dict[str, Any]:
    payload = {"op": OPERATIONS[operation]}
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as channel:
        channel.settimeout(30.0)
        channel.connect(socket_path)
        channel.sendall((json.dumps(payload) + "\n").encode("utf-8"))
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
        description="RD6018 OFF-only AUTONOMOUS physical-validation client"
    )
    parser.add_argument("operation", choices=tuple(OPERATIONS))
    parser.add_argument("--socket", default=DEFAULT_SOCKET)
    args = parser.parse_args()
    print(
        json.dumps(
            request(args.socket, args.operation),
            ensure_ascii=True,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
