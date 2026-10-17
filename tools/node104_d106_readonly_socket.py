"""D106: query status ONLY on the production-owned physical-test socket.

This module never sends enter/exit or any physical operation. Missing,
non-root-owned, wrong-PID, or permissive socket fails closed.
"""
from __future__ import annotations
import json
import math
import os
from pathlib import Path
import socket
import stat
import struct
from typing import Any

SOCKET = "/run/rd6018-bot-physical-test-control.sock"


class StatusError(RuntimeError):
    pass


def _number(value: Any) -> float:
    if type(value) not in (int, float) or not math.isfinite(value):
        raise StatusError("status missing or invalid numeric value")
    return float(value)


def validate_status(envelope: object) -> dict:
    if (type(envelope) is not dict or envelope.get("ok") is not True
            or envelope.get("operation") != "autonomous_status"
            or type(envelope.get("result")) is not dict):
        raise StatusError("real production autonomous_status receipt required")
    result = envelope["result"]
    required = {"rd_control_mode", "manager_edge_autonomous", "edge_autonomous",
                "output_state_code_v2", "protection_code", "programmed_values",
                "edge_lease", "rd_actuator_writes_injected"}
    if not required.issubset(result):
        raise StatusError("status receipt incomplete")
    if (result["rd_control_mode"] != "pb_managed"
            or result["manager_edge_autonomous"] is not False
            or result["edge_autonomous"] is not False
            or _number(result["output_state_code_v2"]) != 0
            or _number(result["protection_code"]) != 0
            or type(result["rd_actuator_writes_injected"]) is not int
            or result["rd_actuator_writes_injected"] != 0):
        raise StatusError("status disagrees with PB-managed OFF condition")
    values = result["programmed_values"]
    if type(values) is not dict or set(values) != {"set_voltage", "set_current", "ovp", "ocp"}:
        raise StatusError("missing programmed readback")
    set_v, set_i = _number(values["set_voltage"]), _number(values["set_current"])
    ovp, ocp = _number(values["ovp"]), _number(values["ocp"])
    if not (0 <= set_v <= 15.5 and set_i >= 0 and ovp >= set_v
            and ocp >= set_i):
        raise StatusError("unsafe status setpoints")
    lease = result["edge_lease"]
    required_edge = {"armed", "tripped", "boot_quarantine", "remaining_s", "modbus_age_s"}
    if type(lease) is not dict or not required_edge.issubset(lease):
        raise StatusError("status lease fields missing")
    if (lease["armed"] is not False or lease["tripped"] is not False
            or lease["boot_quarantine"] is not False
            or _number(lease["remaining_s"]) != 0
            or not 0 <= _number(lease["modbus_age_s"]) <= 20):
        raise StatusError("status edge lease not disarmed/fresh")
    # This status receipt does not independently prove HA/native sensor state
    # or TTL 900: D091 + D106 read-only observer still must prove those.
    return result


def read_status(*, service_pid: int, path: str = SOCKET) -> dict:
    if type(service_pid) is not int or service_pid <= 1:
        raise StatusError("pinned production service PID required")
    if path != SOCKET:
        raise StatusError("only canonical production socket may be queried")
    sock = Path(path)
    st = sock.lstat()
    if (not stat.S_ISSOCK(st.st_mode) or st.st_uid != 0
            or st.st_mode & 0o777 != 0o600):
        raise StatusError("physical test socket not owned by root with mode 0600")
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as channel:
        channel.settimeout(5.0)
        channel.connect(path)
        pid, uid, _ = struct.unpack("3i", channel.getsockopt(
            socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i")))
        if uid != 0 or pid != service_pid:
            raise StatusError("socket peer does not match single production owner")
        channel.sendall(b'{"op":"autonomous_status"}\n')
        buffer = b""
        while not buffer.endswith(b"\n") and len(buffer) < 8192:
            chunk = channel.recv(4096)
            if not chunk:
                break
            buffer += chunk
        if not buffer.endswith(b"\n") or len(buffer) > 8192:
            raise StatusError("missing/bounded status receipt")
    return validate_status(json.loads(buffer.decode("utf-8")))
