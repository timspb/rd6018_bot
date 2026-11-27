"""Full native Windows CPython 3.12 regression with retained logs and Git inventory.

Run using the candidate's supported Windows project venv:
    .venv\\Scripts\\python.exe tools\\run_b884_windows_acceptance.py
The runner uses the real checkout; it does not create synthetic Git history.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
TIMEOUT_SECONDS = 1800


def git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=ROOT, text=True, capture_output=True, check=False,
    )


def main() -> int:
    if os.name != "nt" or sys.version_info[:2] != (3, 12):
        print(f"B884 requires native Windows CPython 3.12; found {os.name} {sys.version}.")
        return 2
    REPORTS.mkdir(parents=True, exist_ok=True)
    stdout_path = REPORTS / "B884_WINDOWS_STDOUT.txt"
    stderr_path = REPORTS / "B884_WINDOWS_STDERR.txt"
    marker_path = REPORTS / "B884_WINDOWS_EXIT.txt"
    meta = {
        "root": git("rev-parse", "--show-toplevel"),
        "branch": git("rev-parse", "--abbrev-ref", "HEAD"),
        "head": git("rev-parse", "HEAD"),
        "status": git("status", "--porcelain=v1"),
        "staged": git("diff", "--cached", "--name-status"),
        "unstaged": git("diff", "--name-status"),
        "untracked": git("ls-files", "--others", "--exclude-standard"),
    }
    env = os.environ.copy()
    paths = [str(ROOT / "tools"), str(ROOT / "tests"), str(ROOT)]
    if env.get("PYTHONPATH"):
        paths.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(paths)
    env["TG_TOKEN"] = "123456789:TEST_TOKEN_NOT_REAL"
    command = [sys.executable, "tools/ci_unittest_runner.py"]
    exit_code = 1
    with stdout_path.open("w", encoding="utf-8", newline="\n") as stdout, \
            stderr_path.open("w", encoding="utf-8", newline="\n") as stderr:
        stdout.write(f"B884 native Windows full CI; Python: {sys.executable} ({sys.version})\n")
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
                completed = subprocess.run(
                    command, cwd=ROOT, env=env, stdout=stdout, stderr=stderr,
                    timeout=TIMEOUT_SECONDS, check=False,
                )
                exit_code = completed.returncode
            except subprocess.TimeoutExpired as exc:
                stderr.write(f"TIMEOUT after {TIMEOUT_SECONDS}s: {exc}\n")
                stderr.flush()
                exit_code = 124
            except BaseException as exc:
                stderr.write(f"LAUNCHER_ERROR {type(exc).__name__}: {exc}\n")
                stderr.flush()
                exit_code = 1
    marker_path.write_text(f"B884_WINDOWS_EXIT={exit_code}\n", encoding="utf-8")
    print(f"B884_WINDOWS_EXIT={exit_code}")
    print(f"stdout={stdout_path}\nstderr={stderr_path}\nmarker={marker_path}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
