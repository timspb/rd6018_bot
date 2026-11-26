"""Reproducible native Windows source/fake acceptance runner for B870.

Run from the B870 candidate with its supported Windows project venv:
    <venv>\\Scripts\\python.exe tools\\run_b870_windows_acceptance.py
Logs are written directly under reports/ and a final exit marker is written.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
TIMEOUT_SECONDS = 600

COHORTS = {
    "B870_BATTERY_ADD_OWNER": [
        "tests.test_b870_battery_add_input_lifecycle",
        "tests.test_battery_selection_regression",
        "tests.test_b854_ui_dependency_injection",
    ],
    "P6_P7": [
        "tests.test_source_audit_inventory",
        "tests.test_modularization_text_ingress_contract",
        "tests.test_modularization_operator_off_state_cutover",
        "tests.test_b863_recipe_selection_ingress",
        "tests.test_p7_telegram_handler_owners_batch21",
        "tests.test_v3_modular_architecture_contract",
    ],
    "P8_FAKE_REGRESSION": [
        "tests.test_acceptance_transient",
        "tests.test_node104_atomic_deploy",
    ],
    "PERSISTENCE_AND_START": [
        "tests.test_session_atomic_windows_fd_ownership",
        "tests.test_session_atomic_guard_binding",
        "tests.test_session_start_pending",
        "tests.test_d123_sprint28_terminal_persistence",
        "tests.test_production_start_execution_port",
        "tests.test_production_start_route",
        "tests.test_production_start_runner",
    ],
}


def main() -> int:
    REPORTS.mkdir(parents=True, exist_ok=True)
    stdout_path = REPORTS / "B870_WINDOWS_STDOUT.txt"
    stderr_path = REPORTS / "B870_WINDOWS_STDERR.txt"
    marker_path = REPORTS / "B870_WINDOWS_EXIT.txt"
    env = os.environ.copy()
    search_paths = [str(ROOT / "tests"), str(ROOT)]
    if env.get("PYTHONPATH"):
        search_paths.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(search_paths)
    env["TG_TOKEN"] = "123456789:TEST_TOKEN_NOT_REAL"
    git_metadata = subprocess.run(
        ["git", "rev-parse", "--show-toplevel", "--abbrev-ref", "HEAD", "HEAD"],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )
    exit_code = 0
    with stdout_path.open("w", encoding="utf-8", newline="\n") as stdout, \
            stderr_path.open("w", encoding="utf-8", newline="\n") as stderr:
        stdout.write(f"B870 native Windows source/fake acceptance; Python: {sys.executable}\n")
        stdout.write(f"Repository: {ROOT}\nTimeout per cohort: {TIMEOUT_SECONDS}s\n")
        if git_metadata.returncode == 0:
            lines = git_metadata.stdout.splitlines()
            stdout.write(f"Verified Git root: {lines[0]}\nBranch: {lines[1]}\nHEAD: {lines[2]}\n")
        else:
            stdout.write("Git metadata unavailable; source inventory cohort will fail closed.\n")
        stdout.flush()
        for name, modules in COHORTS.items():
            command = [sys.executable, "-m", "unittest", *modules, "-v"]
            stdout.write(f"\n=== {name} ===\nCOMMAND: {command!r}\n")
            stdout.flush()
            try:
                completed = subprocess.run(
                    command, cwd=ROOT, env=env, stdout=stdout, stderr=stderr,
                    timeout=TIMEOUT_SECONDS, check=False,
                )
                cohort_exit = completed.returncode
            except subprocess.TimeoutExpired as exc:
                stderr.write(f"TIMEOUT {name} after {TIMEOUT_SECONDS}s: {exc}\n")
                stderr.flush()
                cohort_exit = 124
            except BaseException as exc:
                stderr.write(f"LAUNCHER_ERROR {name}: {type(exc).__name__}: {exc}\n")
                stderr.flush()
                cohort_exit = 1
            stdout.write(f"COHORT_EXIT {name}={cohort_exit}\n")
            stdout.flush()
            if cohort_exit and exit_code == 0:
                exit_code = cohort_exit
    marker_path.write_text(f"B870_WINDOWS_EXIT={exit_code}\n", encoding="utf-8")
    print(f"B870_WINDOWS_EXIT={exit_code}")
    print(f"stdout={stdout_path}")
    print(f"stderr={stderr_path}")
    print(f"marker={marker_path}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
