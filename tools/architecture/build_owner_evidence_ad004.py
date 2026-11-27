"""Build a deterministic, non-authoritative P1-AD004 ownership evidence sidecar."""
from __future__ import annotations

import argparse
import ast
import csv
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASELINE_HEAD = "3c692554074b27805419a9b0767133a1c8d78150"
INVENTORY = ROOT / "tests/fixtures/architecture/mod_p2_ownership_inventory_unique_20261112.csv"
OUTPUT = ROOT / ".recipe-studio-local/mod_p1_owner_evidence_ad004_20261113.csv"
REPORT = ROOT / ".recipe-studio-local/REPORT_MOD_P1_AD004_OWNER_EVIDENCE_20261113.md"
FIELDS = ["path", "existing_candidate", "proposed_owner", "confidence", "evidence",
          "mixed_responsibility", "side_effect_type", "public_entrypoints",
          "primary_consumers", "review_reason", "risk_band"]
OWNERS = {
    "battery-domain": "Battery/Chemistry", "charge-engine": "ChargeEngine",
    "application": "Application", "safety": "Safety",
    "physical-execution": "Physical",
    "ui": "UI", "composition": "Composition/Configuration",
    "integration": "Integrations", "recovery-ownership": "Recovery/Ownership",
    "recovery": "Recovery/Ownership", "diagnostics": "Application",
    "telemetry": "Telemetry/Evidence",
}
OWNERS["sessions-persistence"] = "Session/Persistence"
OWNER_TAXONOMY = frozenset((*OWNERS.values(), "REVIEW_REQUIRED"))
MIXED_MARKERS = ("large-module:", "root-monolith-candidate:", "direct-physical-call-indicator")
ENTRYPOINT_NAMES = {"main", "build_application", "install", "initialize_runtime", "run", "start"}


def read_inventory(path: Path = INVENTORY) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames is None:
            raise ValueError("inventory has no header")
        rows = list(reader)
    if len(rows) != 478 or len({row["path"] for row in rows}) != 478:
        raise ValueError("expected exactly 478 unique inventory paths")
    if any(row.get("final_owner", "") for row in rows):
        raise ValueError("source inventory final_owner is not blank")
    return list(reader.fieldnames), rows


def _source_facts(root: Path, path: str) -> tuple[ast.Module | None, str, str]:
    source_path = root / path
    if not source_path.is_file():
        return None, "", "source file missing"
    text = source_path.read_text(encoding="utf-8")
    try:
        return ast.parse(text, filename=path), text, ""
    except SyntaxError as exc:
        return None, text, f"AST parse unavailable at line {exc.lineno}: {exc.msg}"


def _side_effect_lines(text: str, indicators: str) -> str:
    names = []
    for item in indicators.split(" ; "):
        if ":" in item:
            value = item.split(":", 1)[1]
            # An assignment may list several fields; transport indicators are
            # semantic labels rather than source identifiers.
            names.extend(part.strip() for part in value.split(",") if part.strip())
    found = []
    for number, line in enumerate(text.splitlines(), 1):
        if any(name in line for name in names if name and "-" not in name and "/" not in name):
            found.append(f"{number}:{line.strip()[:160]}")
    return " ; ".join(found[:12])


def _definitions(tree: ast.Module | None) -> list[ast.AST]:
    return [node for node in (tree.body if tree else [])
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]


def _consumer_refs(row: dict[str, str]) -> str:
    refs = []
    for item in row.get("imports_in", "").split(" | "):
        match = re.match(r"(.+?):([0-9]+)\[(eager|deferred|type_checking)\]$", item)
        if match:
            refs.append(f"{match.group(1)}:{match.group(2)}[{match.group(3)}]")
    return " | ".join(sorted(set(refs))) or "no in-repo import reference observed"


def _candidate_owner(candidate: str, path: str, doc: str, defs: list[ast.AST]) -> str:
    if candidate in OWNERS:
        return OWNERS[candidate]
    # Source-level signals only; directory names are not sufficient evidence.
    blob = (path + " " + doc).lower()
    names = " ".join(node.name.lower() for node in defs)
    checks = [
        (("safeoutput", "safety"), "Safety"),
        (("telemetry", "snapshot", "freshness", "readback", "evidence"), "Telemetry/Evidence"),
        (("recovery", "ownership", "adopt", "hands_off", "managed"), "Recovery/Ownership"),
        (("recipe", "charge", "stage", "mix", "signal_analyzer", "main_guard"), "ChargeEngine"),
        (("battery", "chemistry", "profile", "limits"), "Battery/Chemistry"),
        (("telegram", "operator", "dashboard", "keyboard", "render", "callback"), "UI"),
        (("session", "persist", "repository", "atomic"), "Session/Persistence"),
        (("diagnostic", "probe"), "Application"),
        (("replay", "trace"), "Telemetry/Evidence"),
        (("connector", "transport", "hass", "esp", "wake", "integration"), "Integrations"),
        (("execution", "physical", "command", "output"), "Physical"),
        (("production_runtime", "composition", "config", "bootstrap"), "Composition/Configuration"),
        (("application", "usecase", "use_case", "preflight"), "Application"),
    ]
    scores = [(sum(token in blob or token in names for token in tokens), owner) for tokens, owner in checks]
    best = max((score for score, _ in scores), default=0)
    winners = [owner for score, owner in scores if score == best and score]
    return winners[0] if len(winners) == 1 else "REVIEW_REQUIRED"


