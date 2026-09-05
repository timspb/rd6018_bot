"""Transport-only client for D062/D063 physical-test operations."""

from __future__ import annotations

import argparse
import json
import socket
from typing import Any


DEFAULT_SOCKET = "/run/rd6018-bot-physical-test-control.sock"
OPERATIONS = {
    "d063_prior_age",
    "d062_adopt_test_budget",
    "d062_verified_stop",
    "d062_fault_toctou_precommand",
    "d062_fault_ambiguous_edge_ack",
    "d062_test_delta_hold_complete",
}
ADOPTION_OPERATIONS = {
    "d062_adopt_test_budget",
    "d062_fault_toctou_precommand",
    "d062_fault_ambiguous_edge_ack",
}


def request(socket_path: str, payload: dict[str, Any]) -> dict[str, Any]:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as channel:
        # Delta/hold validation may wait for two real HA source heartbeats plus the
        # normal verified-OFF/disarm propagation window. Keep the client transport
        # timeout above that bounded operation without changing production timing.
        channel.settimeout(120.0)
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
        description="RD6018 D062/D063 local physical-test client"
    )
    parser.add_argument("operation", choices=sorted(OPERATIONS))
    parser.add_argument("--battery-id")
    parser.add_argument("--remaining-budget-s", type=float)
    parser.add_argument("--socket", default=DEFAULT_SOCKET)
    args = parser.parse_args()

    payload: dict[str, Any] = {"op": args.operation}
    if args.operation in ADOPTION_OPERATIONS:
        if not args.battery_id:
            parser.error(f"--battery-id is required for {args.operation}")
        if args.remaining_budget_s is None:
            parser.error(f"--remaining-budget-s is required for {args.operation}")
        payload["battery_id"] = args.battery_id
        payload["remaining_budget_s"] = args.remaining_budget_s
    elif args.battery_id is not None or args.remaining_budget_s is not None:
        parser.error(
            "--battery-id/--remaining-budget-s are only valid for D062 adoption/fault operations"
        )

    print(json.dumps(request(args.socket, payload), ensure_ascii=True, sort_keys=True))


if __name__ == "__main__":
    main()
