"""Materialize architect-approved AD-008 owners as an additive diagnostic sidecar."""

from __future__ import annotations

import csv
from io import StringIO
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AD006_SIDECAR = ROOT / "tests/fixtures/architecture/ownership_history/mod_p1_owner_decisions_ad006_20261113.csv"
ADR = ROOT / "docs/RD6018_AD008_SECOND_OWNER_APPROVALS_2026-11-13.md"
SIDECAR = ROOT / ".recipe-studio-local/mod_p1_owner_decisions_ad008_20261113.csv"
REPORT = ROOT / ".recipe-studio-local/REPORT_MOD_P1_AD008_OWNER_RECONCILIATION_20261113.md"

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

AD008_FIELDS = ["AD008_approved_primary_owner", "AD008_approval_status", "AD008_decision_provenance"]
AD008_PROVENANCE = "architect_AD008_2026-11-13"


def _read_text(path: Path) -> str:
    if not path.is_file():
        raise FileNotFoundError(f"required AD008 input missing: {path.relative_to(ROOT)}")
    return path.read_text(encoding="utf-8")


def _read_ad006() -> tuple[list[str], list[dict[str, str]]]:
    if not AD006_SIDECAR.is_file():
        raise FileNotFoundError(f"required AD006 sidecar missing: {AD006_SIDECAR.relative_to(ROOT)}")
    with AD006_SIDECAR.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        fields = list(reader.fieldnames or [])
        rows = list(reader)
    if not fields or "path" not in fields:
        raise ValueError("AD006 sidecar has no path field")
    paths = [row["path"] for row in rows]
    if len(rows) != 480 or len(set(paths)) != 480:
        raise ValueError("AD006 sidecar must contain exactly 480 unique paths")
    if any(row.get("final_owner", "") for row in rows):
        raise ValueError("AD006 final_owner must remain empty for every row")
    if any(field in fields for field in AD008_FIELDS):
        raise ValueError("AD006 sidecar already contains AD008 fields; refusing ambiguous reconciliation")
    approved = {row["path"]: row.get("approved_primary_owner", "") for row in rows if row.get("approved_primary_owner", "")}
    if approved != AD006_APPROVALS:
        raise ValueError("AD006 sidecar approvals do not exactly match its five architect-approved decisions")
    if any(row.get("approval_status") != "APPROVED_PRIMARY_OWNER_ONLY" for row in rows if row["path"] in AD006_APPROVALS):
        raise ValueError("AD006 approval status conflict")
    additions = {"runtime/operator/off_conditions.py", "runtime/charge/evidence/adopted_mix_prior_age.py"}
    if not additions.issubset(set(paths)):
        raise ValueError("the two additive working-set paths are missing from AD006 sidecar")
    for path in additions:
        row = next(row for row in rows if row["path"] == path)
        if row.get("approval_status") != "UNAPPROVED" or row.get("approved_primary_owner", ""):
            raise ValueError(f"AD006 working-set addition must remain unapproved: {path}")
    return fields, rows


def _validate_adr_and_sources(rows: list[dict[str, str]]) -> None:
    adr = _read_text(ADR)
    if "APPROVED ten narrowly scoped PRIMARY MODULE department assignments" not in adr:
        raise ValueError("AD008 ADR does not state the exact ten-owner approval boundary")
    paths = {row["path"] for row in rows}
    for path, owner in AD008_APPROVALS.items():
        expected = f"| {path} | {owner} |"
        if expected not in adr:
            raise ValueError(f"AD008 ADR missing exact owner mapping: {expected}")
        if path not in paths:
            raise ValueError(f"AD008 approved path is absent from AD006 sidecar: {path}")
        if not (ROOT / path).is_file():
            raise FileNotFoundError(f"AD008 approved source path missing: {path}")
    if len(AD008_APPROVALS) != 10 or set(AD008_APPROVALS) & set(AD006_APPROVALS):
        raise ValueError("AD008 approval set is not ten distinct paths")


def build_rows() -> tuple[list[str], list[dict[str, str]]]:
    fields, rows = _read_ad006()
    _validate_adr_and_sources(rows)
    for row in rows:
        row.update({field: "" for field in AD008_FIELDS})
        if row["path"] in AD008_APPROVALS:
            row["AD008_approved_primary_owner"] = AD008_APPROVALS[row["path"]]
            row["AD008_approval_status"] = "APPROVED_PRIMARY_OWNER_ONLY"
            row["AD008_decision_provenance"] = AD008_PROVENANCE
    return fields + AD008_FIELDS, rows


def render_csv() -> str:
    fields, rows = build_rows()
    stream = StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue()


def render_report() -> str:
    fields, rows = build_rows()
    approved = [row for row in rows if row["AD008_approval_status"]]
    prior = [row for row in rows if row["approval_status"] == "APPROVED_PRIMARY_OWNER_ONLY"]
    pending = len(rows) - len(approved) - len(prior)
    table = "\n".join(f"| `{row['path']}` | {row['AD008_approved_primary_owner']} |" for row in approved)
    return f"""# P1-AD008 owner reconciliation report

Status: source-only diagnostic reconciliation; release remains **HOLD**.

## Inputs and reconciliation

- Source: unchanged `.recipe-studio-local/mod_p1_owner_decisions_ad006_20261113.csv`.
- Output: additive AD008 sidecar with all AD006 columns and row values retained, plus only `{', '.join(AD008_FIELDS)}`.
- Coverage: {len(rows)} unique paths. Original AD006 approval records: {len(prior)}; new AD008 approval records: {len(approved)}; total approved: {len(prior) + len(approved)}; pending: {pending}.
- Every `final_owner` remains empty. The two additive working-set paths remain unapproved.

## AD008 architect decisions

| Exact path | Approved primary department |
|---|---|
{table}

These are narrow primary module classifications only. They do not claim exclusive command authority, active runtime reachability, safety ownership, or permission to alter production behavior. No ownership was inferred from folder, confidence, or neighboring modules.

## Validation and limits

The generator validates exact owner strings against the AD008 ADR, verifies each source path exists, checks the AD006 five-approval baseline and empty `final_owner` values, and fails closed on missing paths or conflicts. This is static diagnostic evidence only; no production, node104, HA, ESP, physical, network, deployment, or release validation was performed.

Recorded local checks: `python3 -m py_compile tools/architecture/reconcile_owner_decisions_ad008.py tests/test_architecture_owner_decisions_ad008.py` — PASS; `pytest -q tests/test_architecture_owner_decisions_ad008.py` — 4 passed; `git diff --check` — PASS. Output determinism and field preservation are covered by those four targeted tests.
"""


def write_outputs() -> None:
    csv_text = render_csv()
    report_text = render_report()
    SIDECAR.write_text(csv_text, encoding="utf-8", newline="")
    REPORT.write_text(report_text, encoding="utf-8", newline="")


if __name__ == "__main__":
    write_outputs()
    print(f"wrote {SIDECAR.relative_to(ROOT)} and {REPORT.relative_to(ROOT)}")
