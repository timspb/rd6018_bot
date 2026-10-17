"""Turn a pinned D103 source-only tar into a D105 review stage; never deploy.

This pure file builder does not contact node104, HA, ESP, systemd or Telegram.
Only the D090 transaction owner can use the resulting immutable stage.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import tarfile
import uuid

import sys
TOOLS_DIR = str(Path(__file__).resolve().parent)
if TOOLS_DIR not in sys.path:
    sys.path.insert(0, TOOLS_DIR)
from node104_d102_bench_admission import AdmissionError, SourcePin, verify_source

D103_SHA = "b3cd0174a2918dbbc2ee3f9c908fa14d15089a29"
D103_SOURCE_MANIFEST_SHA256 = "665a12dbd6f216740be182a61c5a842419d4cbf7c4ab0b40abcb4cb2ef94c17f"
D103_SOURCE_TAR_SHA256 = "410af38f6a8ec059560aa1bc351b00a572a96121c3d93a216cbe86a433e84ae4"


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for data in iter(lambda:f.read(1024*1024), b""):
            h.update(data)
    return h.hexdigest()


def safe_member(name: str) -> bool:
    if not isinstance(name, str) or not name or "\\" in name:
        return False
    path = PurePosixPath(name)
    return not path.is_absolute() and ".." not in path.parts


def stage_trial(source_only: Path, destination: Path) -> SourcePin:
    if (source_only.is_symlink() or not source_only.is_dir()
            or destination.exists() or destination.is_symlink()
            or destination.parent.is_symlink()):
        raise AdmissionError("unsafe D105 input or existing destination")
    original_manifest = source_only / "SOURCE_MANIFEST.json"
    original_tar = source_only / "source.tar"
    if any(path.is_symlink() or not path.is_file() for path in (original_manifest, original_tar)):
        raise AdmissionError("D103 files missing or symlinked")
    if (digest(original_manifest) != D103_SOURCE_MANIFEST_SHA256
            or digest(original_tar) != D103_SOURCE_TAR_SHA256):
        raise AdmissionError("D103 source-only bytes differ from reviewed pins")
    source = json.loads(original_manifest.read_text(encoding="utf8"))
    if (source.get("commit") != D103_SHA or source.get("archive_sha256") != D103_SOURCE_TAR_SHA256
            or source.get("type") != "SOURCE_ONLY_NOT_APPROVED_FOR_DEPLOYMENT"
            or source.get("node") != "node104"):
        raise AdmissionError("D103 source identity invalid")
    rows = source.get("source_files")
    if not isinstance(rows,list) or not rows or source.get("tracked_files") != len(rows):
        raise AdmissionError("D103 source inventory invalid")
    files={}
    for row in rows:
        if (type(row) is not dict or not safe_member(row.get("path"))
                or type(row.get("size")) is not int or row["size"] < 0
                or type(row.get("sha256")) is not str or len(row["sha256"]) != 64
                or row["path"] in files):
            raise AdmissionError("D103 source has unsafe duplicate/inventory item")
        files[row["path"]] = row
    temp = destination.parent / (".d105-" + uuid.uuid4().hex)
    temp.mkdir(mode=0o700)
    try:
        shutil.copyfile(original_tar, temp / "source.tar")
        root = temp / "tree"
        root.mkdir()
        seen=set()
        with tarfile.open(temp / "source.tar", "r:") as archive:
            for item in archive:
                if not safe_member(item.name):
                    raise AdmissionError("unsafe source archive path")
                if item.isdir():
                    continue
                if not item.isfile() or item.name in seen or item.name not in files:
                    raise AdmissionError("unsupported/duplicated archive member")
                seen.add(item.name)
                row=files[item.name]
                if item.size != row["size"]:
                    raise AdmissionError("source inventory size disagrees")
                blob=archive.extractfile(item)
                if blob is None:
                    raise AdmissionError("unreadable archive entry")
                dst = root / item.name
                dst.parent.mkdir(parents=True,exist_ok=True)
                h=hashlib.sha256()
                with dst.open("xb") as output:
                    for block in iter(lambda:blob.read(1024*1024),b""):
                        output.write(block);h.update(block)
                if h.hexdigest() != row["sha256"]:
                    raise AdmissionError("source inventory digest disagrees")
        if seen != set(files):
            raise AdmissionError("D103 manifest and tar disagree")
        manifest={"node":"node104","service":"rd6018-bot","source_sha":D103_SHA,
                  "archive_sha256":D103_SOURCE_TAR_SHA256,"files":rows}
        release= temp / "RELEASE_MANIFEST.json"
        release.write_text(json.dumps(manifest,indent=2,sort_keys=True)+"\n",encoding="utf8")
        pin=SourcePin(D103_SHA,D103_SOURCE_TAR_SHA256,digest(release))
        verify_source(temp,pin=pin)
        (temp/"STAGED_OK").write_text(json.dumps(
            {"manifest_sha256":pin.manifest_sha256,"tree_verified":True,
             "source_sha":D103_SHA},indent=2,sort_keys=True)+"\n",encoding="utf8")
        destination.parent.mkdir(parents=True,exist_ok=True)
        temp.rename(destination)
        return pin
    except BaseException:
        shutil.rmtree(temp,ignore_errors=True)
        raise


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_only",type=Path)
    parser.add_argument("destination",type=Path)
    a=parser.parse_args()
    pin=stage_trial(a.source_only,a.destination)
    print(json.dumps({"status":"D105_REVIEW_SOURCE_ONLY_PASS",
                      "source_sha":pin.commit,"archive_sha256":pin.archive_sha256,
                      "manifest_sha256":pin.manifest_sha256,"destination":str(a.destination)},
                     indent=2,sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
