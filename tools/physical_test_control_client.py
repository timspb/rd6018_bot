"""Minimal AF_UNIX client for the opt-in in-process physical-test control plane."""

from __future__ import annotations

import argparse
import json
import socket
from typing import Any


DEFAULT_SOCKET = "/run/rd6018-bot-physical-test-control.sock"
OPERATIONS = {
    "status",
    "enter_hands_off_verified_off",
    "d061_verified_stop",
    "d061_adopt_battery",
}


def request(socket_path: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Send one typed request; this client never imports production managers."""

    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as channel:
        channel.settimeout(15.0)
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
    parser = argparse.ArgumentParser(description="RD6018 local physical-test control client")
    parser.add_argument("operation", choices=sorted(OPERATIONS))
    parser.add_argument("--battery-id")
    parser.add_argument("--socket", default=DEFAULT_SOCKET)
    args = parser.parse_args()
    payload: dict[str, Any] = {"op": args.operation}
    if args.operation == "d061_adopt_battery":
        if not args.battery_id:
            parser.error("--battery-id is required for d061_adopt_battery")
        payload["battery_id"] = args.battery_id
    elif args.battery_id:
        parser.error("--battery-id is only valid for d061_adopt_battery")
    print(json.dumps(request(args.socket, payload), ensure_ascii=True, sort_keys=True))


if __name__ == "__main__":
    main()
