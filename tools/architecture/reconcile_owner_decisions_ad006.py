"""Build the additive, source-only AD-006 owner decision reconciliation."""

from __future__ import annotations

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASELINE = ROOT / "tests/fixtures/architecture/ownership_history/mod_p1_owner_evidence_ad004_20261113.csv"
ADR = ROOT / "docs/RD6018_AD006_FIRST_OWNER_APPROVALS_2026-11-13.md"
SIDECAR = ROOT / ".recipe-studio-local/mod_p1_owner_decisions_ad006_20261113.csv"
REPORT = ROOT / ".recipe-studio-local/REPORT_MOD_P1_AD006_OWNER_RECONCILIATION_20261113.md"
EXPECTED_HEAD = "3c692554074b27805419a9b0767133a1c8d78150"

APPROVALS = {
    "database.py": ("Sessions & Persistence", "aiosqlite", "runtime/production_runtime.py", "runtime/production_lifecycle.py"),
    "bot.py": ("Composition/Configuration", "class ProductionComposition", "runtime/production_runtime.py", "operator_dashboard.py"),
    "operator_dashboard.py": ("UI", "def install_operator_dashboard", "bot.py", "operator_hmi.py"),
    "ha_history.py": ("Telemetry/Evidence", "class HomeAssistantHistoryReader", "physical_test_control_d062.py", "rd_live_adoption.py"),
    "runtime/physical/connectors/esp_direct.py": ("Physical Execution", "class ESPDirectConnector", "runtime/physical/connectors/factory.py", "hass_api.py"),
}
ADDITIONS = {
    "runtime/operator/off_conditions.py": (
        "split_required_unapproved",
        "class OperatorOffConditions",
        "runtime/production_runtime.py",
        "imported at line 32; instantiated at line 444; logger reads and persists operator OFF conditions",
    ),
    "runtime/charge/evidence/adopted_mix_prior_age.py": (
        "unresolved_unapproved",
        "def resolve_prior_mix_age",
        "rd_managed_mix.py",
        "rd_managed_mix imports prior-age projection; pure evidence selection preserves conservative age floor",
    ),
}

EXTRA_FIELDS = [
    "final_owner",
    "approved_primary_owner",
    "approval_status",
    "decision_provenance",
    "inventory_provenance",
    "working_set_status",
    "source_caller_evidence",
    "authority_limit",
]


def _read(path: Path) -> str:
    if not path.is_file():
        raise FileNotFoundError(f"required AD-006 input missing: {path.relative_to(ROOT)}")
    return path.read_text(encoding="utf-8")


def _line_evidence(path: str, token: str) -> str:
    lines = _read(ROOT / path).splitlines()
    for number, line in enumerate(lines, 1):
        if token in line:
            return f"{path}:{number}: {line.strip()}"
    raise ValueError(f"source evidence token {token!r} missing from {path}")


def _baseline() -> tuple[list[str], list[dict[str, str]]]:
    adr = _read(ADR)
    for path, decision in APPROVALS.items():
        expected = f"| {path} | {decision[0]} |"
        if expected not in adr:
            raise ValueError(f"AD-006 architect ADR is missing exact owner label: {expected}")
    if "precisely five existing production paths" not in adr:
        raise ValueError("AD-006 ADR does not state the five-path approval boundary")
    if not BASELINE.is_file():
        raise FileNotFoundError(f"required AD-004 baseline missing: {BASELINE.relative_to(ROOT)}")
    with BASELINE.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        fields = list(reader.fieldnames or [])
        rows = list(reader)
    if len(rows) != 478 or len({row["path"] for row in rows}) != 478:
        raise ValueError("AD-004 baseline must contain exactly 478 unique paths")
    return fields, rows


