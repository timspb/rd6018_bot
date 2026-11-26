"""Normalize repeated textual import observations in the P2 ownership CSV."""
from __future__ import annotations

import argparse
import csv
import re
from collections import Counter
from pathlib import Path
from typing import Iterable

REFERENCE_RE = re.compile(r"^(?P<path>.+):(?P<line>[1-9][0-9]*)\[(?P<kind>eager|deferred|type_checking)\]$")
REQUIRED_COLUMNS = {
    "path", "imports_in_count", "imports_in", "imports_out_count", "imports_out",
    "final_owner",
}


def _identity(reference: str) -> tuple[str, int, str]:
    match = REFERENCE_RE.fullmatch(reference.strip())
    if not match:
        raise ValueError(f"invalid import reference: {reference!r}")
    return match.group("path"), int(match.group("line")), match.group("kind")


def _references(value: str) -> list[str]:
    if not value:
        return []
    refs = [part.strip() for part in value.split(" | ")]
    if any(not ref for ref in refs):
        raise ValueError("empty import reference in non-empty list")
    # Same textual reference identity is deduplicated; first spelling is retained.
    by_identity: dict[tuple[str, int, str], str] = {}
    for ref in refs:
        by_identity.setdefault(_identity(ref), ref)
    return [by_identity[key] for key in sorted(by_identity)]


def _module(path: str) -> str:
    parts = path.removesuffix(".py").split("/")
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def normalize_rows(rows: Iterable[dict[str, str]]) -> tuple[list[dict[str, str]], dict[str, object]]:
    normalized: list[dict[str, str]] = []
    in_edges: set[tuple[str, str, str]] = set()
    out_edges: set[tuple[str, str, str]] = set()
    occurrence_totals = Counter()
    removed = Counter()
    owners_before: dict[str, str] = {}
    for original in rows:
        row = dict(original)
        path = row["path"]
        owners_before[path] = row["final_owner"]
        source_module = _module(path)
        for direction in ("in", "out"):
            field = f"imports_{direction}"
            old = row[field].split(" | ") if row[field] else []
            refs = _references(row[field])
            removed[direction] += len(old) - len(refs)
            row[field] = " | ".join(refs)
            row[f"imports_{direction}_count"] = str(len(refs))
            row[f"imports_{direction}_distinct_occurrence_count"] = str(len(refs))
            occurrence_totals[direction] += len(refs)
            if direction == "in":
                for ref in refs:
                    source_path, _, kind = _identity(ref)
                    in_edges.add((_module(source_path), source_module, kind))
            else:
                for ref in refs:
                    target_path, _, kind = _identity(ref)
                    out_edges.add((source_module, _module(target_path), kind))
        normalized.append(row)
    normalized.sort(key=lambda item: item["path"])
    if len({row["path"] for row in normalized}) != len(normalized):
        raise ValueError("duplicate inventory paths")
    if any(row["final_owner"] != owners_before[row["path"]] for row in normalized):
        raise AssertionError("final_owner changed during normalization")
    if in_edges != out_edges:
        raise ValueError("inbound and outbound normalized module edges disagree")
    stats: dict[str, object] = {
        "rows": len(normalized),
        "distinct_occurrences_in": occurrence_totals["in"],
        "distinct_occurrences_out": occurrence_totals["out"],
        "exact_duplicates_removed_in": removed["in"],
        "exact_duplicates_removed_out": removed["out"],
        "distinct_module_edges_in": len(in_edges),
        "distinct_module_edges_out": len(out_edges),
        "module_edges_by_kind": dict(sorted(Counter(edge[2] for edge in in_edges).items())),
    }
    return normalized, stats


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames is None or not REQUIRED_COLUMNS.issubset(reader.fieldnames):
            raise ValueError("input CSV is missing required columns")
        rows = list(reader)
        if any(None in row for row in rows):
            raise ValueError("input CSV row has extra fields")
        return list(reader.fieldnames), rows


def write_csv(path: Path, columns: list[str], rows: list[dict[str, str]]) -> None:
    added = ["imports_in_distinct_occurrence_count", "imports_out_distinct_occurrence_count"]
    output_columns = columns + [column for column in added if column not in columns]
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=output_columns, lineterminator="\n", extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    columns, source_rows = read_csv(args.input)
    rows, stats = normalize_rows(source_rows)
    write_csv(args.output, columns, rows)
    for key, value in stats.items():
        print(f"{key}={value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
