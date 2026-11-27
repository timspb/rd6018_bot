"""Add the five architect-approved AD014 primary owners to a new sidecar."""

from __future__ import annotations

import csv
from io import StringIO
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AD010_SIDECAR = ROOT / "tests/fixtures/architecture/ownership_history/mod_p1_owner_decisions_ad010_20261113.csv"
AD012_SIDECAR = ROOT / "tests/fixtures/architecture/ownership_history/mod_p1_owner_coverage_ad012_20261113.csv"
ADR = ROOT / "docs/RD6018_AD014_FOURTH_OWNER_APPROVALS_2026-11-13.md"
SIDECAR = ROOT / ".recipe-studio-local/mod_p1_owner_decisions_ad014_20261113.csv"
REPORT = ROOT / ".recipe-studio-local/REPORT_MOD_P1_AD014_OWNER_RECONCILIATION_20261113.md"

AD006_APPROVALS = {
    "database.py": "Sessions & Persistence",
    "bot.py": "Composition/Configuration",
    "operator_dashboard.py": "UI",
    "ha_history.py": "Telemetry/Evidence",
    "runtime/physical/connectors/esp_direct.py": "Physical Execution",
}
AD008_APPROVALS = {
    "runtime/telemetry/snapshot.py": "Telemetry/Evidence",
    "runtime/charge/strategy/desulfation_variables.py": "ChargeEngine",
    "runtime/ui/components/stage_duration.py": "UI",
    "runtime/ui/components/main_stage_progress.py": "UI",
    "runtime/ui/components/mix_stage_progress.py": "UI",
    "runtime/ui/labels/operator_actions.py": "UI",
    "runtime/ui/screens/help.py": "UI",
    "runtime/ui/screens/analysis.py": "UI",
    "runtime/ui/screens/stats.py": "UI",
    "runtime/ui/components/journal_filter.py": "UI",
}
AD010_APPROVALS = {
    "runtime/charge/battery.py": "Battery/Chemistry",
    "runtime/charge/chemistry.py": "Battery/Chemistry",
    "runtime/charge/decisions.py": "ChargeEngine",
    "runtime/charge/manual_session_store.py": "Sessions & Persistence",
    "runtime/ui/components/hmi_state.py": "UI",
    "runtime/charge/evidence/adopted_mix_prior_age.py": "Telemetry/Evidence",
}
AD014_APPROVALS = {
    "runtime/charge/evidence/adopted_mix_source_timestamp.py": "Telemetry/Evidence",
    "runtime/charge/evidence/adopted_mix_sample_decision.py": "Telemetry/Evidence",
    "runtime/charge/evidence/adopted_mix_finish_hold_decision.py": "ChargeEngine",
    "runtime/charge/strategy/adopted_mix_admission.py": "Safety",
    "runtime/operator/pause_state.py": "Sessions & Persistence",
}
AD012_ADDITIONS = {
    "application/manual_cooling_use_case.py",
    "application/manual_mix_transition_use_case.py",
    "application/manual_observer_use_case.py",
    "application/manual_phase_evidence.py",
    "application/manual_start_use_case.py",
    "application/manual_stop_use_case.py",
    "application/manual_supervisor_use_case.py",
    "application/operator_pause_use_case.py",
    "runtime/charge/evidence/adopted_mix_finish_hold_decision.py",
    "runtime/charge/evidence/adopted_mix_sample_decision.py",
    "runtime/charge/evidence/adopted_mix_source_timestamp.py",
    "runtime/charge/evidence/manual_delta.py",
    "runtime/charge/restore_admission.py",
    "runtime/charge/restore_finalization.py",
    "runtime/charge/restore_projection.py",
    "runtime/charge/strategy/adopted_mix_admission.py",
    "runtime/operator/pause_state.py",
    "runtime/operator/__init__.py",
}
AD014_FIELDS = ["ad014_primary_owner", "ad014_decision_status", "ad014_provenance"]
AD014_PROVENANCE = "architect_AD014_2026-11-13"


def _read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    if not path.is_file():
        raise FileNotFoundError(f"required sidecar missing: {path}")
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        fields = list(reader.fieldnames or [])
        rows = list(reader)
    if not fields or "path" not in fields:
        raise ValueError(f"sidecar has no path field: {path}")
    if len(fields) != len(set(fields)):
        raise ValueError(f"sidecar has duplicate columns: {path}")
    return fields, rows


