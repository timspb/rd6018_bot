"""Placeholder accepted-child adapter: intentionally refuses to run actions."""
import sys


def main() -> int:
    print("D061 acceptance child denied: no reviewed source/run proof adapter is installed", file=sys.stderr)
    return 78


if __name__ == "__main__":
    raise SystemExit(main())
