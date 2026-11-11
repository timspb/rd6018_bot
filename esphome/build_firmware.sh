#!/bin/sh
set -eu

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
ESPHOME_DIR="$ROOT_DIR/esphome"
TARGET="$ESPHOME_DIR/rd6018.yaml"
SECRETS="$ESPHOME_DIR/secrets.yaml"
EXAMPLE_SECRETS="$ESPHOME_DIR/secrets.example.yaml"
VENV="${ESPHOME_VENV:-$ESPHOME_DIR/.venv}"
PYTHON="${PYTHON:-python3.12}"
ESPHOME_VERSION="${ESPHOME_VERSION:-2026.9.1}"
DIST_DIR="${ESPHOME_DIST:-$ESPHOME_DIR/dist}"
OUT="$DIST_DIR/rd6018-controller-2.3-ha-canonical.bin"
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
    # ESPHome 2026.9.1 forbids an all-zero Noise key; use a random CI-only key.
    # The temporary example configuration is NEVER an OTA/production image.
    "$PYTHON" - "$SECRETS" <<'PY'
from pathlib import Path
import base64
import os
import sys
p = Path(sys.argv[1])
lines = p.read_text(encoding="utf-8").splitlines()
replacement = 'rd6018_api_encryption_key: "' + base64.b64encode(os.urandom(32)).decode() + '"'
lines = [replacement if ln.startswith("rd6018_api_encryption_key:") else ln for ln in lines]
p.write_text("\n".join(lines) + "\n", encoding="utf-8")
PY
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