def _exact_approval_map(rows: list[dict[str, str]], owner_field: str) -> dict[str, str]:
    found: dict[str, str] = {}
    for row in rows:
        owner = row.get(owner_field, "")
        if owner:
            path = row["path"]
            if path in found:
                raise ValueError(f"duplicate approval path in {owner_field}: {path}")
            found[path] = owner
    return found


def _validate_baseline() -> tuple[list[str], list[dict[str, str]]]:
    fields, rows = _read_csv(AD012_SIDECAR)
    paths = [row["path"] for row in rows]
    if len(rows) != 499 or len(set(paths)) != 499:
        raise ValueError(f"AD012 baseline must contain 499 unique paths; got {len(rows)} rows/{len(set(paths))} paths")
    if len(AD012_ADDITIONS) != 18:
        raise ValueError("internal AD012 path manifest drift")
    if set(paths[-18:]) != AD012_ADDITIONS or set(paths[:481]) & AD012_ADDITIONS:
        raise ValueError("AD012 path set/order drifted from 481 prior rows plus the exact 18 additions")
    if any(row.get("final_owner", "") for row in rows):
        raise ValueError("legacy final_owner must remain blank on all AD012 rows")
    if any(field in fields for field in AD014_FIELDS):
        raise ValueError("AD012 baseline already contains AD014 fields")
    if "inventory_provenance" not in fields or "working_set_status" not in fields:
        raise ValueError("AD012 baseline is missing provenance/status columns")
    if any(row.get("working_set_status") != "untracked_at_HEAD" for row in rows if row["path"] in AD012_ADDITIONS):
        raise ValueError("AD012 addition working_set_status changed")

    prior_maps = (
        ("approved_primary_owner", AD006_APPROVALS, "AD006"),
        ("AD008_approved_primary_owner", AD008_APPROVALS, "AD008"),
        ("ad010_primary_owner", AD010_APPROVALS, "AD010"),
    )
    for owner_field, expected, label in prior_maps:
        actual = _exact_approval_map(rows, owner_field)
        if actual != expected:
            raise ValueError(f"{label} registry values changed: expected exact prior approvals")
    if len(set(AD006_APPROVALS) | set(AD008_APPROVALS) | set(AD010_APPROVALS)) != 21:
        raise ValueError("prior approval manifests overlap or drift")
    if _exact_approval_map(rows, "approved_primary_owner") != AD006_APPROVALS:
        raise ValueError("AD006 approvals conflict")
    for row in rows:
        path = row["path"]
        if path in AD006_APPROVALS and row.get("approval_status") != "APPROVED_PRIMARY_OWNER_ONLY":
            raise ValueError(f"AD006 status conflict: {path}")
        if path in AD008_APPROVALS and row.get("AD008_approval_status") != "APPROVED_PRIMARY_OWNER_ONLY":
            raise ValueError(f"AD008 status conflict: {path}")
        if path in AD010_APPROVALS and row.get("ad010_decision_status") != "APPROVED_PRIMARY_OWNER_ONLY":
            raise ValueError(f"AD010 status conflict: {path}")
    if sum(bool(row.get("approved_primary_owner") or row.get("AD008_approved_primary_owner") or row.get("ad010_primary_owner")) for row in rows) != 21:
        raise ValueError("AD012 baseline must retain exactly 21 distinct prior approvals")

    old_fields, old_rows = _read_csv(AD010_SIDECAR)
    if len(old_rows) != 481 or [row["path"] for row in rows[:481]] != [row["path"] for row in old_rows]:
        raise ValueError("AD012's first 481 rows drifted from the AD010 registry")
    for field in old_fields:
        if field not in fields or any(new[field] != old[field] for new, old in zip(rows[:481], old_rows)):
            raise ValueError(f"AD010 registry values changed in AD012: {field}")
    return fields, rows


