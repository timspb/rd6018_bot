"""Materialize architect-approved AD012 coverage without assigning owners."""
from __future__ import annotations

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASELINE = Path("tests/fixtures/architecture/ownership_history/mod_p1_owner_decisions_ad010_20261113.csv")
AD011 = Path("tests/fixtures/architecture/mod_p1_registry_coverage_ad011_20261113.csv")
OUTPUT = Path(".recipe-studio-local/mod_p1_owner_coverage_ad012_20261113.csv")
REPORT = Path(".recipe-studio-local/REPORT_MOD_P1_AD012_COVERAGE_RECONCILIATION_20261113.md")
AD012_PATHS = (
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
)
EXPECTED_APPROVALS = {"AD006": 5, "AD008": 10, "AD010": 6}


def _read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames:
            raise ValueError(f"missing CSV header: {path}")
        return list(reader.fieldnames), list(reader)


def _git_status(path: str) -> str:
    result = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all", "--", path],
        cwd=ROOT, check=True, capture_output=True, text=True,
    )
    rows = [line for line in result.stdout.splitlines() if line]
    if len(rows) != 1:
        raise ValueError(f"expected one untracked status row for {path}: {rows!r}")
    # Porcelain's two status columns must report untracked, not staged/modified.
    if rows[0][:2] != "??" or rows[0][3:] != path:
        raise ValueError(f"path is not untracked at HEAD/worktree: {path}: {rows[0]!r}")
    tracked = subprocess.run(
        ["git", "ls-files", "--error-unmatch", "--", path], cwd=ROOT,
        capture_output=True, text=True,
    )
    if tracked.returncode == 0:
        raise ValueError(f"AD012 addition is already tracked: {path}")
    return "untracked_at_HEAD"


def _validate_ad010(rows: list[dict[str, str]]) -> None:
    paths = [row["path"] for row in rows]
    if len(rows) != 481 or len(set(paths)) != 481:
        raise ValueError(f"AD010 must contain 481 unique rows; got {len(rows)}")
    if any(row.get("final_owner", "") for row in rows):
        raise ValueError("legacy final_owner must remain blank in AD010")
    counts = {
        "AD006": sum(row.get("approval_status") == "APPROVED_PRIMARY_OWNER_ONLY" and "AD006" in row.get("decision_provenance", "") for row in rows),
        "AD008": sum(row.get("AD008_approval_status") == "APPROVED_PRIMARY_OWNER_ONLY" for row in rows),
        "AD010": sum(row.get("ad010_decision_status") == "APPROVED_PRIMARY_OWNER_ONLY" for row in rows),
    }
    if counts != EXPECTED_APPROVALS:
        raise ValueError(f"preceding approval counts changed: {counts!r}")
    approved = sum(
        row.get("approval_status") == "APPROVED_PRIMARY_OWNER_ONLY"
        or row.get("AD008_approval_status") == "APPROVED_PRIMARY_OWNER_ONLY"
        or row.get("ad010_decision_status") == "APPROVED_PRIMARY_OWNER_ONLY"
        for row in rows
    )
    if approved != 21:
        raise ValueError(f"expected 21 distinct approved rows; got {approved}")


def _new_row(fields: list[str], path: str, audit: dict[str, str]) -> dict[str, str]:
    row = {field: "" for field in fields}
    consumers = audit["source_import_consumers"]
    row.update({
        "path": path,
        "existing_candidate": "",
        "proposed_owner": "REVIEW_REQUIRED",
        "confidence": "uncertain",
        "evidence": "AD012-approved coverage addition; source/import evidence recorded from AD011; ownership remains unassigned.",
        "mixed_responsibility": "uncertain",
        "side_effect_type": "review required; no authority inferred from static source evidence",
        "public_entrypoints": "source definitions require owner review",
        "primary_consumers": consumers or "no inbound source consumer confirmed; package exports OperatorOffConditions",
        "review_reason": "AD012 coverage only; no primary-owner approval or runtime reachability claim",
        "risk_band": audit["risk"],
        "final_owner": "",
        "approved_primary_owner": "",
        "approval_status": "UNAPPROVED",
        "decision_provenance": "",
        "inventory_provenance": "AD012_2026-11-13",
        "working_set_status": "untracked_at_HEAD",
        "source_caller_evidence": consumers or "runtime/operator/__init__.py exports OperatorOffConditions; no inbound consumer confirmed",
        "authority_limit": "Static coverage evidence only; does not establish runtime reachability, owner, or command authority.",
        "AD008_approved_primary_owner": "",
        "AD008_approval_status": "",
        "AD008_decision_provenance": "",
        "ad010_primary_owner": "",
        "ad010_decision_status": "UNAPPROVED",
        "ad010_provenance": "AD012 coverage addition only; owner not assigned",
    })
    return row


