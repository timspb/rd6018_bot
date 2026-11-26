"""Run unittest code from a disposable repository copy with historical inputs.

The candidate root is never used as the test process working directory. The
explicit interpreter must live in this candidate (for example, its Windows
``.venv\\Scripts\\python.exe``). Python isolated mode and a scrubbed environment
prevent foreign ``_pth``/PYTHONPATH configuration from supplying imports.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import ntpath
import shutil
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
HISTORICAL_BASELINE = "3c692554074b27805419a9b0767133a1c8d78150"
HISTORY_OBJECTS = ROOT / ".recipe-studio-local" / "b924-git-history" / ".git" / "objects"
IGNORE = shutil.ignore_patterns(
    ".venv", "venv", ".runtime", "__pycache__", ".pytest_cache", "*.pyc",
    "B*_CODEX_RESULT.txt", "B*_INCREMENTAL.patch",
)


def _clean_env() -> dict[str, str]:
    return {key: value for key, value in os.environ.items()
            if key.upper() not in {"PYTHONPATH", "PYTHONHOME"}}


def _candidate_interpreter(value: str, root: Path = ROOT) -> Path:
    candidate_root = root.resolve()
    supplied = Path(value).expanduser()
    if not supplied.is_absolute():
        supplied = candidate_root / supplied
    addressed = supplied.absolute()
    try:
        addressed.relative_to(candidate_root)
    except ValueError as exc:
        raise ValueError(f"interpreter must be addressed inside candidate root {candidate_root}: {addressed}") from exc
    executable = supplied.resolve()
    try:
        executable.relative_to(candidate_root)
    except ValueError:
        # POSIX venvs commonly symlink their executable to the base install.
        # The candidate-local pyvenv.cfg still selects the candidate venv.
        if not (addressed.parent.parent / "pyvenv.cfg").is_file():
            raise ValueError(f"interpreter must be a candidate-local venv interpreter: {addressed}")
    if not executable.is_file():
        raise FileNotFoundError(f"candidate-bound interpreter does not exist: {executable}")
    _validate_adjacent_pth_files(executable, addressed, candidate_root)
    # Keep the candidate-local spelling when launching. On POSIX the venv
    # executable often resolves to the base interpreter, while pyvenv.cfg and
    # site-packages remain under this candidate-local path.
    return addressed


def _validate_adjacent_pth_files(executable: Path, addressed: Path, candidate_root: Path) -> None:
    """Allow embedded-runtime path files only when every import stays in candidate."""
    path_files = set(executable.parent.glob("python*._pth")) | set(addressed.parent.glob("python*._pth"))
    for path_file in path_files:
        try:
            lines = path_file.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeError) as exc:
            raise ValueError(f"cannot read interpreter path file {path_file}: {exc}") from exc
        for number, raw_line in enumerate(lines, start=1):
            entry = raw_line.strip()
            if not entry or entry.startswith("#"):
                continue
            if entry == "import site":
                continue
            if "\x00" in entry or entry.startswith("import "):
                raise ValueError(f"malformed or unsupported _pth entry at {path_file}:{number}: {entry!r}")

            # Recognize Windows absolute/drive-relative forms even when this
            # policy is exercised on POSIX with a synthetic candidate tree.
            windows_drive, _ = ntpath.splitdrive(entry)
            windows_absolute = ntpath.isabs(entry) and not Path(entry).is_absolute()
            if windows_drive or windows_absolute:
                if os.name != "nt":
                    raise ValueError(f"_pth entry is outside candidate root: {path_file}:{number}: {entry}")
                try:
                    resolved = Path(ntpath.normpath(entry)).resolve()
                except (OSError, RuntimeError, ValueError) as exc:
                    raise ValueError(f"malformed _pth path entry at {path_file}:{number}: {entry}") from exc
            else:
                # _pth files use platform path syntax. Reject alternate
                # separators that could conceal an escaping Windows path.
                if os.name != "nt" and "\\" in entry:
                    raise ValueError(f"malformed _pth path entry at {path_file}:{number}: {entry}")
                try:
                    candidate_path = Path(entry)
                    resolved = (candidate_path if candidate_path.is_absolute() else path_file.parent / candidate_path).resolve()
                except (OSError, RuntimeError, ValueError) as exc:
                    raise ValueError(f"malformed _pth path entry at {path_file}:{number}: {entry}") from exc
            try:
                resolved.relative_to(candidate_root)
            except ValueError as exc:
                raise ValueError(f"_pth entry is outside candidate root: {path_file}:{number}: {entry}") from exc


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", "-C", str(root), *args], env=_clean_env(),
                          text=True, capture_output=True, check=False)


def _prepare_history(disposable: Path, history_objects: Path = HISTORY_OBJECTS) -> None:
    git_dir = _git(disposable, "rev-parse", "--absolute-git-dir")
    if git_dir.returncode:
        raise RuntimeError(f"disposable copy has no usable Git metadata: {git_dir.stderr.strip()}")

    # A fully assembled candidate may already carry the reviewed historical
    # baseline in its own Git object store. Prefer that self-contained state.
    baseline = _git(disposable, "cat-file", "-e", f"{HISTORICAL_BASELINE}^{{commit}}")
    if not baseline.returncode:
        return

    object_dir = Path(git_dir.stdout.strip()) / "objects"
    if not history_objects.is_dir():
        raise RuntimeError(
            f"historical Git baseline {HISTORICAL_BASELINE} is unavailable and "
            f"fallback object store is missing: {history_objects}"
        )
    # Copy loose objects and pack/index files. Existing object names are
    # immutable Git object identities and therefore already equivalent.
    for source_dir, directories, files in os.walk(history_objects):
        relative = Path(source_dir).relative_to(history_objects)
        target_dir = object_dir / relative
        target_dir.mkdir(parents=True, exist_ok=True)
        for filename in files:
            source = Path(source_dir) / filename
            target = target_dir / filename
            if not target.exists():
                shutil.copy2(source, target)

    baseline = _git(disposable, "cat-file", "-e", f"{HISTORICAL_BASELINE}^{{commit}}")
    if baseline.returncode:
        raise RuntimeError(
            f"historical Git baseline {HISTORICAL_BASELINE} is unavailable in disposable copy: "
            f"{baseline.stderr.strip()}"
        )


def _run(disposable: Path, python: Path, targets: list[str]) -> int:
    if targets:
        selected = disposable / "tools" / "_isolated_selected_runner.py"
        selected.write_text(
            "import os, sys, unittest\n"
            "sys.path[:0] = " + repr([str(disposable / "tools"), str(disposable / "tests"), str(disposable)]) + "\n"
            "suite = unittest.TestSuite()\n"
            "loader = unittest.defaultTestLoader\n"
            "for target in " + repr(targets) + ":\n"
            "    suite.addTests(loader.loadTestsFromName(target))\n"
            "result = unittest.TextTestRunner(verbosity=2).run(suite)\n"
            "sys.stdout.flush(); sys.stderr.flush()\n"
            "os._exit(0 if result.wasSuccessful() else 1)\n",
            encoding="utf-8",
        )
        command = [str(python), "-I", "-X", "utf8", str(selected)]
    else:
        command = [str(python), "-I", "-X", "utf8", str(disposable / "tools" / "ci_unittest_runner.py")]
    env = _clean_env()
    env["TG_TOKEN"] = "123456789:TEST_TOKEN_NOT_REAL"
    return subprocess.call(command, cwd=disposable, env=env)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", required=True,
                        help="explicit interpreter inside this candidate (e.g. .venv/Scripts/python.exe)")
    parser.add_argument("targets", nargs="*", help="unittest module names; default runs full CI discovery")
    args = parser.parse_args(argv)
    try:
        python = _candidate_interpreter(args.python)
        with tempfile.TemporaryDirectory(prefix="rd6018-tests-") as temp:
            disposable = Path(temp) / "candidate"
            shutil.copytree(ROOT, disposable, ignore=IGNORE)
            _prepare_history(disposable)
            env = _clean_env()
            prepare = subprocess.run(
                [str(python), "-I", "-X", "utf8", str(disposable / "tools" / "architecture" / "prepare_historical_test_inputs.py")],
                cwd=disposable, env=env, check=False,
            )
            if prepare.returncode:
                return prepare.returncode
            return _run(disposable, python, args.targets)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"isolated unittest preflight failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
