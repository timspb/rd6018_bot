"""D108 temporary candidate AF_UNIX systemd drop-in, owned by D090 trial.

The production CLI deliberately does not construct this helper yet. The
owner calls install() only after it has stopped the original service and
journaled the trial; cleanup() before the verified old service restart.
No process creation or physical command is performed here.
"""
from __future__ import annotations

import os
import socket as socket_api
from pathlib import Path
import stat
from typing import Callable

CANONICAL_DROPIN_DIR = Path("/etc/systemd/system/rd6018-bot.service.d")
CANONICAL_SOCKET = Path("/run/rd6018-bot-physical-test-control.sock")
DROPIN_NAME = "90-d090-off-only-trial.conf"
DROPIN_BYTES = (
    "[Service]\n"
    'Environment="RD6018_PHYSICAL_TEST_CONTROL=1"\n'
    'Environment="RD6018_PHYSICAL_TEST_SOCKET=/run/rd6018-bot-physical-test-control.sock"\n'
).encode("ascii")


class SocketLeaseError(RuntimeError):
    pass


def _sync(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


class TemporarySocketLease:
    """Own exactly one opt-in drop-in and its stopped candidate's socket.

    offline=True is confined to fake-root tests; the production binding
    requires root, exact systemd dir and exact canonical socket.
    """

    def __init__(self, *, dropin_dir: Path, socket: Path,
                 main_pid: Callable[[], int], daemon_reload: Callable[[], None],
                 offline: bool = False) -> None:
        self.dropin_dir = dropin_dir
        self.socket = socket
        self.main_pid = main_pid
        self.daemon_reload = daemon_reload
        self.offline = offline
        if not offline and (os.geteuid() != 0
                            or dropin_dir != CANONICAL_DROPIN_DIR
                            or socket != CANONICAL_SOCKET):
            raise SocketLeaseError("production socket lease requires pinned root/path")

    @property
    def dropin(self) -> Path:
        return self.dropin_dir / DROPIN_NAME

    def _stopped(self) -> None:
        pid = self.main_pid()
        if type(pid) is not int or pid != 0:
            raise SocketLeaseError("socket mutation requires stopped service")

    def _dir(self) -> None:
        if self.dropin_dir.is_symlink():
            raise SocketLeaseError("drop-in directory symlink")
        if self.dropin_dir.exists():
            if not self.dropin_dir.is_dir() or any(self.dropin_dir.iterdir()):
                raise SocketLeaseError("other systemd drop-ins or non-directory")
        else:
            self.dropin_dir.mkdir(mode=0o700)
            _sync(self.dropin_dir.parent)

    def install(self) -> None:
        self._stopped()
        if self.socket.exists() or self.socket.is_symlink():
            raise SocketLeaseError("pre-existing physical socket not owned by this trial")
        self._dir()
        if self.dropin.exists() or self.dropin.is_symlink():
            raise SocketLeaseError("temporary trial drop-in already exists")
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(self.dropin, flags, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(DROPIN_BYTES)
            stream.flush()
            os.fsync(stream.fileno())
        _sync(self.dropin_dir)
        self.daemon_reload()

    def cleanup(self) -> None:
        self._stopped()
        if self.dropin_dir.is_symlink():
            raise SocketLeaseError("systemd drop-in directory identity changed")
        if self.dropin_dir.exists():
            if (not self.dropin_dir.is_dir()
                    or any(p.name != DROPIN_NAME for p in self.dropin_dir.iterdir())):
                raise SocketLeaseError("unreviewed systemd override appeared during trial")
        if self.dropin.is_symlink():
            raise SocketLeaseError("temporary drop-in is a symlink")
        if not self.dropin.exists():
            if self.socket.exists() or self.socket.is_symlink():
                raise SocketLeaseError("unowned socket remains after drop-in lost")
            # Crash may have removed our drop-in but failed before daemon-
            # reload. Re-running reload is mandatory before old bot restart.
            self.daemon_reload()
            return
        st = self.dropin.stat()
        owner = os.geteuid() if self.offline else 0
        if (not stat.S_ISREG(st.st_mode) or st.st_uid != owner
                or st.st_mode & 0o777 != 0o600
                or self.dropin.read_bytes() != DROPIN_BYTES):
            raise SocketLeaseError("temporary drop-in bytes/permissions are not owned")
        if self.socket.exists() or self.socket.is_symlink():
            ss = self.socket.lstat()
            if (not stat.S_ISSOCK(ss.st_mode) or ss.st_uid != owner
                    or ss.st_mode & 0o777 != 0o600):
                raise SocketLeaseError("unknown, unsafe, or forged physical socket")
            # A socket inode may survive after the candidate stopped. Only
            # an unbound stale inode is removable. Never unlink another
            # process's still-listening AF_UNIX socket even if its mode matches.
            with socket_api.socket(socket_api.AF_UNIX, socket_api.SOCK_STREAM) as probe:
                probe.settimeout(0.25)
                try:
                    probe.connect(str(self.socket))
                except ConnectionRefusedError:
                    pass
                except FileNotFoundError:
                    pass
                else:
                    raise SocketLeaseError("physical socket still has a live listener")
            if self.socket.exists():
                self.socket.unlink()
                _sync(self.socket.parent)
        self.dropin.unlink()
        _sync(self.dropin_dir)
        self.daemon_reload()
