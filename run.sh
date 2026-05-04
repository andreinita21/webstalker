#!/usr/bin/env bash
# WebStalker one-shot launcher.
# Creates a virtual env, installs dependencies, and starts the app on
# http://127.0.0.1:8000. Re-run any time; it's idempotent.

set -euo pipefail

# Always run from the project root, regardless of where the user invoked it from.
cd "$(dirname "$0")"

VENV_DIR=".venv"
PYTHON_BIN="${PYTHON_BIN:-}"
HOST="${WEBSTALKER_BIND_HOST:-127.0.0.1}"
PORT="${WEBSTALKER_BIND_PORT:-8000}"

color()  { printf '\033[%sm%s\033[0m\n' "$1" "$2"; }
info()   { color "1;34" "▸ $*"; }
ok()     { color "1;32" "✓ $*"; }
warn()   { color "1;33" "! $*"; }
fail()   { color "1;31" "✗ $*"; }

# 1. Find a Python interpreter we can use.
if [ -z "$PYTHON_BIN" ]; then
  for candidate in python3.13 python3.12 python3.11 python3; do
    if command -v "$candidate" >/dev/null 2>&1; then
      PYTHON_BIN="$candidate"
      break
    fi
  done
fi

if [ -z "$PYTHON_BIN" ]; then
  fail "Python 3.11+ is required but no python3 was found on PATH."
  echo "  macOS:  brew install python@3.12"
  echo "  Ubuntu: sudo apt install python3-venv python3-pip"
  exit 1
fi

PY_VERSION="$("$PYTHON_BIN" -c 'import sys;print(".".join(str(x) for x in sys.version_info[:2]))' 2>/dev/null || echo "?")"
PY_MAJOR_OK="$("$PYTHON_BIN" -c 'import sys;print(1 if sys.version_info[:2] >= (3,11) and sys.version_info[:2] < (3,14) else 0)' 2>/dev/null || echo 0)"

if [ "$PY_MAJOR_OK" != "1" ]; then
  fail "Found Python $PY_VERSION at $(command -v "$PYTHON_BIN"), but WebStalker needs Python 3.11, 3.12, or 3.13."
  echo "  Set PYTHON_BIN to a compatible interpreter and re-run, e.g."
  echo "    PYTHON_BIN=python3.12 ./run.sh"
  exit 1
fi
ok "Using $PYTHON_BIN ($PY_VERSION)"

# 2. Create the virtual environment if it does not already exist.
if [ ! -d "$VENV_DIR" ]; then
  info "Creating virtual environment in $VENV_DIR/"
  "$PYTHON_BIN" -m venv "$VENV_DIR"
  ok "Virtual environment ready"
fi

PIP="$VENV_DIR/bin/pip"
PY="$VENV_DIR/bin/python"

# 3. Install / refresh dependencies. Cheap fingerprint avoids reinstalling
#    every run unless requirements.txt actually changed.
FINGERPRINT_FILE="$VENV_DIR/.requirements.sha"
NEW_FP="$(shasum -a 256 requirements.txt 2>/dev/null | awk '{print $1}')"
OLD_FP="$(cat "$FINGERPRINT_FILE" 2>/dev/null || true)"

if [ "$NEW_FP" != "$OLD_FP" ] || [ ! -x "$VENV_DIR/bin/uvicorn" ]; then
  info "Installing dependencies"
  "$PIP" install --quiet --upgrade pip
  "$PIP" install --quiet -r requirements.txt
  echo "$NEW_FP" > "$FINGERPRINT_FILE"
  ok "Dependencies installed"
else
  ok "Dependencies up to date"
fi

# 4. Make sure the data directory exists (the app would create it on its own,
#    but doing it here lets us print a friendlier path).
DATA_DIR="${WEBSTALKER_DATA_DIR:-data}"
mkdir -p "$DATA_DIR"

# 5. Start the server.
echo
ok "Starting WebStalker"
echo "    Open in your browser: http://${HOST}:${PORT}"
echo "    Stored data:          $(cd "$DATA_DIR" && pwd)"
echo "    Press Ctrl+C to stop"
echo

exec "$PY" -m uvicorn webstalker.main:app \
  --host "$HOST" \
  --port "$PORT" \
  --log-level info \
  "$@"
