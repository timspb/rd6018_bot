"""Production entrypoint for the evidence-driven V2 UI/controller.

The previous monolithic Telegram runtime is kept byte-for-byte as bot_legacy.py.
Set V2_UI=0 to keep its UI, and V2_AUTHORITATIVE=0 as the independent actuator
rollback. Running bot_legacy.py directly is also available for emergency diagnosis.
"""
from __future__ import annotations

import asyncio
import os
import sys

import bot_legacy as _legacy
from v2_bootstrap import init_v2_storage, install_v2


def _env_enabled(name: str, default: bool = True) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return bool(default)
    return str(raw).strip().lower() not in {"0", "false", "no", "off", "disabled"}


if _env_enabled("V2_UI", True):
    install_v2(_legacy)

_legacy_main = _legacy.main


async def main() -> None:
    await init_v2_storage()
    await _legacy_main()


# Keep one runtime module object. Existing tests and operational helpers import many
# private bot symbols; aliasing preserves their globals/monkeypatch semantics instead
# of copying 180+ KB of names into this shim.
_legacy.main = main

if __name__ == "__main__":
    asyncio.run(main())
else:
    sys.modules[__name__] = _legacy