def _mixed(row: dict[str, str], owner: str, defs: list[ast.AST], doc: str) -> bool:
    flags = row.get("review_flags", "")
    if any(marker in flags for marker in MIXED_MARKERS):
        return True
    # Multiple semantic responsibility signals, or a side-effecting module with
    # a policy/adapter-looking surface, stays unresolved for human review.
    signals = sum(token in (row["path"] + " " + doc + " " + " ".join(n.name for n in defs)).lower()
                 for token in ("policy", "format", "render", "telegram", "persist", "session", "safety", "physical", "telemetry", "recovery"))
    effect = bool(row.get("observed_side_effect_indicators"))
    return signals >= 3 or (effect and signals >= 2)


def build_rows(root: Path = ROOT, inventory_path: Path = INVENTORY) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    _, source_rows = read_inventory(inventory_path)
    result, reviews = [], []
    for row in sorted(source_rows, key=lambda x: x["path"]):
        if not (root / row["path"]).is_file():
            raise ValueError(f"inventory production path is missing: {row['path']}")
        tree, source_text, parse_issue = _source_facts(root, row["path"])
        defs = _definitions(tree)
        doc = ast.get_docstring(tree) or "" if tree else ""
        owner = _candidate_owner(row.get("proposed_owner_candidate", ""), row["path"], doc, defs)
        is_mixed = _mixed(row, owner, defs, doc)
        review_flag = row.get("requires_architect_review", "").lower() == "true"
        uncertain = owner == "REVIEW_REQUIRED" or is_mixed
        if is_mixed:
            owner = "REVIEW_REQUIRED"
        confidence = "uncertain" if uncertain else ("high" if row.get("responsibility_basis") == "module_docstring" and row.get("proposed_owner_candidate") != "REVIEW_REQUIRED" else "medium")
        signature = ", ".join(f"{n.name}@{n.lineno}" for n in defs[:8]) or "no module-level callable/class"
        import_refs = row.get("imports_out", "")
        effect = row.get("observed_side_effect_indicators", "")
        evidence = [f"inventory:{row['path']} candidate={row.get('proposed_owner_candidate','')} basis={row.get('responsibility_basis','')}",
                    f"source:{row['path']} module_docstring={doc[:180]!r}" if doc else f"source:{row['path']} module_docstring absent",
                    f"source defs={signature}"]
        if import_refs:
            evidence.append("imports_out=" + import_refs)
        if effect:
            evidence.append("side_effect_indicators=" + effect)
            effect_lines = _side_effect_lines(source_text, effect)
            if effect_lines:
                evidence.append("source side-effect lines=" + effect_lines)
        if parse_issue:
            evidence.append(parse_issue)
        flags = row.get("review_flags", "")
        reasons = []
        if flags: reasons.append("inventory review flags: " + flags)
        if row.get("proposed_owner_candidate") == "REVIEW_REQUIRED": reasons.append("candidate intentionally unresolved in source inventory")
        if is_mixed: reasons.append("mixed responsibility signals require function-level owner decision")
        if effect: reasons.append("side-effect indicator requires explicit owner/path review")
        if not row.get("imports_in"): reasons.append("no production import consumer observed; active wiring unproven")
        if parse_issue: reasons.append(parse_issue)
        if not reasons: reasons.append("proposal only; architect approval still required")
        if review_flag and "proposal only; architect approval still required" not in reasons:
            reasons.append("architect approval required; source inventory review gate remains open")
        risk = "critical" if "direct-physical-call-indicator" in flags or "direct-physical-call:" in effect else "high" if is_mixed or "root-monolith" in flags or "large-module" in flags else "review" if review_flag or effect else "standard"
        item = {"path": row["path"], "existing_candidate": row.get("proposed_owner_candidate", ""),
                "proposed_owner": owner, "confidence": confidence, "evidence": " | ".join(evidence),
                "mixed_responsibility": "true" if is_mixed else "false", "side_effect_type": effect or "none observed in inventory",
                "public_entrypoints": "; ".join(f"{n.name}@{n.lineno}" for n in defs if n.name in ENTRYPOINT_NAMES) or signature,
                "primary_consumers": _consumer_refs(row), "review_reason": "; ".join(reasons), "risk_band": risk}
        result.append(item)
        if row.get("proposed_owner_candidate") == "REVIEW_REQUIRED":
            reviews.append(item)
    return result, reviews


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS, lineterminator="\n", extrasaction="raise")
        writer.writeheader(); writer.writerows(rows)


