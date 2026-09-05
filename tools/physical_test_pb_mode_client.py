"""Transport-only client for the verified HANDS_OFF -> PB_MANAGED physical-test transition."""
from __future__ import annotations

import argparse
import json
import socket
from typing import Any

DEFAULT_SOCKET = "/run/rd6018-bot-physical-test-control.sock"
OPERATION = "return_pb_control_verified_off"


def request(socket_path: str) -> dict[str, Any]:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as channel:
        channel.settimeout(30.0)
        channel.connect(socket_path)
        channel.sendall((json.dumps({"op": OPERATION}) + "\n").encode("utf-8"))
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
        description="RD6018 verified HANDS_OFF to PB_MANAGED physical-test client"
    )
    parser.add_argument("--socket", default=DEFAULT_SOCKET)
    args = parser.parse_args()
    print(json.dumps(request(args.socket), ensure_ascii=True, sort_keys=True))


if __name__ == "__main__":
    main()
