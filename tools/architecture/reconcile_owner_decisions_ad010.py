"""Materialize architect-approved AD010 owners as an additive diagnostic sidecar."""

from __future__ import annotations

import csv
from io import StringIO
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AD008_SIDECAR = ROOT / "tests/fixtures/architecture/ownership_history/mod_p1_owner_decisions_ad008_20261113.csv"
ADR = ROOT / "docs/RD6018_AD010_THIRD_OWNER_APPROVALS_2026-11-13.md"
SIDECAR = ROOT / ".recipe-studio-local/mod_p1_owner_decisions_ad010_20261113.csv"
REPORT = ROOT / ".recipe-studio-local/REPORT_MOD_P1_AD010_OWNER_RECONCILIATION_20261113.md"

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
AD010_FIELDS = ["ad010_primary_owner", "ad010_decision_status", "ad010_provenance"]
AD010_PROVENANCE = "architect_AD010_2026-11-13"
ADDITIONS = {
    "runtime/operator/off_conditions.py",
    "runtime/charge/evidence/adopted_mix_prior_age.py",
}
MANUAL_STORE_PATH = "runtime/charge/manual_session_store.py"
MANUAL_STORE_ROW = {
    "path": MANUAL_STORE_PATH,
    "existing_candidate": "NO_AD004_CANDIDATE",
    "proposed_owner": "REVIEW_REQUIRED",
    "confidence": "uncertain",
    "evidence": "No AD-004 candidate: source was untracked at HEAD and absent from the historical 478-path inventory.",
    "mixed_responsibility": "false",
    "side_effect_type": "filesystem read/write",
    "public_entrypoints": "read_manual_session_document@19, write_manual_session_document@38",
    "primary_consumers": "manual_mode.py:17[eager]",
    "review_reason": "Added working-set coverage by AD010A; Manual JSON persistence adapter has an active source import; no historical owner evidence exists.",
    "risk_band": "review",
    "final_owner": "",
    "approved_primary_owner": "",
    "approval_status": "",
    "decision_provenance": "",
    "inventory_provenance": "untracked_at_HEAD",
    "working_set_status": "UNAPPROVED_AD006_ADDITION",
    "source_caller_evidence": "runtime/charge/manual_session_store.py:19: def read_manual_session_document | runtime/charge/manual_session_store.py:38: def write_manual_session_document | manual_mode.py:17: from runtime.charge.manual_session_store import ( | manual_mode.py calls both adapters for manual_session_v2.json persistence",
    "authority_limit": "File persistence adapter only; no session policy, chemistry transition, safety admission, or actuator authority.",
    "AD008_approved_primary_owner": "",
    "AD008_approval_status": "",
    "AD008_decision_provenance": "",
}


def _read_ad008() -> tuple[list[str], list[dict[str, str]]]:
    if not AD008_SIDECAR.is_file():
        raise FileNotFoundError(f"required AD008 sidecar missing: {AD008_SIDECAR.relative_to(ROOT)}")
    with AD008_SIDECAR.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        fields = list(reader.fieldnames or [])
        rows = list(reader)
    if not fields or "path" not in fields:
        raise ValueError("AD008 sidecar has no path field")
    paths = [row["path"] for row in rows]
    if len(rows) != 480 or len(set(paths)) != 480:
        raise ValueError("AD008 sidecar must contain exactly 480 unique paths")
    if any(field in fields for field in AD010_FIELDS):
        raise ValueError("AD008 sidecar already contains AD010 fields; refusing ambiguous reconciliation")
    if any(row.get("final_owner", "") for row in rows):
        raise ValueError("legacy final_owner must remain empty for every row")
    ad006 = {r["path"]: r.get("approved_primary_owner", "") for r in rows if r.get("approved_primary_owner", "")}
    ad008 = {r["path"]: r.get("AD008_approved_primary_owner", "") for r in rows if r.get("AD008_approved_primary_owner", "")}
    if ad006 != AD006_APPROVALS or ad008 != AD008_APPROVALS:
        raise ValueError("AD006/AD008 approvals do not match the exact approved baselines")
    if set(AD010_APPROVALS) & (set(ad006) | set(ad008)):
        raise ValueError("AD010 approval overlaps an existing approval")
    if set(ad006) & set(ad008):
        raise ValueError("AD006 and AD008 approval paths overlap")
    if any(row.get("approval_status") != "APPROVED_PRIMARY_OWNER_ONLY" for row in rows if row["path"] in AD006_APPROVALS):
        raise ValueError("AD006 approval status conflict")
    if any(row.get("AD008_approval_status") != "APPROVED_PRIMARY_OWNER_ONLY" for row in rows if row["path"] in AD008_APPROVALS):
        raise ValueError("AD008 approval status conflict")
    if MANUAL_STORE_PATH in paths:
        raise ValueError("AD008 sidecar unexpectedly already contains AD010A additive path")
    if not ADDITIONS.issubset(set(paths)):
        raise ValueError("the two AD008 additive working-set paths are missing")
    for path in ADDITIONS:
        row = next(row for row in rows if row["path"] == path)
        if row.get("inventory_provenance") != "untracked_at_HEAD":
            raise ValueError(f"AD008 addition provenance changed: {path}")
    return fields, rows