def build_rows() -> tuple[list[str], list[dict[str, str]]]:
    fields, rows = _baseline()
    paths = {row["path"] for row in rows}
    if set(APPROVALS) - paths:
        raise ValueError("one or more architect-approved paths are absent from AD-004 baseline")
    if set(ADDITIONS) & paths:
        raise ValueError("AD-006 addition unexpectedly already exists in AD-004 baseline")
    for row in rows:
        row.update({field: "" for field in EXTRA_FIELDS})
        if row["path"] in APPROVALS:
            owner = APPROVALS[row["path"]][0]
            row["approved_primary_owner"] = owner
            row["approval_status"] = "APPROVED_PRIMARY_OWNER_ONLY"
            row["decision_provenance"] = "architect_AD006_2026-11-13"
            row["working_set_status"] = "IN_AD004_478"
            row["authority_limit"] = "Primary module owner only; no nested safety or exclusive active command authority approval."
            if row["path"] == "runtime/physical/connectors/esp_direct.py":
                row["authority_limit"] = "Adapter module only; no exclusive physical command authority, active command reachability, or bypass permission around application.ExecutionPort/Safety."

    for path, (state, source_token, caller, note) in ADDITIONS.items():
        evidence = _line_evidence(path, source_token)
        caller_line = _line_evidence(caller, path.rsplit("/", 1)[-1].replace(".py", ""))
        row = {name: "" for name in fields + EXTRA_FIELDS}
        row.update({
            "path": path,
            "existing_candidate": "NO_AD004_CANDIDATE",
            "proposed_owner": "REVIEW_REQUIRED",
            "confidence": "uncertain",
            "evidence": "No AD-004 candidate: path was outside the original 478-row inventory.",
            "mixed_responsibility": "true" if "split" in state else "false",
            "side_effect_type": "source behavior requires review; no physical authority inferred",
            "public_entrypoints": evidence,
            "primary_consumers": caller_line,
            "review_reason": "Added working-set coverage only; owner remains unapproved.",
            "risk_band": "review",
            "approval_status": "UNAPPROVED",
            "inventory_provenance": "untracked_at_HEAD",
            "working_set_status": "UNAPPROVED_AD006_ADDITION",
            "source_caller_evidence": f"{evidence} | {caller_line} | {note}",
            "authority_limit": "No owner approval; source/caller presence is static evidence and does not establish runtime reachability or command authority.",
        })
        rows.append(row)

    output_fields = fields + EXTRA_FIELDS
    return output_fields, rows


def render_csv() -> str:
    fields, rows = build_rows()
    from io import StringIO

    stream = StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue()


def render_report() -> str:
    fields, rows = build_rows()
    approved = [row for row in rows if row["approval_status"] == "APPROVED_PRIMARY_OWNER_ONLY"]
    additions = [row for row in rows if row["inventory_provenance"] == "untracked_at_HEAD"]
    return f"""# P1-AD006 owner reconciliation report

Status: source-only diagnostic reconciliation; production/release acceptance remains **HOLD**.

## Coverage and decisions

- Baseline: AD-004 sidecar, exactly 478 unique original paths; all original evidence fields are preserved byte-for-field in this additive output.
- Reconciled working set: {len(rows)} unique rows; original 478 path set unchanged; additions: {', '.join(row['path'] for row in additions)}.
- Architect-approved primary owners: exactly {len(approved)} and only the five below. AD-004 `proposed_owner`, evidence, mixed-responsibility, side-effect, consumer, and review fields are unchanged; every original `final_owner` notion remains empty (this schema does not add or populate one).
- Added paths have provenance `untracked_at_HEAD`, no fabricated AD-004 candidate, and `UNAPPROVED` status. Their source and caller evidence is captured in the sidecar.
- All other original rows remain unapproved. No path-derived or confidence-derived approvals are made.

| Path | Approved primary owner | Scope limit |
|---|---|---|
""" + "\n".join(f"| `{row['path']}` | {row['approved_primary_owner']} | {row['authority_limit']} |" for row in approved) + """

`runtime/physical/connectors/esp_direct.py` approval classifies the adapter module only. It does not grant exclusive physical command authority, active command reachability, or bypass permission around `application.ExecutionPort` and Safety.

The false AD-004 `ChargeEngine` proposal for `database.py` is rejected by AD-006. `runtime/__init__.py` also remains unresolved; its AD-004 `ChargeEngine` proposal is rejected. This reconciliation does not approve nested safety decisions or the mixed/unresolved AD-005 batch.

## Validation limits

Inputs are local source, the immutable AD-004 sidecar, AD-004/AD-005 reports, and architect-authored AD-006. No production imports, physical reads, node access, deployment, service actions, or hardware commands are part of this tool. This report records static source/caller evidence only; it cannot establish dynamic reachability or physical behavior.
"""


def write_outputs() -> None:
    csv_text = render_csv()
    report_text = render_report()
    SIDECAR.parent.mkdir(parents=True, exist_ok=True)
    SIDECAR.write_text(csv_text, encoding="utf-8", newline="")
    REPORT.write_text(report_text, encoding="utf-8", newline="")


if __name__ == "__main__":
    write_outputs()
    print(f"wrote {SIDECAR.relative_to(ROOT)} and {REPORT.relative_to(ROOT)}")
