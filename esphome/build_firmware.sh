#!/bin/sh
set -eu

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
ESPHOME_DIR="$ROOT_DIR/esphome"
TARGET="$ESPHOME_DIR/rd6018.yaml"
SECRETS="$ESPHOME_DIR/secrets.yaml"
EXAMPLE_SECRETS="$ESPHOME_DIR/secrets.example.yaml"
VENV="${ESPHOME_VENV:-$ESPHOME_DIR/.venv}"
PYTHON="${PYTHON:-python3.12}"
ESPHOME_VERSION="${ESPHOME_VERSION:-2026.8.2}"
DIST_DIR="${ESPHOME_DIST:-$ESPHOME_DIR/dist}"
OUT="$DIST_DIR/rd6018-controller-v2.bin"
CREATED_EXAMPLE_SECRETS=0

cleanup() {
    if [ "$CREATED_EXAMPLE_SECRETS" -eq 1 ]; then
        rm -f "$SECRETS"
    fi
}
trap cleanup EXIT INT TERM

if [ "${ESPHOME_SECRETS_MODE:-local}" = "example" ]; then
    if [ -e "$SECRETS" ]; then
        echo "Refusing to overwrite existing $SECRETS in example-secrets mode." >&2
        exit 2
    fi
    cp "$EXAMPLE_SECRETS" "$SECRETS"
    CREATED_EXAMPLE_SECRETS=1
elif [ ! -f "$SECRETS" ]; then
    echo "Missing $SECRETS." >&2
    echo "Copy $EXAMPLE_SECRETS to $SECRETS and replace every example value." >&2
    exit 2
fi

"$PYTHON" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)' || {
    echo "Python 3.12+ is required for ESPHome $ESPHOME_VERSION." >&2
    exit 2
}

if [ ! -x "$VENV/bin/python" ]; then
    "$PYTHON" -m venv "$VENV"
fi

"$VENV/bin/python" -m pip install --disable-pip-version-check --upgrade pip
"$VENV/bin/python" -m pip install --disable-pip-version-check "esphome==$ESPHOME_VERSION"
"$VENV/bin/esphome" version

"$VENV/bin/esphome" config "$TARGET"

if [ "${1:-}" = "--validate-only" ]; then
    echo "Configuration valid: $TARGET"
    exit 0
fi

"$VENV/bin/esphome" compile "$TARGET"

firmware=$(find "$ESPHOME_DIR/.esphome" -type f \
    -path '*/.pioenvs/rd6018-controller/firmware.bin' -print -quit)
if [ -z "$firmware" ] || [ ! -s "$firmware" ]; then
    echo "Compiled firmware.bin not found." >&2
    exit 3
fi

mkdir -p "$DIST_DIR"
cp "$firmware" "$OUT"

echo
echo "Firmware: $OUT"
if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$OUT"
elif command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$OUT"
fi
