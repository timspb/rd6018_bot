"""Build the additive, evidence-backed AD148T owner decision crosswalk."""
from __future__ import annotations

import csv
import importlib.util
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / ".recipe-studio-local"
CSV_OUT = OUT / "mod_p1_owner_ledger_ad148t_20261117.csv"
REPORT_OUT = OUT / "REPORT_MOD_P1_AD148T_OWNER_REGISTRY_20261117.md"
EVENTS_OUT = OUT / "mod_p1_owner_ledger_events_ad148v_20261117.json"
AUDIT_OUT = OUT / "mod_p1_owner_ledger_adr_coverage_ad148v_20261117.json"
HISTORY = ROOT / "tests/fixtures/architecture/ownership_history"
CHRONOLOGY = ROOT / "tests/fixtures/architecture/REPORT_MOD_P1_AD148S_OWNER_CHRONOLOGY_20261117.md"
AD010 = HISTORY / "mod_p1_owner_decisions_ad010_20261113.csv"
AD012 = HISTORY / "mod_p1_owner_coverage_ad012_20261113.csv"
AD014 = HISTORY / "mod_p1_owner_decisions_ad014_20261113.csv"
GENERATOR = ROOT / "tools/architecture/reconcile_owner_decisions_ad014.py"

def _ad014_module():
    spec = importlib.util.spec_from_file_location("canonical_ad014", GENERATOR)
    if not spec or not spec.loader:
        raise ValueError("AD014 generator unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def _csv(path: Path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames or len(reader.fieldnames) != len(set(reader.fieldnames)):
            raise ValueError(f"invalid CSV header: {path}")
        rows = list(reader)
    if len({r["path"] for r in rows}) != len(rows):
        raise ValueError(f"duplicate path: {path}")
    return list(reader.fieldnames), rows

def _events():
    """Decisions transcribed from the source-reviewed AD148S chronology."""
    events = []
    def add(stage, path, owner, status="APPROVED_PRIMARY_OWNER_ONLY", scope="Whole-file primary owner; bounded scope per source decision.", doc=None, heading=None, evidence=None):
        if doc is None:
            doc = "docs/RD6018_MODULARIZATION_MASTER_PLAN_2026-11-12.md" if stage in {"AD056", "AD057"} else None
        if doc is None:
            doc = next((p.relative_to(ROOT).as_posix() for p in sorted((ROOT/"docs").glob(f"RD6018_{stage}_*.md"))), None)
        if not doc or not (ROOT/doc).is_file():
            raise ValueError(f"missing decision source for {stage} {path}")
        lines = (ROOT/doc).read_text(encoding="utf-8").splitlines()
        needle = path
        stage_heading=[i for i,line in enumerate(lines) if line.startswith("##") and f"— {stage} " in line]
        decision_heading=[i for i,line in enumerate(lines) if line.startswith("##") and "decision" in line.casefold()]
        start=stage_heading[0] if stage_heading else (decision_heading[0] if decision_heading else next((i for i,line in enumerate(lines) if line.startswith("#")),None))
        if start is None: raise ValueError(f"required decision heading missing: {doc} {stage}")
        # ADR files are one document per stage; their decision block may span
        # several ## subsections. Master-plan stage excerpts end at next ##.
        end=next((i for i in range(start+1,len(lines)) if lines[i].startswith("# ")),len(lines)) if "MODULARIZATION_MASTER_PLAN" not in doc else next((i for i in range(start+1,len(lines)) if lines[i].startswith("##")),len(lines))
        matches = [i for i in range(start,end) if needle in lines[i]] if path else []
        if not matches and evidence:
            matches = [i for i in range(start,end) if evidence.casefold() in lines[i].casefold()]
            if not matches:
                # The stage's own ADR title is valid provenance for stage-only
                # audit events when its body uses a different heading vocabulary.
                matches=[i for i,line in enumerate(lines) if line.startswith("#") and (stage in line or stage.replace("AD","AD-") in line)]
        if not matches:
            raise ValueError(f"source {doc} does not evidence cited decision/path/owner: {stage} {path} {owner}")
        idx = matches[0]
        owner_idx=idx
        if path and owner:
            owner_terms={"Telemetry/Evidence":("Telemetry",),"Safety Authority":("Safety",),"Engine / Charge Stages":("Engine / Charge Stages",),"Application adapter":("Application adapter",),"Manual Delta Evidence":("Manual Delta Evidence",),"Application transaction orchestration":("Application",),"Presentation / Telegram workflow":("Presentation / Telegram workflow",)}.get(owner,(owner,))
            row=lines[idx]
            if not any(term.casefold() in row.casefold() for term in owner_terms):
                # Some ADRs separate the exact implementation path from its owner
                # mapping. Accept only a dedicated bounded Ownership subsection.
                sub=next((i for i in range(idx,-1,-1) if lines[i].startswith("### ")),None)
                if sub is None: raise ValueError(f"source path/owner association missing: {doc}:{idx+1} {path} {owner}")
                subend=next((i for i in range(sub+1,end) if lines[i].startswith("### ")),end)
                owner_matches=[i for i in range(sub,subend) if any(t.casefold() in lines[i].casefold() for t in owner_terms)]
                if not owner_matches: raise ValueError(f"source path/owner association missing in bounded subsection: {doc}:{idx+1} {path} {owner}")
                owner_idx=owner_matches[0]
        if heading is None:
            heading = next((lines[i].lstrip("# ").strip() for i in range(idx, -1, -1) if lines[i].startswith("#")), "(no heading)")
        events.append({"stage":stage,"path":path or "","owner":owner or "","status":status,"scope":scope,"source":doc,"heading":heading,"line":idx+1,"owner_line":owner_idx+1})

    m="docs/RD6018_MODULARIZATION_MASTER_PLAN_2026-11-12.md"
    for p,o in {
      "application/controller_action_execution.py":"Application","application/controller_session_retirement.py":"Recovery & Ownership","application/execution_intent/policy.py":"Safety Authority","application/safe_output_coordinator.py":"Physical Execution","runtime/safety/strict_guard.py":"Safety Authority","runtime/safety/managed_guard.py":"Safety Authority","application/execution_port.py":"Physical Execution","application/session_recovery_service.py":"Recovery & Ownership","runtime/startup_recovery.py":"Recovery & Ownership","runtime/production_lifecycle.py":"Composition/Config/Deploy","application/main_guard_transaction.py":"Physical Execution"}.items(): add("AD056",p,o,doc=m)
    for p,o in {"diagnostic_persistence.py":"Sessions & Persistence","diagnostic_probe.py":"Application","hass_api.py":"Integrations","rd_managed_adoption.py":"Recovery & Ownership","rd_managed_mix.py":"Recovery & Ownership","runtime/production_runtime.py":"Composition/Config/Deploy"}.items(): add("AD057",p,o,doc=m)
    # Later ADR approvals; exact source path+owner text is checked below.
    approvals={
      "AD062":{"runtime/charge/evidence/recovery_plateau_observer.py":"Telemetry/Evidence","runtime/charge/evidence/recovery_plateau_policy.py":"Telemetry/Evidence"},
      "AD063":{"application/main_guard_runtime.py":"Application"},"AD065":{"runtime/charge/strategy/main_authority.py":"Engine / Charge Stages"},"AD067":{"runtime/charge/restore_finalization.py":"Application"},
      "AD069":{"application/manual_cooling_use_case.py":"Application","application/manual_mix_transition_use_case.py":"Application","application/manual_start_use_case.py":"Application","application/manual_stop_use_case.py":"Application"},
      "AD071":{"application/start_transaction_runner.py":"Application","application/start_transaction_adapter.py":"Application","application/charge_session_tick.py":"Application"},
      "AD073":{"application/operator_recovery_clearance.py":"Application","application/session_recovery_guard.py":"Recovery & Ownership","runtime/journal/recovery_quarantine.py":"Recovery & Ownership"},
      "AD078":{"runtime/charge/diagnostics.py":"Application","runtime/telemetry/recorder.py":"Telemetry/Evidence","signal_analyzer.py":"Engine / Charge Stages","recovery_trace_report.py":"Recovery & Ownership","recovery_session.py":"Recovery & Ownership","charging_log.py":"Sessions & Persistence"},
      "AD080":{"manual_mode.py":"Application"},
      "AD082":{"runtime/safety/engine.py":"Safety Authority","runtime/safety/edge_lease.py":"Safety Authority","runtime/safety/output_policy.py":"Safety Authority","runtime/safety/critical_telemetry.py":"Safety Authority","runtime/safety/telemetry_recovery.py":"Safety Authority","runtime/safety/temperature_integrity.py":"Safety Authority"},
      "AD083":{"rd_control_mode.py":"Recovery & Ownership","rd_live_adoption.py":"Recovery & Ownership","edge_live_adoption.py":"Recovery & Ownership","rd_managed_mix_adoption.py":"Presentation / Telegram workflow"},
      "AD142":{"application/manual_supervisor_use_case.py":"Application"},
      "AD143":{"application/manual_observer_use_case.py":"Application","runtime/safety/thermal_variables.py":"Safety Authority"},
      "AD144":{"application/manual_phase_evidence.py":"Application adapter"},
      "AD145":{"runtime/charge/evidence/manual_delta.py":"Manual Delta Evidence"},
      "AD146":{"application/operator_pause_use_case.py":"Application transaction orchestration"}}
    for stage, paths in approvals.items():
        for p,o in paths.items():
            scope = "Whole-file primary owner, bounded by the narrow exclusions and function-group notes in the source decision."
            add(stage,p,o,scope=scope) if stage == "AD078" else add(stage,p,o)
    # Explicit exclusions/reaffirmations from the ADR decision tables. These are
    # evidence events and never add an owner to the approved-primary set.
    add("AD067","runtime/charge/restore_projection.py","","HELD_NO_FILE_LEVEL_APPROVAL","Mixed scalar persistence and stage timeline projection remain unresolved.")
    for p in ("application/manual_observer_use_case.py","application/manual_phase_evidence.py","application/manual_supervisor_use_case.py","application/operator_pause_use_case.py","runtime/charge/evidence/manual_delta.py"):
        add("AD069",p,"","HELD_NO_FILE_LEVEL_APPROVAL","Explicit AD069 HOLD; later stage-specific decisions may supersede only their own path.")
    add("AD071","application/start_transaction_service.py","","HELD_NO_FILE_LEVEL_APPROVAL","Explicit START service HOLD.")
    add("AD071","application/main_guard_transaction.py","Physical Execution","RECONFIRMED","AD056 primary owner reaffirmed; no new approval.")
    for p,o in {"runtime/charge/strategy/manual_phase_lifecycle.py":"Charge Strategy","runtime/charge/programs/manual.py":"Manual Charge Program"}.items():
        add("AD144",p,o,"RECONFIRMED","Existing owner reaffirmation; not a new approval.")
    add("AD144","runtime/charge/evidence/first_stage_variables.py","First Stage Evidence variables",
        "RECONFIRMED","Owns the near-target voltage margin and fallback MAIN tail-current threshold; existing owner reaffirmation, not a new approval.")
    add("AD083","rd_managed_adoption.py","Recovery & Ownership","HELD_NO_FILE_LEVEL_APPROVAL","Whole-file approval explicitly rejected; AD057 approval superseded.")
    # AD066 approves this bounded Safety module responsibility, but assigns
    # only the named reader function to Persistence. AD076 later rejects
    # file-level approval for persistence.py.
    add("AD066","runtime/charge/strategy/main_guard_admission.py","Safety Authority",
        scope="Bounded module responsibility: MAIN Guard admission contract only; not a broader Safety subsystem approval.",
        doc="docs/RD6018_AD066_MAIN_GUARD_ADMISSION_OWNER_SPLIT_2026-11-15.md",
        heading="Decision", evidence="runtime/charge/strategy/main_guard_admission.py")
    # Stage-level decisions are first-class history and never imply path approval.
    stage_events = [
      ("AD064","TEST_CONTRACT_ONLY","docs/RD6018_AD064_MAIN_GUARD_DIAGNOSTIC_BOUNDARY_TEST_2026-11-15.md","AD064"),
      ("AD066","FUNCTION_GROUP_ONLY","docs/RD6018_AD066_MAIN_GUARD_ADMISSION_OWNER_SPLIT_2026-11-15.md","AD066"),
      ("AD072","HOLD","docs/RD6018_AD072_START_ENABLE_CANCELLATION_DECISION_2026-11-15.md","AD072"),
      ("AD076","NO_FILE_LEVEL_APPROVAL; FUNCTION_GROUP_ONLY","docs/RD6018_AD076_SESSION_PERSISTENCE_FUNCTION_GROUP_DECISIONS_2026-11-15.md","AD076"),
      ("AD086","FUNCTION_GROUP_ONLY","docs/RD6018_AD086_RUNTIME_GUARD_FUNCTION_GROUP_DECISION_2026-11-15.md","AD086"),
      ("AD087","IMPLEMENTATION_ONLY","docs/RD6018_AD087_HANDS_OFF_OFF_D061_FALSE_RESULT_IMPLEMENTATION_DECISION_2026-11-15.md","AD087"),
      ("AD089","RECONFIRMED","docs/RD6018_AD089_SAME_OWNER_CANCELLATION_FENCE_DECISION_2026-11-15.md","AD089"),
      ("AD092","RECONFIRMED","docs/RD6018_AD092_TELEMETRY_SIGNAL_DIAGNOSTICS_OWNER_DECISION_2026-11-15.md","AD092"),
      ("AD147","IMPLEMENTATION_ONLY","docs/RD6018_AD147_OPERATOR_PAUSE_TRANSACTION_2026-11-16.md","AD147"),
    ]
    for stage,status,doc,evidence in stage_events:
        add(stage,"","",status,"Stage decision provenance only; no path-level approval is created.",doc=doc,evidence=evidence)
    by_stage={e["stage"]:e for e in events if not e["path"]}
    by_stage["AD066"].update({"heading":"Decision","line":5,"owner_line":5,
        "scope_notes":[{"heading":"Decision","line":8,"meaning":"main_guard_admission.py"},
                       {"heading":"Decision","line":9,"meaning":"read_canonical_session"}]})
    by_stage["AD076"].update({"heading":"Whole-file decisions","line":5,"owner_line":5,
        "scope_notes":[
            {"heading":"Whole-file decisions","line":9,"meaning":"runtime/charge/session.py | **NO FILE-LEVEL APPROVAL**"},
            {"heading":"Whole-file decisions","line":10,"meaning":"runtime/charge/persistence.py | **NO FILE-LEVEL APPROVAL**"},
            {"heading":"Function-group owner decisions","line":14,"meaning":"Function-group owner decisions"},
            {"heading":"runtime/charge/session.py","line":20,"meaning":"SessionStatus, SessionSnapshot, SessionManager | Sessions & Persistence"},
            {"heading":"runtime/charge/session.py","line":21,"meaning":"TraceIdentitySnapshot, new/project/restore/prepare/apply trace identity | Sessions & Persistence"},
            {"heading":"runtime/charge/session.py","line":22,"meaning":"RestoredSessionDocument | Sessions & Persistence"},
            {"heading":"runtime/charge/session.py","line":23,"meaning":"GuardedRestoreCandidate and guarded activation permit issue/validation | Recovery & Ownership"},
            {"heading":"runtime/charge/session.py","line":24,"meaning":"GuardedPhysicalResumePermit and issue/validation | Safety Authority"},
            {"heading":"runtime/charge/session.py","line":25,"meaning":"set_current_stage and stage-history normalization/restore/clear | Engine / Charge Stages"},
            {"heading":"runtime/charge/persistence.py","line":31,"meaning":"SESSION_FILE, read_canonical_session, clear_session_file, save_session, canonical AUTO schema | Sessions & Persistence"},
            {"heading":"runtime/charge/persistence.py","line":32,"meaning":"atomic_session_write and complete_session_document in session_atomic.py | Sessions & Persistence"},
            {"heading":"runtime/charge/persistence.py","line":33,"meaning":"mark_session_interrupted schema/write | Sessions & Persistence"},
            {"heading":"runtime/charge/persistence.py","line":34,"meaning":"retire_controller_session tombstone write/readback | Sessions & Persistence"},
            {"heading":"runtime/charge/persistence.py","line":35,"meaning":"managed_storage_ownership_proven | Safety Authority"},
            {"heading":"runtime/charge/persistence.py","line":36,"meaning":"paused_done_resume_is_authorized | Safety Authority / Recovery & Ownership"},
            {"heading":"runtime/charge/persistence.py","line":37,"meaning":"_set_done_outcome and terminal DONE semantic normalization | Engine / Charge Stages"},
            {"heading":"runtime/charge/persistence.py","line":38,"meaning":"enrich_restored_session | Application"},
            {"heading":"runtime/charge/persistence.py","line":39,"meaning":"restore_session | Sessions & Persistence (canonical restore coordinator)"},
            {"heading":"runtime/charge/persistence.py","line":41,"meaning":"whole-file decision remains NO FILE-LEVEL APPROVAL"}]})
    return events

def parse_porcelain_z(data: bytes):
    """Return path -> XY status from git status --porcelain -z, including renames."""
    if not data:
        return {}  # A clean commit has no porcelain records, not a malformed stream.
    if not data.endswith(b"\0"): raise ValueError("porcelain -z stream is not NUL terminated")
    parts=data.decode("utf-8","surrogateescape").split("\0")
    result={}; i=0
    while i < len(parts):
        item=parts[i]; i+=1
        if not item: continue
        if len(item)<4 or item[2]!=" ": raise ValueError(f"invalid porcelain record: {item!r}")
        xy=item[:2]; path=item[3:]
        result[path]=xy
        if "R" in xy or "C" in xy:
            if i>=len(parts) or not parts[i]: raise ValueError("rename/copy record missing source path")
            result[parts[i]]="R" if "R" in xy else "C"; i+=1
    return result

def git_path_state(tracked, status, exists):
    if tracked and not exists: return "deleted"
    if "R" in status: return "renamed"
    if "C" in status: return "copied"
    if tracked and status: return "tracked_modified"
    if tracked: return "tracked"
    if exists: return "untracked"
    return "absent"

def validate_provenance(event, root=ROOT):
    """Validate an event against its exact source path, stage section and line."""
    source_path=root/event["source"]
    if not source_path.is_file(): raise ValueError(f"missing decision source: {event['source']}")
    lines=source_path.read_text(encoding="utf-8").splitlines()
    if event["line"]<1 or event["line"]>len(lines): raise ValueError("incorrect provenance line")
    line=lines[event["line"]-1]
    if event["path"] and event["path"] not in line: raise ValueError("incorrect provenance path")
    if event.get("stage") == "AD078" and event.get("status") == "APPROVED_PRIMARY_OWNER_ONLY":
        if not (line.startswith("|") and "APPROVE" in line and event["path"] in line):
            raise ValueError("AD078 primary approval must cite a Whole-file decisions table row")
        whole_file = next((i for i in range(event["line"] - 1, -1, -1) if lines[i].startswith("## ")), None)
        if whole_file is None or lines[whole_file].strip() != "## Whole-file decisions":
            raise ValueError("AD078 primary approval is outside the Whole-file decisions section")
    if event.get("stage") in {"AD066", "AD076"} and not event["path"]:
        expected = {"AD066": ("## Decision", "FUNCTION_GROUP_ONLY"),
                    "AD076": ("## Whole-file decisions", "NO_FILE_LEVEL_APPROVAL")}[event["stage"]]
        if lines[event["line"] - 1].strip() != expected[0] or expected[1] not in event["status"]:
            raise ValueError(f"{event['stage']} stage provenance must identify its decision boundary")
        for note in event.get("scope_notes", []):
            if note["line"] < 1 or note["line"] > len(lines): raise ValueError("invalid scope-note line")
            nearest=next((l.lstrip("# ").strip() for l in reversed(lines[:note["line"]]) if l.startswith("#")),"")
            if nearest != note["heading"] or note["meaning"].casefold() not in lines[note["line"]-1].casefold():
                raise ValueError("scope-note citation does not match the exact section/line")
    if event["path"] and event["owner"]:
        terms={"Telemetry/Evidence":("Telemetry",),"Safety Authority":("Safety",),"Engine / Charge Stages":("Engine / Charge Stages",),"Application adapter":("Application adapter",),"Manual Delta Evidence":("Manual Delta Evidence",),"Application transaction orchestration":("Application",),"Presentation / Telegram workflow":("Presentation / Telegram workflow",)}.get(event["owner"],(event["owner"],))
        owner_line_no=event.get("owner_line",event["line"])
        if owner_line_no<1 or owner_line_no>len(lines): raise ValueError("incorrect owner evidence line")
        owner_line=lines[owner_line_no-1]
        if owner_line_no!=event["line"]:
            # Separate owner/path evidence is accepted only in the exact bounded
            # subsection whose heading is cited by both lines.
            nearest_path=next((l for l in reversed(lines[:event["line"]]) if l.startswith("### ")),None)
            nearest_owner=next((l for l in reversed(lines[:owner_line_no]) if l.startswith("### ")),None)
            if nearest_path is None or nearest_path!=nearest_owner: raise ValueError("owner evidence belongs to unrelated subsection")
        if not any(t.casefold() in owner_line.casefold() for t in terms): raise ValueError("owner not associated with cited path")
    if event["stage"] in {f"AD{i:03d}" for i in range(62,148)}:
        expected=f"RD6018_{event['stage']}_"
        if expected not in source_path.name and "MODULARIZATION_MASTER_PLAN" not in source_path.name:
            raise ValueError("wrong decision source for stage")
    # Heading must be the nearest actual markdown heading above the cited line.
    nearest=next((l.lstrip("# ").strip() for l in reversed(lines[:event["line"]]) if l.startswith("#")),"")
    if nearest!=event["heading"]: raise ValueError("incorrect provenance heading")
    if event["path"]:
        before="\n".join(lines[:event["line"]])
        if event["stage"] not in before and event["stage"].replace("AD","AD-") not in before: raise ValueError("wrong decision stage")
    return True

def current_owner(history):
    """Return current primary owner; explicit AD083 hold supersedes AD057."""
    if any(e["stage"]=="AD083" and e["status"].startswith("HELD") for e in history): return ""
    approved=[e for e in history if e["status"]=="APPROVED_PRIMARY_OWNER_ONLY"]
    owners={e["owner"] for e in approved}
    if len(owners)>1: raise ValueError("conflicting owner decision")
    return approved[-1]["owner"] if approved else ""

def build():
    if not CHRONOLOGY.is_file(): raise FileNotFoundError(CHRONOLOGY)
    module=_ad014_module()
    fields, base=module.build_rows()
    if len(base)!=499 or len({x["path"] for x in base})!=499: raise ValueError("canonical AD014 rebuild is not 499 unique paths")
    baseline={r["path"]:r for r in base}
    prior=module.AD006_APPROVALS | module.AD008_APPROVALS | module.AD010_APPROVALS | module.AD014_APPROVALS
    if len(prior)!=26: raise ValueError("canonical AD014 approval count drift")
    # Historical sidecars are read-only inputs. Canonical AD014 rows are
    # rebuilt in memory from AD012; this builder never writes these files.
    for path in (AD010, AD012, AD014):
        if not path.is_file(): raise FileNotFoundError(path)
    ev=_events()
    git_tracked=set(subprocess.check_output(["git","ls-files","-z"],cwd=ROOT).decode().split("\0"))
    git_status=subprocess.check_output(["git","status","--porcelain=v1","-z","--untracked-files=all"],cwd=ROOT)
    state=parse_porcelain_z(git_status)
    paths=set(baseline)|{e["path"] for e in ev if e["path"]}
    current={}
    for p in paths:
        exists=(ROOT/p).is_file()
        st=state.get(p,"")
        current[p]={"ad012_membership":"AD012" if p in baseline else "LATER_DECISION_EVENT","worktree_exists":exists,"git_status":git_path_state(p in git_tracked,st,exists)}
    by={p:[] for p in paths}
    for p,o in prior.items():
        # canonical baseline's original metadata and manifest are authoritative
        by[p].append({"stage":"AD014_CANONICAL","owner":o,"status":"APPROVED_PRIMARY_OWNER_ONLY","scope":"Canonical generator approval; primary owner only.","source":"tools/architecture/reconcile_owner_decisions_ad014.py","heading":"AD014 approval manifest","line":0})
    # Preserve events from source report even where owner approval occurred before this event set.
    for e in ev:
        if e["path"]: by[e["path"]].append(e)
    stage_history=[e for e in ev if not e["path"]]
    current_approvals={}
    for p,history in by.items():
        owner=current_owner(history)
        if owner: current_approvals[p]=owner
    for e in ev:
        if e["status"]=="APPROVED_PRIMARY_OWNER_ONLY" and not e["path"]: raise ValueError("pathless primary approval")
        validate_provenance(e)
    rows=[]
    for p in sorted(paths):
        rows.append({"path":p,"baseline_source_metadata":json.dumps(baseline.get(p),ensure_ascii=False,sort_keys=True,separators=(",",":")) if p in baseline else "",**current[p],"current_primary_approval":current_approvals.get(p,""),"resolved_final_owner":"","decision_history":json.dumps(by[p],ensure_ascii=False,sort_keys=True,separators=(",",":"))})
    counts={"AD012_paths":len(baseline),"later_approved_paths_not_AD012":len(set(evx["path"] for evx in ev if evx["path"] and evx["status"]=="APPROVED_PRIMARY_OWNER_ONLY")-set(baseline)),"ledger_paths":len(paths),"current_existing_ledger_paths":sum(x["worktree_exists"] for x in current.values()),"unique_current_primary_approvals":len(current_approvals),"AD056_AD057_decision_events":17,"AD142_AD146_new_approvals":6,"stage_only_events":sum(not e["path"] for e in ev)}
    return rows,counts

def render_csv(rows):
    from io import StringIO
    f=StringIO(newline=""); w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator="\n"); w.writeheader();w.writerows(rows);return f.getvalue()

