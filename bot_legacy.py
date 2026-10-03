"""Non-executable import-compatibility shim pending removal.

Production starts through :mod:`bot`. Direct execution is intentionally retired;
only import compatibility remains for characterization tests during migration.
"""
from __future__ import annotations

import sys


if __name__ == "__main__":
    # Exit before importing the historical runtime so direct invocation cannot
    # construct Telegram/HA/runtime globals as a side effect.
    raise SystemExit(
        "bot_legacy.py direct execution is retired; use the canonical production entrypoint"
    )

from runtime import v2_runtime as _runtime

# Import compatibility remains temporarily for characterization tests only.
sys.modules[__name__] = _runtime