def build_rows(root: Path = ROOT) -> tuple[list[str], list[dict[str, str]]]:
    baseline_path = root / BASELINE
    audit_path = root / AD011
    fields, original = _read_csv(baseline_path)
    _validate_ad010(original)
    audit_fields, audit_rows = _read_csv(audit_path)
    del audit_fields
    audit = {row["path"]: row for row in audit_rows}
    existing = {row["path"] for row in original}
    if len(AD012_PATHS) != 18 or len(set(AD012_PATHS)) != 18:
        raise ValueError("AD012 path manifest must contain exactly 18 unique paths")
    additions = []
    for path in AD012_PATHS:
        if path in existing:
            raise ValueError(f"AD012 addition already exists in AD010: {path}")
        if not (root / path).is_file():
            raise ValueError(f"AD012 source path missing: {path}")
        row = audit.get(path)
        if row is None or row.get("git_status") != "untracked" or row.get("registry_membership") != "undiscovered":
            raise ValueError(f"AD011 evidence/status contradicts AD012 for {path}: {row!r}")
        additions.append(_new_row(fields, path, row))
    result = original + additions
    paths = [row["path"] for row in result]
    if len(result) != 499 or len(set(paths)) != 499:
        raise ValueError(f"expected 499 unique rows; got {len(result)} rows/{len(set(paths))} paths")
    return fields, result


def render_csv(fields: list[str], rows: list[dict[str, str]]) -> str:
    import io
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fields, lineterminator="\n", extrasaction="raise")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def render_report(rows: list[dict[str, str]]) -> str:
    approved = 21
    return (
        "# P1-AD012 — Coverage reconciliation (diagnostic only)\n\n"
        "Architect-approved scope is coverage addition for the exact 18 paths in AD012; this is not owner assignment.\n\n"
        f"- AD010 original rows preserved field-for-field: 481\n"
        f"- AD012 additions: {len(rows) - 481}; all `UNAPPROVED`, legacy `final_owner` blank\n"
        f"- Unique working-set paths: {len({r['path'] for r in rows})}\n"
        f"- Approved owner assignments: {approved} (AD006 5 + AD008 10 + AD010 6)\n"
        f"- Pending owner assignments: {len(rows) - approved}\n"
        "- AD011 baseline: 18 undiscovered paths; all were required to exist and be untracked at HEAD\n\n"
        "`runtime/operator/__init__.py` exports `OperatorOffConditions`; AD011 found no inbound source consumer. "
        "This static export is recorded as evidence only and does not establish runtime reachability or ownership.\n\n"
        "Generated deterministically by `tools/architecture/reconcile_owner_coverage_ad012.py`. "
        "No production imports, hardware/device calls, network access, or runtime actions are performed.\n\n"
        "Status: source-only release **HOLD**. R7.2 execution/ACK: not performed by this executor.\n"
    )


def generate(root: Path = ROOT) -> tuple[Path, Path]:
    fields, rows = build_rows(root)
    csv_path, report_path = root / OUTPUT, root / REPORT
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    csv_path.write_text(render_csv(fields, rows), encoding="utf-8", newline="")
    report_path.write_text(render_report(rows), encoding="utf-8", newline="")
    return csv_path, report_path


if __name__ == "__main__":
    generate()