def _validate_adr_and_sources(rows: list[dict[str, str]]) -> None:
    adr = ADR.read_text(encoding="utf-8")
    paths = {row["path"] for row in rows}
    for path, owner in AD010_APPROVALS.items():
        expected = f"| {path} | {owner} |"
        if expected not in adr:
            raise ValueError(f"AD010 ADR missing exact owner mapping: {expected}")
        if path != MANUAL_STORE_PATH and path not in paths:
            raise ValueError(f"AD010 approved path is absent from AD008 sidecar: {path}")
        if not (ROOT / path).is_file():
            raise FileNotFoundError(f"AD010 approved source path missing: {path}")
        if path == MANUAL_STORE_PATH:
            continue
        row = next(r for r in rows if r["path"] == path)
        if row.get("final_owner", "") or row.get("AD008_approved_primary_owner", ""):
            raise ValueError(f"AD010 path already has a conflicting/legacy owner: {path}")
    for path in set(AD006_APPROVALS) | set(AD008_APPROVALS):
        if not (ROOT / path).is_file():
            raise FileNotFoundError(f"prior approved source path missing: {path}")
    if len(AD010_APPROVALS) != 6 or len(set(AD010_APPROVALS) & (set(AD006_APPROVALS) | set(AD008_APPROVALS))):
        raise ValueError("AD010 approvals are not six distinct paths")


def build_rows() -> tuple[list[str], list[dict[str, str]]]:
    fields, rows = _read_ad008()
    _validate_adr_and_sources(rows)
    if not (ROOT / MANUAL_STORE_PATH).is_file():
        raise FileNotFoundError(f"AD010 approved source path missing: {MANUAL_STORE_PATH}")
    for row in rows:
        row.update({field: "" for field in AD010_FIELDS})
        if row["path"] in AD010_APPROVALS:
            row["ad010_primary_owner"] = AD010_APPROVALS[row["path"]]
            row["ad010_decision_status"] = "APPROVED_PRIMARY_OWNER_ONLY"
            row["ad010_provenance"] = AD010_PROVENANCE
    added = dict(MANUAL_STORE_ROW)
    added.update({field: "" for field in AD010_FIELDS})
    added["ad010_primary_owner"] = AD010_APPROVALS[MANUAL_STORE_PATH]
    added["ad010_decision_status"] = "APPROVED_PRIMARY_OWNER_ONLY"
    added["ad010_provenance"] = AD010_PROVENANCE
    rows.append(added)
    return fields + AD010_FIELDS, rows


def render_csv() -> str:
    fields, rows = build_rows()
    stream = StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue()


def render_report() -> str:
    _, rows = build_rows()
    approvals = [row for row in rows if row["ad010_decision_status"]]
    old = [row for row in rows if row["approval_status"] == "APPROVED_PRIMARY_OWNER_ONLY"]
    old += [row for row in rows if row["AD008_approval_status"] == "APPROVED_PRIMARY_OWNER_ONLY"]
    pending = len(rows) - len(old) - len(approvals)
    table = "\n".join(f"| `{r['path']}` | {r['ad010_primary_owner']} |" for r in approvals)
    return f"""# P1-AD010 owner reconciliation report

Status: source-only diagnostic reconciliation; physical and release status remain **HOLD**.

## Inputs and reconciliation

- Source: unchanged `.recipe-studio-local/mod_p1_owner_decisions_ad008_20261113.csv`.
- Output preserves all 480 original rows and every prior field value, then appends one row; AD010 fields are `{', '.join(AD010_FIELDS)}`.
- Original inventory: 478 paths; AD008 additions: 2; AD010A addition: `runtime/charge/manual_session_store.py`; total working set: 481 unique paths. All three added rows retain `untracked_at_HEAD` provenance.
- Prior approvals: AD006=5 and AD008=10; new AD010 approvals=6; total=21; pending=460.
- `runtime/charge/evidence/adopted_mix_prior_age.py` is now explicitly approved while retaining its source provenance. `runtime/operator/off_conditions.py` remains unapproved. Every legacy `final_owner` remains blank.

## AD010 architect decisions

| Exact path | Approved primary department |
|---|---|
{table}

These are narrow module classifications only. They do not claim exclusive command authority, runtime actuation authority, deployment approval, or physical acceptance. No approvals were inferred from confidence, folder, or neighboring modules.

## Validation and limits

The generator validates exact AD010 ADR rows, source existence, the exact AD006/AD008 baselines, unique 481-path coverage, untracked provenance, non-overlap, unchanged legacy rows, and blank legacy owners; invalid or conflicting input fails closed. No production, node104, HA, ESP, network, physical, service, deployment, or secret activity was performed.

Recorded local checks: `python3 -m py_compile tools/architecture/reconcile_owner_decisions_ad010.py tests/test_architecture_owner_decisions_ad010.py` — PASS; `python3 -m unittest tests.test_architecture_owner_decisions_ad010` — 7 PASS; `git diff --check` — PASS (pre-existing CRLF normalization warnings only). Tests invoke the generator directly and check deterministic bytes without subprocess capture.
"""


def write_outputs() -> None:
    SIDECAR.write_text(render_csv(), encoding="utf-8", newline="")
    REPORT.write_text(render_report(), encoding="utf-8", newline="")


if __name__ == "__main__":
    write_outputs()
    print(f"wrote {SIDECAR.relative_to(ROOT)} and {REPORT.relative_to(ROOT)}")
