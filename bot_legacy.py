"""Rollback-only compatibility shim.

Production starts through :mod:`bot`, which imports ``runtime.v2_runtime``
directly.  This module remains only for emergency rollback tooling and old
operator scripts; it does not define a second runtime or polling owner.
"""
from __future__ import annotations

import asyncio
import sys

from runtime import v2_runtime as _runtime

if __name__ == "__main__":
    asyncio.run(_runtime.main())
else:
    sys.modules[__name__] = _runtime