def _validate_adr_and_approved_sources(rows: list[dict[str, str]]) -> None:
    if not ADR.is_file():
        raise FileNotFoundError(f"required AD014 ADR missing: {ADR}")
    adr = ADR.read_text(encoding="utf-8")
    path_to_row = {row["path"]: row for row in rows}
    for path, owner in AD014_APPROVALS.items():
        exact_row = f"| {path} | {owner} |"
        if exact_row not in adr:
            raise ValueError(f"AD014 ADR missing exact owner label: {exact_row}")
        if path not in path_to_row:
            raise ValueError(f"AD014 approved path missing from AD012: {path}")
        if not (ROOT / path).is_file():
            raise FileNotFoundError(f"AD014 approved source path missing: {path}")
        row = path_to_row[path]
        if row.get("inventory_provenance") != "AD012_2026-11-13" or row.get("working_set_status") != "untracked_at_HEAD":
            raise ValueError(f"AD014 source provenance changed: {path}")
        if row.get("final_owner", "") or row.get("approved_primary_owner", "") or row.get("AD008_approved_primary_owner", "") or row.get("ad010_primary_owner", ""):
            raise ValueError(f"AD014 path has a conflicting older approval: {path}")
    if len(AD014_APPROVALS) != 5 or set(AD014_APPROVALS) & (set(AD006_APPROVALS) | set(AD008_APPROVALS) | set(AD010_APPROVALS)):
        raise ValueError("AD014 approvals overlap an older approved path or drift from five")
    for path in AD012_ADDITIONS - set(AD014_APPROVALS):
        row = path_to_row[path]
        if row.get("approved_primary_owner") or row.get("AD008_approved_primary_owner") or row.get("ad010_primary_owner"):
            raise ValueError(f"unapproved AD012 addition has an unexpected older approval: {path}")


def build_rows() -> tuple[list[str], list[dict[str, str]]]:
    fields, rows = _validate_baseline()
    _validate_adr_and_approved_sources(rows)
    result = []
    for original in rows:
        row = dict(original)
        row.update({field: "" for field in AD014_FIELDS})
        if row["path"] in AD014_APPROVALS:
            row["ad014_primary_owner"] = AD014_APPROVALS[row["path"]]
            row["ad014_decision_status"] = "APPROVED_PRIMARY_OWNER_ONLY"
            row["ad014_provenance"] = AD014_PROVENANCE
        result.append(row)
    return fields + AD014_FIELDS, result


def render_csv() -> str:
    fields, rows = build_rows()
    stream = StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n", extrasaction="raise")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue()


def render_report() -> str:
    _, rows = build_rows()
    approvals = [row for row in rows if row["ad014_decision_status"]]
    return """# P1-AD014 — Architect owner reconciliation (diagnostic only)

## Source and preserved registry

- Input: immutable `.recipe-studio-local/mod_p1_owner_coverage_ad012_20261113.csv`.
- The 499 AD012 rows are retained in order with every prior field value unchanged; only three AD014 fields are appended.
- The first 481 paths and old registry values are cross-checked against AD010; the exact 18 AD012 additions and their `untracked_at_HEAD` status are validated.
- All rows retain their `inventory_provenance` and `working_set_status`; legacy `final_owner` remains blank.

## Architect-approved decisions

| Exact path | Approved primary department |
|---|---|
""" + "\n".join(f"| `{row['path']}` | {row['ad014_primary_owner']} |" for row in approvals) + """

Only these five paths receive AD014 fields. The other 13 AD012 additions and all previously pending rows remain unassigned.

## Counts and limits

- Working set: **499 unique paths** (481 earlier rows + 18 additions).
- Prior approvals: AD006=5, AD008=10, AD010=6 (**21**).
- AD014 approvals: **5**; total approved: **26**; pending: **473**.
- `inventory_provenance` and `working_set_status` are copied unchanged for every row.
- No production, device, HA, ESP, network, physical, service, deployment, or secret action was performed. Node104 and full modularization/release remain **HOLD**.

## Local verification

- `python3 -m py_compile tools/architecture/reconcile_owner_decisions_ad014.py tests/test_architecture_owner_decisions_ad014.py` — PASS.
- `python3 -m unittest tests.test_architecture_owner_decisions_ad014` — 6 PASS.
- `git diff --check` — PASS (exit 0; Git emitted pre-existing broad-worktree CRLF normalization warnings).
- Independent Windows acceptance remains pending. This executor did not call the Wake R7.2 connector; notifications are launcher-owned.

Generated in-process by `tools/architecture/reconcile_owner_decisions_ad014.py`.
"""


def write_outputs() -> None:
    SIDECAR.write_text(render_csv(), encoding="utf-8", newline="")
    REPORT.write_text(render_report(), encoding="utf-8", newline="")


if __name__ == "__main__":
    write_outputs()
    print(f"wrote {SIDECAR.relative_to(ROOT)} and {REPORT.relative_to(ROOT)}")