def render_report(rows,counts):
    return f"""# P1-AD148T — Deterministic owner ledger and worktree crosswalk\n\nDate: 2026-11-17. Diagnostic source registry; not release acceptance.\n\n## Reconstruction and provenance\n\nThe builder treats historical AD010/AD012/AD014 sidecars as read-only inputs and rebuilds canonical AD014 rows **in memory** from AD012 using `reconcile_owner_decisions_ad014.build_rows()`. It does not write, normalize, regenerate-overwrite, or stage any historical sidecar. The in-memory reconstruction yielded exactly 499 unique paths and 26 canonical approvals; the materialized AD014 artifact is not used as the seed.\n\nEvery ledger path retains its exact AD012 row as JSON in `baseline_source_metadata`. Each later event contains its status, path, owner, scope, source document, nearest heading and exact line number. Events and unique current approvals are counted separately. `resolved_final_owner` remains empty: primary owner evidence does not determine a final owner. AD083 records `rd_managed_adoption.py` as `HELD_NO_FILE_LEVEL_APPROVAL`, superseding its earlier AD057 approval. Reaffirmations do not create new approvals.\n\n## Counts\n\n- AD012 baseline: **{counts['AD012_paths']}** paths.\n- Later explicitly approved paths outside AD012: **{counts['later_approved_paths_not_AD012']}**.\n- Ledger paths (union): **{counts['ledger_paths']}**.\n- Existing worktree files among ledger paths: **{counts['current_existing_ledger_paths']}** (path-scoped; not repository-wide).\n- Unique current primary approvals after AD083 HOLD: **{counts['unique_current_primary_approvals']}**.\n- AD056/AD057 decisions: 17; AD142–AD146 explicit new approvals: 6. AD144 confirmations and AD147 acceptance are not counted as new approvals.\n\nThe 499 baseline, later approvals, and current worktree file count answer different questions. The ledger includes deleted or absent paths for historical traceability; it does not force their sum to equal the current file count. Git status and existence are per-path in the CSV.\n\nAD066/AD076 reconciliation: AD066 `## Decision` assigns the bounded `main_guard_admission.py` module responsibility to Safety Authority (line 8), counted as one path-level primary approval. AD066 assigns only `read_canonical_session` (line 9) to Persistence; it does not approve the full `persistence.py` path. AD076's later `## Whole-file decisions` expressly records `persistence.py` as NO FILE-LEVEL APPROVAL (line 10), while its function-group table assigns the reader function to Persistence (line 31). Function-group ownership does not create file approval. The count changes from AD148W's 80 to **{counts['unique_current_primary_approvals']}** solely from the bounded AD066 Safety module decision. AD078's six approvals remain unchanged.\n\nAD144 also names `runtime/charge/evidence/first_stage_variables.py` as an existing owner of the near-target voltage margin and fallback MAIN tail-current threshold. The ADR gives the descriptive label ‘First Stage Evidence variables,’ not a department label; the ledger preserves that wording without inferring a department. This is a reaffirmation only.\n\n## Scope and limits — review HOLD\n\nStage-only events are stored once in `mod_p1_owner_ledger_events_ad148v_20261117.json`, not copied into path rows. The full inventory of existing ADR documents AD062–AD147, their explicit disposition, and section/line provenance is in `mod_p1_owner_ledger_adr_coverage_ad148v_20261117.json`; nonexistent stages are not synthesized. AD078's six whole-file approvals are listed separately from function-group scope notes. AD083 HOLD supersedes AD057 for `rd_managed_adoption.py`. Independent architecture review of source classifications remains required. No final-owner assignment is inferred. No production/hardware acceptance is implied.

Porcelain parsing handles the NUL-delimited destination/source records for rename/copy plus deletion and untracked states. This remains diagnostic: no source path is auto-approved, and the historical AD010/AD012/AD014 artifacts are read-only and untouched.\n"""

