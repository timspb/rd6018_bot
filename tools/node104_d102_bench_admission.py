"""D102 new-source bench readiness audit (read-only; never a release permit).

This verifier independently pins the accepted D101 source candidate and reports
remaining physical evidence. It cannot run hardware, approve a trial, or bypass
D090. D090 retains sole ownership of production activation and rollback.
"""
from __future__ import annotations

from dataclasses import dataclass
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import tarfile
from typing import Any

from node104_d090_release import REQUIRED_BENCH_CASES

@dataclass(frozen=True)
class SourcePin:
    commit: str
    archive_sha256: str
    manifest_sha256: str

REVIEWED_SOURCE = SourcePin(
    "b44476bcd19dbf0f4ac955634f02a4a7f9e51ddc",
    "89bb7a891c590fcd72eeb14fedd6e8405690528b627ff9ce56b91a7a91781294",
    "bebb447abf423ab3295866d95990fd2b575164dd716555f69201f9403d7e5c76",
)

class AdmissionError(RuntimeError):
    pass

def sha256(path: Path) -> str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""):h.update(chunk)
    return h.hexdigest()

def _safe_relative(raw: str) -> bool:
    if not isinstance(raw,str) or not raw:
        return False
    path=PurePosixPath(raw)
    return (not path.is_absolute() and ".." not in path.parts
            and "\\" not in raw)

def verify_source(stage: Path, *, pin: SourcePin=REVIEWED_SOURCE) -> dict[str, Any]:
    stage=Path(stage)
    if not stage.is_dir() or stage.is_symlink():
        raise AdmissionError("stage is not an ordinary directory")
    manifest=stage/"RELEASE_MANIFEST.json"
    archive=stage/"source.tar"
    tree=stage/"tree"
    if any(p.is_symlink() or not p.is_file() for p in (manifest,archive)):
        raise AdmissionError("manifest or source archive missing/unsafe")
    if tree.is_symlink() or not tree.is_dir():
        raise AdmissionError("staged source tree missing/unsafe")
    if sha256(manifest)!=pin.manifest_sha256 or sha256(archive)!=pin.archive_sha256:
        raise AdmissionError("staged source bytes disagree with reviewed immutable pins")
    obj=json.loads(manifest.read_text(encoding="utf8"))
    if obj.get("source_sha")!=pin.commit or obj.get("archive_sha256")!=pin.archive_sha256:
        raise AdmissionError("source identity mismatch")
    rows=obj.get("files")
    if not isinstance(rows,list) or not rows:
        raise AdmissionError("no source file inventory")
    by_name={}
    for row in rows:
        if (not isinstance(row,dict) or not _safe_relative(row.get("path"))
            or type(row.get("size")) is not int or row["size"]<0
            or not isinstance(row.get("sha256"),str) or len(row["sha256"])!=64
            or row["path"] in by_name):
            raise AdmissionError("invalid/duplicate staged inventory row")
        by_name[row["path"]]=row
    seen=set()
    with tarfile.open(archive,"r:") as source:
        for member in source:
            if not _safe_relative(member.name):
                raise AdmissionError("unsafe source archive path")
            if member.isdir():continue
            if not member.isfile() or member.name in seen or member.name not in by_name:
                raise AdmissionError("unsupported, unexpected or repeated archive member")
            seen.add(member.name)
            row=by_name[member.name]
            stream=source.extractfile(member)
            if stream is None or member.size!=row["size"]:
                raise AdmissionError("source archive file size mismatch")
            if hashlib.sha256(stream.read()).hexdigest()!=row["sha256"]:
                raise AdmissionError("source archive checksum mismatch")
    if seen!=set(by_name):
        raise AdmissionError("archive and manifest disagree")
    found=set()
    for path in tree.rglob("*"):
        if path.is_symlink() or not (path.is_dir() or path.is_file()):
            raise AdmissionError("unsafe object in extracted tree")
        if path.is_file():
            rel=path.relative_to(tree).as_posix()
            if rel not in by_name or sha256(path)!=by_name[rel]["sha256"]:
                raise AdmissionError("extracted tree differs from immutable archive")
            found.add(rel)
    if found!=seen:
        raise AdmissionError("extracted tree file set differs")
    return {"commit":pin.commit,"archive_sha256":pin.archive_sha256,
            "manifest_sha256":pin.manifest_sha256,"verified_source_files":len(seen)}

def readiness(stage: Path, *, pin: SourcePin=REVIEWED_SOURCE) -> dict[str, Any]:
    source=verify_source(stage,pin=pin)
    return {
        "schema":1,
        "review_stage":"D102",
        "status":"SOURCE_ONLY_PASS_PHYSICAL_ADMISSION_OPEN",
        "source":source,
        "physical_case_status":{name:"OPEN_EXACT_SOURCE_FIRMWARE_EVIDENCE_MISSING"
                                for name in REQUIRED_BENCH_CASES},
        "firmware_binary_sha256_status":"NOT_PROVEN_FOR_INSTALLED_ESP",
        "reviewed_physical_signer_status":"NOT_CONFIGURED",
        "d097_production_enter_exit_status":"OPEN_NOT_EXECUTED_ON_NEW_PRODUCTION",
        "d090_source_pins_match":False,
        "production_activation_authorized":False,
        "physical_trial_authorized_by_this_report":False,
        "important":"Software and source-integrity verification cannot replace signed exact-source physical bench evidence.",
    }

def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage",type=Path)
    parser.add_argument("--output",type=Path)
    args=parser.parse_args()
    try:
        value=readiness(args.stage)
    except (AdmissionError, OSError, ValueError, tarfile.TarError) as exc:
        print(json.dumps({"status":"SOURCE_INVALID", "error":str(exc)},sort_keys=True))
        return 2
    serial=json.dumps(value,indent=2,sort_keys=True)+"\n"
    if args.output:args.output.write_text(serial,encoding="utf8")
    print(serial,end="")
    return 0

if __name__=="__main__":raise SystemExit(main())
