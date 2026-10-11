"""Build an offline callback acceptance matrix for the installed V3 composition.

This tool only imports the composition and evaluates aiogram filters against synthetic
CallbackQuery-shaped objects. It never feeds Telegram, calls a Bot API, starts the
runtime, mutates a lease, or touches an RD connector. The actual handler invocations
for the safety-bounded scenarios live in ``tests/test_ui_callback_acceptance.py``.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import subprocess
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
REPORT_PATH = ROOT / "docs" / "UI_CALLBACK_ACCEPTANCE_MATRIX_20261010.json"

import bot  # noqa: E402,F401 - canonical composition is the inventory authority
import production_bot_ui  # noqa: E402
from runtime import production_runtime as app  # noqa: E402
from runtime.ui.telegram.charge import CHARGE_CALLBACK_DATA  # noqa: E402
from runtime.ui.telegram.details import HOME_CALLBACK_DATA  # noqa: E402
from ui_callback_acceptance_support import exercise_safe_callbacks  # noqa: E402


class SyntheticCallback:
    def __init__(self, data: str) -> None:
        self.data = data


async def matching_handlers(data: str):
    result = []
    for handler in app.router.observers["callback_query"].handlers:
        matched, _ = await handler.check(SyntheticCallback(data))
        if matched:
            result.append(handler)
    return result


def _module_file(module: str) -> str:
    return module.rsplit(".", 1)[-1] + ".py"


def _static_candidates(static_handlers: list[dict]) -> list[str]:
    values: list[str] = []
    for item in static_handlers:
        values.extend(re.findall(r'"([^"\n]+)"', item["text"]))
    # Representative values for prefix/encoded callback declarations.
    values.extend(
        [
            "v2_battery_id_000000000000",
            "v2_battery_0",
            "v2_mbind:token",
            "v2_mix_profile_efb",
            "v2_mix_bat_0",
            "v2_quick_intent_recovery",
            "v2_bat_intent_recovery",
            "v2_sg_pick_0",
            "operator_graph_30m",
            "rd_live_mix_bat_0",
            "rd_managed_adopt_bat_0",
            "rd_managed_mix_bat_0",
            "rd_managed_mix_age_1h",
            "ui:charge.select_profile?profile=EFB",
            "off:preset?minutes=30",
        ]
    )
    return list(dict.fromkeys(values))


async def build_matrix() -> dict:
    static_path = ROOT / "docs" / "UI_CALLBACK_STATIC_INVENTORY_20261010.json"
    if not static_path.exists():
        raise RuntimeError("tracked callback inventory is missing from the checkout")
    tracked = subprocess.run(
        ["git", "ls-files", "--error-unmatch", "docs/UI_CALLBACK_STATIC_INVENTORY_20261010.json"],
        cwd=ROOT, capture_output=True, text=True,
    )
    if tracked.returncode != 0:
        raise RuntimeError("callback inventory must be tracked for fresh-checkout reproducibility")
    static = json.loads(static_path.read_text(encoding="utf-8"))
    active = list(app.router.observers["callback_query"].handlers)
    exercised = await exercise_safe_callbacks()
    exercised_keys = {(item["module"], item["handler"]) for item in exercised}
    tested_callbacks = [str(item["callback"]) for item in exercised]
    static_candidates = _static_candidates(static["handlers"])
    candidate_matches = {
        candidate: await matching_handlers(candidate)
        for candidate in set(static_candidates + tested_callbacks)
    }
    rows = []
    for index, handler in enumerate(active):
        module = handler.callback.__module__
        qualname = handler.callback.__qualname__
        static_same_file = [
            item for item in static["handlers"] if item["file"].replace("\\", "/").endswith(_module_file(module))
        ]
        static_matched = False
        for candidate in static_candidates:
            matches = candidate_matches[candidate]
            if handler in matches:
                static_matched = True
                break
        dispatched_by = []
        for scenario_callback in tested_callbacks:
            matches = candidate_matches[scenario_callback]
            if handler in matches:
                dispatched_by.append(scenario_callback)
        actually_dispatched = (module, qualname) in exercised_keys
        rows.append(
            {
                "active_index": index,
                "module": module,
                "handler": qualname,
                "static_declarations_same_file": len(static_same_file),
                "static_match": static_matched,
                "actually_dispatched": actually_dispatched,
                "dispatch_scenarios": dispatched_by,
                "cause": None if actually_dispatched else "not exercised by offline safety-bounded scenario set; stateful/physical contract requires a dedicated fake",
            }
        )
    static_files = Counter(item["file"].replace("\\", "/").rsplit("/", 1)[-1] for item in static["handlers"])
    return {
        "schema": "rd6018.ui.callback.acceptance.v1",
        "scope": {
            "head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
            "composition": "bot.ProductionComposition -> runtime.production_runtime.router",
            "offline": True,
            "telegram_messages": False,
            "physical_rd_commands": False,
            "output_on": False,
            "lease_mutation": False,
            "production_restart": False,
        },
        "static_inventory": {
            "path": str(static_path.relative_to(ROOT)).replace("\\", "/"),
            "button_declarations": len(static["buttons"]),
            "callback_declarations": len(static["handlers"]),
            "handler_files": dict(sorted(static_files.items())),
            "meaning": "declarations only; not execution coverage",
            "buttons": static["buttons"],
            "callback_declarations_detail": static["handlers"],
        },
        "active_v3": {
            "router_observer": "callback_query",
            "installed_handlers": len(active),
            "static_matched_handlers": sum(row["static_match"] for row in rows),
            "actually_dispatched_handlers": sum(row["actually_dispatched"] for row in rows),
            "uncovered_handlers": sum(not row["actually_dispatched"] for row in rows),
            "duplicate_or_not_installed_static_declarations": len(static["handlers"]) - len(active),
        },
        "exercised_callbacks": exercised,
        "hazardous_skipped": [
            {
                "module": row["module"],
                "handler": row["handler"],
                "reason": "hazardous output/lease/ownership transaction; covered only by FAKE safety-preflight tests",
            }
            for row in rows
            if not row["actually_dispatched"] and any(
                token in f"{row['module']}:{row['handler']}".lower()
                for token in ("start", "execute", "release", "hands_off", "adopt", "output_off", "stop")
            )
        ],
        "handlers": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    matrix = asyncio.run(build_matrix())
    if args.write:
        REPORT_PATH.write_text(json.dumps(matrix, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "installed_handlers": matrix["active_v3"]["installed_handlers"],
        "static_matched_handlers": matrix["active_v3"]["static_matched_handlers"],
        "actually_dispatched_handlers": matrix["active_v3"]["actually_dispatched_handlers"],
        "uncovered_handlers": matrix["active_v3"]["uncovered_handlers"],
    }))
    # The composed offline app may have legacy best-effort timer/thread work
    # attached to its process.  The matrix is already written and no runtime
    # lifecycle is being tested here; terminate the short-lived CLI cleanly
    # after flushing evidence so it cannot keep a fake acceptance job alive.
    sys.stdout.flush()
    os._exit(0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
