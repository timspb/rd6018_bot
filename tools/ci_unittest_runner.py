"""CI-only unittest runner with explicit result-preserving process exit.

Some legacy tests leave non-daemon workers alive after unittest prints OK.
The test result is authoritative; do not wait indefinitely for these workers.
GitHub Actions cleans up remaining child processes when the job finishes.
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

# Running this file as a script sets sys.path[0] to tools/, not the repository.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main() -> int:
    suite = unittest.defaultTestLoader.discover("tests", pattern="test_*.py")
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    try:
        status = main()
    except BaseException:
        import traceback

        traceback.print_exc()
        status = 2
    finally:
        sys.stdout.flush()
        sys.stderr.flush()
    os._exit(status)