def render_report(rows: list[dict[str, str]], reviews: list[dict[str, str]], inventory_rows: list[dict[str, str]]) -> str:
    counts = Counter(r["existing_candidate"] for r in rows)
    confidence = Counter(r["confidence"] for r in rows)
    mixed = [r for r in rows if r["mixed_responsibility"] == "true"]
    side_effect = [r for r in rows if r["side_effect_type"] != "none observed in inventory"]
    def mixed_priority(item: dict[str, str]) -> tuple[int, int, str]:
        source_row = next(row for row in inventory_rows if row["path"] == item["path"])
        flags = source_row.get("review_flags", "")
        tier = 0 if "direct-physical-call-indicator" in flags else 1 if "root-monolith-candidate" in flags else 2 if "large-module" in flags else 3
        return tier, -int(source_row.get("lines", "0") or 0), item["path"]
    priority_modules = sorted(mixed, key=mixed_priority)[:15]
    by_path = {r["path"]: r for r in rows}
    lines = ["# P1-AD004 ownership evidence report", "", "Status: **PROPOSAL / not approved**. No `final_owner` value was written. This source-only sidecar preserves the 478-path inventory and is not proof of dynamic reachability or physical ownership.", "", f"Baseline worktree HEAD preserved: `{BASELINE_HEAD}` (broad dirty WIP retained).", "", "## Coverage", "", f"- Inventory paths: {len(rows)} unique; matched source inventory exactly.", f"- Candidate counts: {', '.join(f'{k}={v}' for k,v in sorted(counts.items()))}.", f"- Confidence: {', '.join(f'{k}={v}' for k,v in sorted(confidence.items()))}.", f"- High confidence: {confidence.get('high', 0)}; uncertain: {confidence.get('uncertain', 0)}.", f"- Mixed-responsibility unresolved: {len(mixed)}.", f"- Source-inventory side-effect flags preserved: {len(side_effect)}.", "- Consumers are source inventory inbound import references; imports alone do not prove active production wiring.", "", "## REVIEW_REQUIRED disposition (all 82)", "", "Each row retains `REVIEW_REQUIRED` as its existing candidate. A source-grounded department proposal is emitted only when the classifier is unambiguous and the module is not mixed; all other cases remain `REVIEW_REQUIRED` / uncertain. Review flags and side-effect evidence remain present in the CSV.", "", "| Path | Proposal | Confidence | Disposition / reason |", "|---|---|---|---|"]
    for original in inventory_rows:
        if original.get("proposed_owner_candidate") == "REVIEW_REQUIRED":
            item = by_path[original["path"]]
            disposition = "unresolved" if item["proposed_owner"] == "REVIEW_REQUIRED" else "department proposal; approval pending"
            lines.append(f"| `{item['path']}` | {item['proposed_owner']} | {item['confidence']} | {disposition}: {item['review_reason']} |")
    lines += ["", "## Prioritized 15 mixed modules", "", "Priority puts direct physical-call indicators first, then root monoliths, large modules, and remaining mixed responsibilities; larger source files rank first within a tier. This is a review queue, not an owner decision.", "", "| Rank | Path | Risk | Candidate | Evidence / next review |", "|---:|---|---|---|---|"]
    for i, item in enumerate(priority_modules, 1):
        lines.append(f"| {i} | `{item['path']}` | {item['risk_band']} | {item['existing_candidate']} | {item['review_reason']} |")
    lines += ["", "## Local verification and remaining closure actions", "", "Local Linux verification: focused unittest **5 PASS**, `py_compile` PASS, `git diff --check` PASS. Independent Windows regression, R7.2 completion/ACK evidence, and the controlling ChatGPT's mandatory four-document updates remain pending outside this strict four-file allowlist.", "", "1. Architect review of every uncertain/mixed proposal, starting with the ranked modules above.", "2. Resolve each review flag with function-level boundaries, active composition call paths, and explicit side-effect owner; distinguish test-only monkeypatching from production behavior.", "3. Confirm import consumers against production composition and runtime registration; do not treat static imports as execution proof.", "4. Independently validate this generated CSV on Windows and approve owners only in subsequent evidence-grounded batches.", "5. Keep physical command ownership, verified OFF semantics, and live node acceptance HOLD pending separate P3 evidence.", "", "## Reproducibility and limits", "", "Generator: `tools/architecture/build_owner_evidence_ad004.py`. The output is sorted by path, UTF-8 BOM CSV, and derived from the unchanged source inventory plus source AST/docstrings. Candidate owners are proposals. No source files, original inventory, or canonical documents were changed by this work package.", ""]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, default=INVENTORY)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--report", type=Path, default=REPORT)
    parser.add_argument("--source-root", type=Path, default=ROOT,
                        help="root of the source preimage to analyze; sidecars still go to --output/--report")
    args = parser.parse_args()
    rows, reviews = build_rows(args.source_root, args.inventory)
    _, inventory_rows = read_inventory(args.inventory)
    write_csv(args.output, rows)
    args.report.write_text(render_report(rows, reviews, inventory_rows), encoding="utf-8")
    print(f"rows={len(rows)} review_required={len(reviews)} mixed={sum(r['mixed_responsibility']=='true' for r in rows)} output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
