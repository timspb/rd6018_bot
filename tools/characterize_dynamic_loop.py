#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from probe_characterization import (  # noqa: E402
    characterization_to_mapping,
    characterize_probe_samples,
    load_characterization_jsonl,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Characterize actual RD6018/HA sampling cadence, noise, observed quantization "
            "and a labeled current-reduction response without choosing production thresholds."
        )
    )
    parser.add_argument("samples", type=Path, help="JSONL samples with labeled phases")
    parser.add_argument("--baseline-phase", default="baseline")
    parser.add_argument("--stepped-phase", default="stepped")
    parser.add_argument("--tail-count", type=int, default=3)
    parser.add_argument("--output", type=Path, help="optional JSON report path")
    args = parser.parse_args()

    try:
        samples = load_characterization_jsonl(args.samples.read_text(encoding="utf-8"))
        report = characterize_probe_samples(
            samples,
            baseline_phase=args.baseline_phase,
            stepped_phase=args.stepped_phase,
            tail_count=args.tail_count,
        )
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"characterization failed: {exc}", file=sys.stderr)
        return 2

    rendered = json.dumps(
        characterization_to_mapping(report),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
