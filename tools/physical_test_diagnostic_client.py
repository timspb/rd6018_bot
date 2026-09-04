"""Transport-only client for deterministic diagnostic physical-test operations."""
from __future__ import annotations

import argparse
import json
import socket
from typing import Any

DEFAULT_SOCKET = "/run/rd6018-bot-physical-test-control.sock"


def request(socket_path: str, operation: str, battery_id: str) -> dict[str, Any]:
    payload = {"op": operation, "battery_id": battery_id}
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as channel:
        channel.settimeout(90.0)
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
    parser = argparse.ArgumentParser(description="RD6018 diagnostic physical-test client")
    parser.add_argument("--socket", default=DEFAULT_SOCKET)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("cancel-after-step", "prepare-restart"):
        item = sub.add_parser(name)
        item.add_argument("--battery-id", required=True)
    args = parser.parse_args()
    operation = (
        "diagnostic_probe_cancel_after_step"
        if args.command == "cancel-after-step"
        else "diagnostic_probe_prepare_restart_window"
    )
    print(json.dumps(request(args.socket, operation, args.battery_id), sort_keys=True))


if __name__ == "__main__":
    main()
