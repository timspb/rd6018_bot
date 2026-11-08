#!/usr/bin/env python3
"""Local Recipe Studio check/save against existing versioned libraries.

No network listener, charge START, output command or embedded device access.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import MAX_MANUAL_VOLTAGE
from runtime.safety.variables import MAX_STAGE_CURRENT_A
from runtime.charge.programs.recipe_library import RecipeLibrary
from runtime.charge.programs.native_recipe_draft_library import NativeRecipeDraftLibrary
from runtime.charge.programs.recipe_studio_import import (
    inspect_step_document, publish_step_document,
    inspect_native_document, publish_native_document,
)


def _reject_constant(value: str) -> None:
    raise ValueError("nonfinite JSON value: " + value)


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Offline canonical RD6018 recipe check/save")
    commands = parser.add_subparsers(dest="action", required=True)
    for action in ("check", "save", "check-native", "save-native"):
        cmd = commands.add_parser(action)
        cmd.add_argument("--file", required=True, type=Path, help="canonical exported JSON")
        if action in ("save", "save-native"):
            cmd.add_argument("--library-root", required=True, type=Path,
                             help="explicit library folder; never inferred from node104")
    args = parser.parse_args(argv)
    try:
        with args.file.open("r", encoding="utf-8") as handle:
            document = json.load(handle, parse_constant=_reject_constant)
        if args.action == "check":
            result = inspect_step_document(
                document,
                max_voltage_v=float(MAX_MANUAL_VOLTAGE),
                max_current_a=float(MAX_STAGE_CURRENT_A.default),
            )
        elif args.action == "save":
            library = RecipeLibrary(
                args.library_root,
                max_voltage_v=float(MAX_MANUAL_VOLTAGE),
                max_current_a=float(MAX_STAGE_CURRENT_A.default),
            )
            result = publish_step_document(library, document)
        elif args.action == "check-native":
            result = inspect_native_document(document)
        else:
            result = publish_native_document(NativeRecipeDraftLibrary(args.library_root), document)
        native = args.action.endswith("-native")
        output = {
            "status": "SAVED" if args.action.startswith("save") else "VALIDATED",
            "kind": "native_draft" if native else "step_recipe",
            "recipe_id": result.name if native else result.recipe.recipe_id,
            "version": result.version if native else result.recipe.version,
            "base_recipe_id": result.draft.base_recipe_id if native else None,
            "digest": None if native else result.recipe.digest,
            "start_eligible_structure": None if native else result.start_eligible,
            "warnings": [] if native else result.warnings,
            "physical_start_authorized": False,
        }
        print(json.dumps(output, ensure_ascii=False, sort_keys=True))
        return 0
    except (ValueError, TypeError, KeyError, OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "REJECTED", "reason": str(exc)},
                         ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(run())