def build_coverage(events=None):
    events=_events() if events is None else events
    import re
    coverage=[]
    for p in sorted((ROOT/"docs").glob("RD6018_AD*.md")):
        m=re.match(r"RD6018_AD(\d{3})_",p.name)
        if not m or not 62 <= int(m.group(1)) <= 147: continue
        stage=f"AD{int(m.group(1)):03d}"
        ev=[e for e in events if e["stage"]==stage]
        lines=p.read_text(encoding="utf-8").splitlines()
        heading=next((line.lstrip("# ").strip() for line in lines if line.startswith("#")), "")
        sections=[]
        for e in ev:
            citation={"heading":e["heading"],"line":e["line"]}
            if citation not in sections: sections.append(citation)
        item={"stage":stage,"source":p.relative_to(ROOT).as_posix(),"disposition":";".join(sorted({e["status"] for e in ev})) or "REVIEW_REQUIRED_HOLD","sections":sections or [{"heading":heading,"line":1}]}
        if stage == "AD078":
            whole=next(i for i,line in enumerate(lines) if line.strip()=="## Whole-file decisions")
            function=next(i for i,line in enumerate(lines) if line.strip()=="## Function-group decisions and boundaries")
            function_end=next((i for i in range(function+1,len(lines)) if lines[i].startswith("## ")),len(lines))
            item["primary_decisions"]=[{"path":e["path"],"owner":e["owner"],"decision":lines[e["line"]-1].split("|")[2].strip(),"line":e["line"]} for e in ev if e["status"]=="APPROVED_PRIMARY_OWNER_ONLY"]
            item["scope_notes"]=[{"heading":lines[function].removeprefix("## ").strip(),"line":function+1}]+[{"heading":lines[i].removeprefix("### ").strip(),"line":i+1} for i in range(function+1,function_end) if lines[i].startswith("### ")]
        if stage == "AD076":
            item["whole_file_decisions"]=[{"path":lines[i].split("|")[1].strip(),"decision":"NO FILE-LEVEL APPROVAL","line":i+1} for i in (8,9)]
            item["scope_notes"]=[{"heading":n["heading"],"line":n["line"],"meaning":n["meaning"]} for n in ev[0]["scope_notes"]]
        coverage.append(item)
    return coverage

def write():
    rows,counts=build(); data=render_csv(rows); report=render_report(rows,counts)
    CSV_OUT.write_text(data,encoding="utf-8",newline=""); REPORT_OUT.write_text(report,encoding="utf-8",newline="")
    events=_events()
    stage_events=[e for e in events if not e["path"]]
    coverage=build_coverage(events)
    EVENTS_OUT.write_text(json.dumps({"schema":"ad148v-owner-events-v1","events":stage_events},ensure_ascii=False,sort_keys=True,indent=2)+"\n",encoding="utf-8",newline="")
    AUDIT_OUT.write_text(json.dumps({"schema":"ad148v-adr-coverage-v1","adr_coverage":coverage},ensure_ascii=False,sort_keys=True,indent=2)+"\n",encoding="utf-8",newline="")

if __name__=="__main__": write()
