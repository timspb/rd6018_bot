"""Reproducible native Windows acceptance runner for B861.

Run with the repository's supported Windows project venv from any directory:
    <venv>\\Scripts\\python.exe tools\\run_b861_windows_acceptance.py
Logs are written directly to reports/B861_WINDOWS_STDOUT.txt and
reports/B861_WINDOWS_STDERR.txt. A final exit marker is always written.
"""
from __future__ import annotations

import subprocess
import sys
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
TIMEOUT_SECONDS = 600

COHORTS = {
    "P8_13_MODULE_REGRESSION": [
        "test_acceptance_transient",
        "test_source_audit_inventory",
        "test_d140_disk_guard",
        "test_node104_atomic_deploy",
        "test_node104_d090_transaction",
        "test_d061_detached_supervisor",
        "test_d061_global_gate",
        "test_d061_kill_supervisor",
        "test_d061_supervisor_fixture_protocol",
        "test_d143_owner_bound_transition",
        "test_d144_owner_binding",
        "test_node104_d106_readonly_recovery",
        "test_node104_d145_entrypoint",
    ],
    "P6_P7_AND_B842_GRAPH": [
        "tests.test_b854_ui_dependency_injection",
        "tests.test_p7_telegram_handler_owners_batch21",
        "tests.test_start_route_isolation",
        "tests.test_battery_selection_regression",
        "tests.test_production_start_route",
        "tests.test_production_start_runner",
        "tests.test_ui_polish",
        "tests.test_b842_external_graph_history",
    ],
    "COMPOSED_START_ROUTE_CAPTURE": [
        "tests.test_recipe_real_callback_chain.RealRecipeCallbackChainTests.test_registered_battery_callback_uses_shared_selection_owner_state",
        "tests.test_recipe_real_callback_chain.RealRecipeCallbackChainTests.test_registered_quick_profile_ah_intent_start_uses_same_pending_owner",
    ],
    "NO_AUTOMATIC_START_ON_INSTALL_OR_RECOVERY": [
        "tests.test_production_entrypoint.V2EntrypointTests.test_composed_graph_unknown_output_never_restores_v1_start",
        "tests.test_production_entrypoint.V2EntrypointTests.test_composed_graph_autonomous_never_restores_pb_start",
        "tests.test_autonomous_startup_authority_contract",
        "tests.test_modularization_restore_lifecycle_containment_ad155.RestoreLifecycleContainmentAD155.test_every_late_restore_failure_is_quarantined_before_background_start",
        "tests.test_modularization_restore_lifecycle_containment_ad155.RestoreLifecycleContainmentAD155.test_successful_restore_does_not_quarantine_and_startup_continues",
    ],
}


def main() -> int:
    REPORTS.mkdir(parents=True, exist_ok=True)
    stdout_path = REPORTS / "B861_WINDOWS_STDOUT.txt"
    stderr_path = REPORTS / "B861_WINDOWS_STDERR.txt"
    marker_path = REPORTS / "B861_WINDOWS_EXIT.txt"
    env = os.environ.copy()
    env.setdefault("TG_TOKEN", "123456789:TEST_TOKEN_NOT_REAL")
    exit_code = 1
    with stdout_path.open("w", encoding="utf-8", newline="\n") as stdout, \
            stderr_path.open("w", encoding="utf-8", newline="\n") as stderr:
        stdout.write(f"B861 native Windows acceptance; Python: {sys.executable}\n")
        stdout.write(f"Repository: {ROOT}\nTimeout per cohort: {TIMEOUT_SECONDS}s\n")
        stdout.flush()
        try:
            for name, modules in COHORTS.items():
                command = [sys.executable, "-m", "unittest", *modules, "-v"]
                stdout.write(f"\n=== {name} ===\nCOMMAND: {command!r}\n")
                stdout.flush()
                completed = subprocess.run(
                    command,
                    cwd=ROOT,
                    env=env,
                    stdout=stdout,
                    stderr=stderr,
                    timeout=TIMEOUT_SECONDS,
                    check=False,
                )
                stdout.write(f"COHORT_EXIT {name}={completed.returncode}\n")
                stdout.flush()
                if completed.returncode:
                    exit_code = completed.returncode
                    break
            else:
                exit_code = 0
        except subprocess.TimeoutExpired as exc:
            stderr.write(f"TIMEOUT after {TIMEOUT_SECONDS}s: {exc}\n")
            stderr.flush()
            exit_code = 124
        except BaseException as exc:
            stderr.write(f"LAUNCHER_ERROR: {type(exc).__name__}: {exc}\n")
            stderr.flush()
            exit_code = 1
    marker_path.write_text(f"B861_WINDOWS_EXIT={exit_code}\n", encoding="utf-8")
    print(f"B861_WINDOWS_EXIT={exit_code}")
    print(f"stdout={stdout_path}")
    print(f"stderr={stderr_path}")
    print(f"marker={marker_path}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
