"""Source-paired Python release profile for the existing D090 transaction owner."""
from __future__ import annotations
import json
import re
from dataclasses import fields
from pathlib import Path
import node104_d090_release as release
from node104_release_admission import classify


def load_software_release_profile(path: Path) -> tuple[release.ReleaseManifest, str, dict]:
    if path.is_symlink() or not path.is_file():
        raise ValueError("release profile must be a regular file")
    obj=json.loads(path.read_text(encoding="utf8"))
    if type(obj) is not dict or set(obj)!={"schema","mode","pin","preimage_inventory_sha256","changed_paths","proof_collector_sha256"}:
        raise ValueError("invalid release profile schema")
    if obj["schema"] != 2 or obj["mode"] != "python_control_change":
        raise ValueError("unknown release profile type")
    raw=obj["pin"]
    names={f.name for f in fields(release.ReleaseManifest)}
    if type(raw) is not dict or set(raw)!=names:
        raise ValueError("release profile has unexpected fields")
    pin=release.ReleaseManifest(**raw)
    if (pin.node!=release.NODE or pin.hostname!=release.HOSTNAME or
        pin.machine_id!=release.MACHINE_ID or pin.service!=release.SERVICE or
        pin.root!=release.ROOT or pin.python!="3.11" or
        pin.firmware!="2.3-ha-canonical" or pin.edge_lease_ttl_s!=900 or
        pin.edge_renewal_s!=300 or pin.old_source_sha==pin.source_sha):
        raise ValueError("release profile node/firmware/lease identity differs")
    sha=re.compile(r"[0-9a-f]{64}\Z")
    inventory=obj["preimage_inventory_sha256"]
    if type(inventory) is not str or not sha.fullmatch(inventory):
        raise ValueError("preimage inventory pin invalid")
    for v in (pin.staging_manifest_sha256,pin.source_archive_sha256,
              pin.service_environment_sha256,pin.systemd_unit_sha256,
              obj["proof_collector_sha256"]):
        if type(v) is not str or not sha.fullmatch(v):
            raise ValueError("release digest pin invalid")
    for v in (pin.old_source_sha,pin.source_sha):
        if type(v) is not str or not re.fullmatch(r"[0-9a-f]{40}",v):
            raise ValueError("source identity is not an exact commit SHA")
    if pin.firmware_digest is not None:
        raise ValueError("Python-only update cannot claim a new firmware artifact")
    changed=obj["changed_paths"]
    if type(changed) is not list or len(changed)!=len(set(changed)):
        raise ValueError("release diff inventory must be unique")
    verdict=classify(changed)
    if verdict.classification!="python_control_change" or verdict.changed_firmware_paths:
        raise ValueError("release contains firmware or lacks control change")
    return pin,inventory,obj
