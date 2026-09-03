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
    "d061_fault_toctou_precommand",
    "d061_fault_ambiguous_edge_ack",
    "d061_fault_raw_protection_unavailable",
}
_BATTERY_OPERATIONS = {
    "d061_adopt_battery",
    "d061_fault_toctou_precommand",
    "d061_fault_ambiguous_edge_ack",
}


def request(socket_path: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Send one typed request; this client never imports production managers."""

    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as channel:
        # Fault-injection requests may include bounded OFF confirmation, edge ACK
        # timeout and lease-disarm convergence windows. This is a client timeout only;
        # it does not change any production safety deadline.
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
    parser = argparse.ArgumentParser(description="RD6018 local physical-test control client")
    parser.add_argument("operation", choices=sorted(OPERATIONS))
    parser.add_argument("--battery-id")
    parser.add_argument("--socket", default=DEFAULT_SOCKET)
    args = parser.parse_args()
    payload: dict[str, Any] = {"op": args.operation}
    if args.operation in _BATTERY_OPERATIONS:
        if not args.battery_id:
            parser.error(f"--battery-id is required for {args.operation}")
        payload["battery_id"] = args.battery_id
    elif args.battery_id:
        parser.error("--battery-id is only valid for D061 battery/adoption fault operations")
    print(json.dumps(request(args.socket, payload), ensure_ascii=True, sort_keys=True))


if __name__ == "__main__":
    main()
