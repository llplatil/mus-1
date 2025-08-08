#!/usr/bin/env bash
# Quick launcher for MUS1 development environment
# 1. Creates .venv with uv or python -m venv if missing
# 2. Activates the venv
# 3. Installs MUS1 in editable mode
# 4. Runs the mus1 CLI (use --help for commands)

set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
  echo "[dev-launch] Creating virtual environment (.venv)"
  if command -v uv >/dev/null 2>&1; then
    uv venv .venv
    source .venv/bin/activate
    uv pip install -e .
  else
    python3 -m venv .venv
    source .venv/bin/activate
    pip install --upgrade pip
    pip install -e .
  fi
else
  source .venv/bin/activate
fi

exec mus1 "$@"

