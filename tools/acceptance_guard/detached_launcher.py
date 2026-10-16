"""Opt-in launcher used only by the detached acceptance systemd template."""
from __future__ import annotations

import argparse
import os
import socket
import sys
import time

from .detached import DetachedChild


def _notify(message: str) -> None:
    address = os.environ.get("NOTIFY_SOCKET")
    if not address:
        raise RuntimeError("systemd NOTIFY_SOCKET unavailable")
    if address.startswith("@"):
        address = "\0" + address[1:]
    with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as sock:
        sock.connect(address)
        sock.sendall(message.encode("ascii"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--enable", action="store_true")
    parser.add_argument("child", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    if not args.enable or os.environ.get("D061_ACCEPTANCE_OPT_IN") != "YES_I_HAVE_REVIEWED_BENCH_GATES":
        raise SystemExit("D061 detached acceptance is opt-in and disabled by default")
    child_argv = args.child[1:] if args.child[:1] == ["--"] else args.child
    if not child_argv or any(os.path.basename(part) == "bot.py" for part in child_argv):
        raise SystemExit("an explicit non-production acceptance child command is required")
    owner = DetachedChild()
    child = owner.start(child_argv)
    try:
        _notify("READY=1\nSTATUS=D061 acceptance child running\nWATCHDOG=1")
        watchdog_usec = int(os.environ.get("WATCHDOG_USEC", "0"))
        interval = max(0.2, watchdog_usec / 2_000_000) if watchdog_usec else 1.0
        next_ping = time.monotonic() + interval
        while child.poll() is None:
            if time.monotonic() >= next_ping:
                _notify("WATCHDOG=1")
                next_ping = time.monotonic() + interval
            time.sleep(min(0.1, max(0.01, next_ping - time.monotonic())))
        return owner.join()
    finally:
        if child.poll() is None:
            child.kill()
            child.wait()
        owner.close()


if __name__ == "__main__":
    sys.exit(main())
