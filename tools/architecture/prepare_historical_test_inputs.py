"""Prepare only historical, source-reviewed architecture test inputs.

Run this inside a disposable clean checkout before pytest. Derived owner
sidecars remain ignored test outputs, not production or approval records.
"""
from __future__ import annotations

import io
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures" / "architecture"
OUTPUT = ROOT / ".recipe-studio-local"
HISTORICAL_INPUTS = (
    "mod_p2_ownership_inventory_unique_20261112.csv",
    "mod_p1_registry_coverage_ad011_20261113.csv",
    "REPORT_MOD_P1_AD148S_OWNER_CHRONOLOGY_20261117.md",
)
BUILD_CHAIN = (
    "reconcile_owner_decisions_ad006.py",
    "reconcile_owner_decisions_ad008.py",
    "reconcile_owner_decisions_ad010.py",
    "reconcile_owner_coverage_ad012.py",
    "reconcile_owner_decisions_ad014.py",
)
HISTORICAL_BASELINE = "3c692554074b27805419a9b0767133a1c8d78150"
HISTORICAL_SOURCE_FIXTURE = (
    FIXTURES / "ownership_history"
    / "source_3c692554074b27805419a9b0767133a1c8d78150.tar.gz"
)


def materialize_source_preimage(destination: Path, *, root: Path = ROOT,
                                 baseline: str = HISTORICAL_BASELINE) -> Path:
    """Extract the required historical source tree without touching the candidate."""
    result = subprocess.run(
        ["git", "-C", str(root), "archive", "--format=tar", baseline],
        cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    destination.mkdir(parents=True, exist_ok=True)
    if result.returncode == 0:
        with tarfile.open(fileobj=io.BytesIO(result.stdout), mode="r:") as bundle:
            bundle.extractall(destination)
    elif baseline == HISTORICAL_BASELINE and HISTORICAL_SOURCE_FIXTURE.is_file():
        # Fresh clones may not retain this old commit object. The tracked
        # source-only fixture is an archive of the exact 478 inventory paths.
        with tarfile.open(HISTORICAL_SOURCE_FIXTURE, mode="r:gz") as bundle:
            bundle.extractall(destination)
    else:
        raise subprocess.CalledProcessError(
            result.returncode, result.args, output=result.stdout, stderr=result.stderr
        )
    if not any(destination.iterdir()):
        raise RuntimeError(f"historical source baseline is empty: {baseline}")
    return destination


def build_ad004(source_root: Path, *, root: Path = ROOT) -> None:
    script = root / "tools" / "architecture" / "build_owner_evidence_ad004.py"
    subprocess.run(
        [sys.executable, str(script), "--source-root", str(source_root)],
        cwd=root, check=True,
    )


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for name in HISTORICAL_INPUTS:
        fixture = FIXTURES / name
        output = OUTPUT / name
        if not fixture.is_file():
            raise FileNotFoundError(f"required tracked architecture fixture: {fixture}")
        if output.exists():
            if output.read_bytes() != fixture.read_bytes():
                raise RuntimeError(f"refusing to overwrite a different local historical input: {output}")
        else:
            shutil.copy2(fixture, output)
    with tempfile.TemporaryDirectory(prefix="rd6018-ad004-preimage-") as temp:
        source_root = materialize_source_preimage(Path(temp) / "source")
        build_ad004(source_root)
    for name in BUILD_CHAIN:
        subprocess.run([sys.executable, str(ROOT / "tools" / "architecture" / name)], cwd=ROOT, check=True)
    print("HISTORICAL_ARCHITECTURE_TEST_CORPUS=READY")


if __name__ == "__main__":
    main()
