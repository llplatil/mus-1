#!/usr/bin/env bash
# dev-launch.sh – streamlined launcher for MUS1 development
#
# Behaviour:
#   1. Re-uses an existing .venv if possible (fast-path)
#   2. Rebuilds the venv only when necessary:
#        • .venv is missing, OR
#        • pyproject.toml has changed since last installation
#   3. Ensures MUS1 is installed in *editable* mode from this checkout
#   4. Finally execs the mus1 CLI so all args/flags are forwarded.
#
# The script is idempotent and should complete in ~0 s when nothing changed.

set -euo pipefail

ROOT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$ROOT_DIR"

VENV_DIR=".venv"
PYPROJECT_FILE="pyproject.toml"
HASH_FILE="$VENV_DIR/.pyproject.sha256"

###############################################################################
# Helper functions
###############################################################################

calc_hash() {
  shasum -a 256 "$PYPROJECT_FILE" | awk '{print $1}'
}

create_venv() {
  echo "[dev-launch] Creating virtual environment ($VENV_DIR)"
  if command -v uv >/dev/null 2>&1; then
    uv venv "$VENV_DIR"
  else
    python3 -m venv "$VENV_DIR"
  fi
  # shellcheck source=/dev/null
  source "$VENV_DIR/bin/activate"
  python -m pip install --upgrade pip
  python -m pip install -e .
  calc_hash > "$HASH_FILE"
}

activate_venv() {
  # shellcheck source=/dev/null
  source "$VENV_DIR/bin/activate"
}

editable_install_ok() {
  python - <<'PY'
import sys, importlib.util, pathlib
try:
    spec = importlib.util.find_spec("mus1")
except ModuleNotFoundError:
    sys.exit(1)
if not spec or not spec.origin:
    sys.exit(1)
origin_path = pathlib.Path(spec.origin).resolve()
# We run this script from the repo root (the script cd's there),
# so the current working directory is the repository root.
repo_root = pathlib.Path.cwd()
if repo_root in origin_path.parents:
    sys.exit(0)  # good – editable install from this checkout
sys.exit(1)
PY
}

###############################################################################
# Main logic
###############################################################################

if [ ! -d "$VENV_DIR" ]; then
  create_venv
elif [ ! -f "$VENV_DIR/bin/activate" ]; then
  echo "[dev-launch] Detected incomplete venv – rebuilding"
  rm -rf "$VENV_DIR"
  create_venv
else
  activate_venv
  if [ ! -f "$HASH_FILE" ] || [ "$(calc_hash)" != "$(cat "$HASH_FILE")" ]; then
    echo "[dev-launch] pyproject.toml changed – rebuilding environment"
    rm -rf "$VENV_DIR"
    create_venv
  elif ! editable_install_ok; then
    echo "[dev-launch] Installing MUS1 in editable mode (pip install -e .)"
    python -m pip install -e .
  fi
fi

exec mus1 "$@"
