"""Hard wall-clock callback isolation for detached D061 emergency actions."""
from __future__ import annotations

import os
import pickle
import select
import signal
import time
from typing import Any, Callable


def _close_inherited_fds(keep: int) -> None:
    try:
        names = os.listdir("/proc/self/fd")
    except OSError as exc:
        raise RuntimeError("cannot enumerate inherited descriptors") from exc
    for name in names:
        if name.isdecimal() and int(name) >= 3 and int(name) != keep:
            try:
                os.close(int(name))
            except OSError:
                pass


def _write_all(fd: int, payload: bytes) -> None:
    view = memoryview(payload)
    while view:
        count = os.write(fd, view)
        view = view[count:]


def run_bounded(callback: Callable[[], Any], timeout_s: float, *,
                monotonic: Callable[[], float] = time.monotonic) -> Any:
    """Run a fork-safe callback in a worker killed and reaped at deadline."""
    if timeout_s <= 0:
        raise TimeoutError("no callback wall-clock budget remains")
    read_fd, write_fd = os.pipe()
    deadline = monotonic() + timeout_s
    pid = os.fork()
    if pid == 0:
        try:
            os.close(read_fd)
            _close_inherited_fds(write_fd)
            try:
                message = (True, callback())
            except BaseException as exc:
                message = (False, (type(exc).__name__, str(exc)))
            try:
                payload = pickle.dumps(message, protocol=4)
                _write_all(write_fd, len(payload).to_bytes(8, "big") + payload)
            except BaseException:
                pass
        finally:
            os._exit(0)
    os.close(write_fd)
    payload = bytearray()
    try:
        while monotonic() < deadline:
            wait = max(0.0, deadline - monotonic())
            readable, _, _ = select.select([read_fd], [], [], wait)
            if readable:
                chunk = os.read(read_fd, 65536)
                if not chunk:
                    break
                payload.extend(chunk)
                if len(payload) >= 8 and len(payload) >= 8 + int.from_bytes(payload[:8], "big"):
                    break
        if not payload or len(payload) < 8 or len(payload) < 8 + int.from_bytes(payload[:8], "big"):
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            os.waitpid(pid, 0)
            raise TimeoutError("emergency callback exceeded OS-enforced deadline")
        os.waitpid(pid, 0)
        size = int.from_bytes(payload[:8], "big")
        ok, result = pickle.loads(payload[8:8 + size])
        if not ok:
            name, message = result
            raise RuntimeError(f"emergency callback failed: {name}: {message}")
        return result
    finally:
        os.close(read_fd)


class DeadlineCallbacks:
    """Wrap OFF hooks so each gets only the shared lifecycle budget remaining."""
    def __init__(self, callbacks: dict[str, Callable[[], Any]], *,
                 deadline: float, monotonic: Callable[[], float] = time.monotonic):
        self.callbacks, self.deadline, self.monotonic = callbacks, deadline, monotonic

    def __getattr__(self, name: str) -> Callable[[], Any]:
        callback = self.callbacks[name]
        def invoke() -> Any:
            return run_bounded(callback, self.deadline - self.monotonic(), monotonic=self.monotonic)
        return invoke
