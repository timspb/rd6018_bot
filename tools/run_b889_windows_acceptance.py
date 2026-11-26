"""Full native Windows CPython 3.12.10 acceptance with retained Git inventory.

Run in the supervisor's isolated E-drive copy:
    .venv\\Scripts\\python.exe tools\\run_b889_windows_acceptance.py
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
TIMEOUT_SECONDS = 1800
HISTORICAL_BASELINE = "3c692554074b27805419a9b0767133a1c8d78150"


def _checkout_reference(value: str) -> str | None:
    """Return a foreign RD6018 checkout path embedded in a runtime value."""
    normalized = value.replace("\\", "/").casefold()
    current = str(ROOT.resolve()).replace("\\", "/").casefold().rstrip("/")
    for match in re.finditer(r"[^\"'\r\n]*rd6018[^\"'\r\n]*", normalized):
        reference = match.group(0).strip()
        current_index = reference.find(current)
        if current_index < 0:
            return reference
        suffix = reference[current_index + len(current):]
        if suffix and suffix[0] not in "/\\=:,)] \t":
            return reference
    return None


def runtime_contamination() -> str | None:
    """Reject interpreter configuration that imports another RD6018 tree."""
    candidates = [f"sys.executable={sys.executable}"]
    candidates.extend(f"sys.path[{index}]={entry}" for index, entry in enumerate(sys.path))
    executable_dir = Path(sys.executable).resolve().parent
    pth_files = (executable_dir / "python312._pth", executable_dir / "python._pth")
    for pth_file in pth_files:
        if pth_file.is_file():
            try:
                for line_number, line in enumerate(pth_file.read_text(encoding="utf-8").splitlines(), 1):
                    candidates.append(f"{pth_file}:{line_number}={line}")
            except (OSError, UnicodeError) as exc:
                return f"cannot inspect interpreter path file {pth_file}: {exc}"
    for candidate in candidates:
        foreign = _checkout_reference(candidate)
        if foreign:
            return f"interpreter contamination: {candidate} references another RD6018 checkout ({foreign})"
    return None


def git(*args: str) -> subprocess.CompletedProcess[str]:
    env = {key: value for key, value in os.environ.items() if not key.upper().startswith("GIT_")}
    return subprocess.run(["git", *args], cwd=ROOT, env=env, text=True,
                          capture_output=True, check=False)


def historical_baseline_error(returncode: int) -> str | None:
    if returncode == 0:
        return None
    return (
        "PREFLIGHT_ERROR: required historical Git baseline "
        f"{HISTORICAL_BASELINE} is missing; candidate Git history is incomplete. "
        "Restore the candidate's original .git history before full CI."
    )


def main() -> int:
    if os.name != "nt" or sys.implementation.name != "cpython" or sys.version_info[:3] != (3, 12, 10):
        print(f"B889 requires native Windows CPython 3.12.10; found {os.name} {sys.version}.")
        return 2
    contamination = runtime_contamination()
    if contamination:
        print(contamination)
        return 2
    if str(ROOT).startswith("\\\\") or not ROOT.drive:
        print(f"B889 requires a local Windows drive checkout; found {ROOT}.")
        return 2
    REPORTS.mkdir(parents=True, exist_ok=True)
    stdout_path = REPORTS / "B889_WINDOWS_STDOUT.txt"
    stderr_path = REPORTS / "B889_WINDOWS_STDERR.txt"
    marker_path = REPORTS / "B889_WINDOWS_EXIT.txt"
    meta = {
        "root": git("rev-parse", "--show-toplevel"),
        "branch": git("rev-parse", "--abbrev-ref", "HEAD"),
        "head": git("rev-parse", "HEAD"),
        "status": git("status", "--porcelain=v1"),
        "staged": git("diff", "--cached", "--name-status"),
        "unstaged": git("diff", "--name-status"),
        "untracked": git("ls-files", "--others", "--exclude-standard"),
    }
    git_root = meta["root"].stdout.strip()
    if git_root and os.path.normcase(os.path.realpath(git_root)) != os.path.normcase(os.path.realpath(ROOT)):
        print(f"Git root mismatch: candidate={ROOT}; Git reports={git_root}.")
        return 2
    env = {key: value for key, value in os.environ.items()
           if not key.upper().startswith("GIT_")
           and key.upper() not in {"PYTHONPATH", "PYTHONHOME"}}
    env["PYTHONPATH"] = os.pathsep.join(
        [str(ROOT / "tools"), str(ROOT / "tests"), str(ROOT)]
    )
    env["TG_TOKEN"] = "123456789:TEST_TOKEN_NOT_REAL"
    command = [sys.executable, "-X", "utf8", "tools/ci_unittest_runner.py"]
    exit_code = 1
    with stdout_path.open("w", encoding="utf-8", newline="\n") as stdout, \
            stderr_path.open("w", encoding="utf-8", newline="\n") as stderr:
        stdout.write(f"B889 native Windows full CI; Python: {sys.executable} ({sys.version})\n")
        stdout.write(f"Repository: {ROOT}\nTimeout: {TIMEOUT_SECONDS}s\nCOMMAND: {command!r}\n")
        for key, result in meta.items():
            stdout.write(f"\n--- GIT {key.upper()} (exit={result.returncode}) ---\n")
            stdout.write(result.stdout or "(empty)\n")
            if result.stderr:
                stdout.write("GIT STDERR: " + result.stderr + "\n")
            if result.returncode:
                exit_code = 2
        stdout.flush()
        if exit_code != 2:
            try:
                baseline = git("cat-file", "-e", f"{HISTORICAL_BASELINE}^{{commit}}")
                baseline_error = historical_baseline_error(baseline.returncode)
                if baseline_error:
                    stderr.write(baseline_error + "\n")
                    stderr.flush()
                    exit_code = 2
                else:
                    prepare = subprocess.run(
                        [sys.executable, "-X", "utf8", "tools/architecture/prepare_historical_test_inputs.py"],
                        cwd=ROOT, env=env, stdout=stdout, stderr=stderr, timeout=TIMEOUT_SECONDS,
                        check=False,
                    )
                    exit_code = prepare.returncode
            except subprocess.TimeoutExpired as exc:
                stderr.write(f"PREFLIGHT_TIMEOUT after {TIMEOUT_SECONDS}s: {exc}\n")
                stderr.flush()
                exit_code = 124
            except BaseException as exc:
                stderr.write(f"PREFLIGHT_ERROR {type(exc).__name__}: {exc}\n")
                stderr.flush()
                exit_code = 1
        if exit_code == 0:
            try:
                completed = subprocess.run(command, cwd=ROOT, env=env, stdout=stdout,
                                           stderr=stderr, timeout=TIMEOUT_SECONDS,
                                           check=False)
                exit_code = completed.returncode
            except subprocess.TimeoutExpired as exc:
                stderr.write(f"TIMEOUT after {TIMEOUT_SECONDS}s: {exc}\n")
                stderr.flush()
                exit_code = 124
            except BaseException as exc:
                stderr.write(f"LAUNCHER_ERROR {type(exc).__name__}: {exc}\n")
                stderr.flush()
                exit_code = 1
    marker_path.write_text(f"B889_WINDOWS_EXIT={exit_code}\n", encoding="utf-8")
    print(f"B889_WINDOWS_EXIT={exit_code}")
    print(f"stdout={stdout_path}\nstderr={stderr_path}\nmarker={marker_path}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
