#!/usr/bin/env python3
"""Pinned SSH/host profile helpers for D061. Importing never actuates hardware."""
from __future__ import annotations

import hashlib
import argparse
import io
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tarfile
import tempfile
import time
import uuid

from dotenv import dotenv_values

EVIDENCE = Path(os.environ.get("RD6018_D061_EVIDENCE_PATH", "d061-evidence.json"))
CANDIDATE = Path(os.environ.get("RD6018_D061_CANDIDATE", "__unset_candidate__"))
SECRETS = Path(os.environ.get("RD6018_D061_PROFILE", "__unset_profile__"))
OVERLAY = Path(__file__).resolve().parent / "acceptance_guard"
SHA = "594a386e2b9fdd6bde9ebb15a5dfab30155291d6"
OVERLAY_FILES = ("__init__.py", "guard.py", "adapters.py", "transient.py", "pairing.py")
REMOTE = "node104"
STAGE_ROOT = "/tmp"
SERVICE = "rd6018-bot.service"
PYTHON = "/opt/services/rd6018-bot/venv/bin/python"
PRODUCTION_ENV = "/opt/services/rd6018-bot/.env"


def digest_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def git(*args: str, cwd: Path) -> str:
    return subprocess.check_output(["git", *args], cwd=cwd, text=True,
                                   stderr=subprocess.STDOUT).strip()


def profile_values() -> dict[str, str]:
    if not SECRETS.is_file():
        raise RuntimeError("RD6018_D061_PROFILE is not configured or unavailable")
    raw = {k: str(v) for k, v in dotenv_values(SECRETS).items() if v is not None}
    mapping = {
        "SFTP_HOST": ("SFTP_RD6018_BOT_104_HOST", "SFTP_HOST"),
        "SFTP_PORT": ("SFTP_RD6018_BOT_104_PORT", "SFTP_PORT"),
        "SFTP_USERNAME": ("SFTP_RD6018_BOT_104_USER", "SFTP_USERNAME"),
        "SFTP_HOST_KEY_SHA256": ("SFTP_RD6018_BOT_104_HOST_KEY_SHA256", "SFTP_HOST_KEY_SHA256"),
        "SFTP_KNOWN_HOSTS": ("SFTP_RD6018_BOT_104_KNOWN_HOSTS", "SFTP_KNOWN_HOSTS"),
        "SFTP_KEY_FILENAME": ("SFTP_RD6018_BOT_104_PRIVATE_KEY_PATH", "SFTP_KEY_FILENAME"),
        "SFTP_KEY_PASSPHRASE": ("SFTP_RD6018_BOT_104_KEY_PASSPHRASE", "SFTP_KEY_PASSPHRASE"),
        "SFTP_PASSWORD": ("SFTP_RD6018_BOT_104_PASSWORD", "SFTP_PASSWORD"),
    }
    values = {target: next((raw[key] for key in keys if raw.get(key)), "")
              for target, keys in mapping.items()}
    if not values["SFTP_KNOWN_HOSTS"]:
        values["SFTP_KNOWN_HOSTS"] = str(Path.home() / ".ssh" / "known_hosts")
    required = ("SFTP_HOST", "SFTP_USERNAME", "SFTP_KNOWN_HOSTS")
    missing = [key for key in required if not values.get(key)]
    if missing:
        raise RuntimeError("node104 SFTP profile fields missing: " + ", ".join(missing))
    return values


def connect(profile: dict[str, str]):
    import paramiko
    known_hosts = Path(profile["SFTP_KNOWN_HOSTS"])
    if not known_hosts.is_file():
        raise RuntimeError("configured known_hosts file unavailable")
    client = paramiko.SSHClient()
    client.load_host_keys(str(known_hosts))
    client.set_missing_host_key_policy(paramiko.RejectPolicy())
    kwargs: dict[str, object] = {
        "hostname": profile["SFTP_HOST"],
        "username": profile["SFTP_USERNAME"],
        "port": int(profile.get("SFTP_PORT", "22")),
        "timeout": 20,
        "allow_agent": False,
        "look_for_keys": False,
    }
    if profile.get("SFTP_KEY_FILENAME"):
        kwargs["key_filename"] = profile["SFTP_KEY_FILENAME"]
        if profile.get("SFTP_KEY_PASSPHRASE"):
            kwargs["passphrase"] = profile["SFTP_KEY_PASSPHRASE"]
    elif profile.get("SFTP_PASSWORD"):
        kwargs["password"] = profile["SFTP_PASSWORD"]
    else:
        raise RuntimeError("SFTP profile has no key or password authentication")
    client.connect(**kwargs)
    transport = client.get_transport()
    if transport is None or not transport.is_active():
        client.close()
        raise RuntimeError("SSH transport is not active")
    key = transport.get_remote_server_key()
    pinned = client.get_host_keys().lookup(profile["SFTP_HOST"])
    if not pinned or not any(item.asbytes() == key.asbytes() for item in pinned.values()):
        client.close()
        raise RuntimeError("SSH server host key is not pinned in known_hosts")
    expected = profile.get("SFTP_HOST_KEY_SHA256", "")
    if expected:
        actual = "SHA256:" + __import__("base64").b64encode(hashlib.sha256(key.asbytes()).digest()).decode().rstrip("=")
        if actual != expected:
            client.close()
            raise RuntimeError("SSH server host-key fingerprint mismatch")
    return client


def remote_exec(client, command: str, timeout: int = 180) -> str:
    _stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
    out, err = stdout.read().decode("utf-8", "replace"), stderr.read().decode("utf-8", "replace")
    status = stdout.channel.recv_exit_status()
    combined = out + ("\n[stderr]\n" + err if err else "")
    if status:
        raise RemoteCommandError(status, combined)
    return combined.strip()


class RemoteCommandError(RuntimeError):
    def __init__(self, status: int, output: str):
        super().__init__("remote command exited " + str(status))
        self.status, self.output = status, output


def service_state(client) -> dict[str, str]:
    raw = remote_exec(client, "systemctl show " + shlex.quote(SERVICE) +
                      " -p ActiveState -p MainPID -p NRestarts")
    return dict(line.split("=", 1) for line in raw.splitlines() if "=" in line)
