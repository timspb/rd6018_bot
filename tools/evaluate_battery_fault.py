#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow running as `python tools/evaluate_battery_fault.py cases.jsonl` from repo root.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from battery_fault_calibration import (  # noqa: E402
    calibration_summary_to_mapping,
    evaluate_fault_cases,
    load_calibration_jsonl,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate current V2 bank-fault scoring against labeled JSONL cases without tuning thresholds."
    )
    parser.add_argument("cases", type=Path, help="JSONL calibration cases")
    parser.add_argument("--output", type=Path, help="optional JSON report path")
    args = parser.parse_args()

    cases = load_calibration_jsonl(args.cases.read_text(encoding="utf-8"))
    summary = evaluate_fault_cases(cases)
    report = calibration_summary_to_mapping(summary)
    rendered = json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")

    # A false automatic-HV block or a missed labeled block is a safety-significant
    # calibration mismatch. Ordinary level mismatches remain visible in the report
    # but do not make the CLI pretend a threshold change is automatically correct.
    if summary.unexpected_hv_blocks or summary.missed_hv_blocks:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
