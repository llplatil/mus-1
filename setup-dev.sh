#!/usr/bin/env bash
# setup-dev.sh – One-time setup script for MUS1 development
#
# This script ensures you have a properly configured development environment
# with all dependencies and plugins installed.

set -euo pipefail

ROOT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$ROOT_DIR"

echo "=== MUS1 Development Environment Setup ==="

# Step 1: Ensure virtual environment exists and is up to date
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    if command -v uv >/dev/null 2>&1; then
        uv venv .venv
    else
        python3 -m venv .venv
    fi
fi

# Activate venv
if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
else
    echo "Error: Virtual environment not found. Please run this from the MUS1 project root."
    exit 1
fi

# Install pip if missing (uv doesn't include it by default)
if ! python -m pip --version >/dev/null 2>&1; then
    echo "Installing pip..."
    curl -sSL https://bootstrap.pypa.io/get-pip.py | python
fi

# Upgrade pip
python -m pip install --upgrade pip

# Install MUS1 in editable mode
echo "Installing MUS1..."
pip install -e .

# Install private plugins
if [ -f "requirements-plugins.private.txt" ]; then
    echo "Installing private plugins..."
    pip install -r requirements-plugins.private.txt
fi

# Update hash file to prevent unnecessary rebuilds
echo "Updating environment hash..."
shasum -a 256 pyproject.toml > .venv/.pyproject.sha256

echo ""
echo "✅ Setup complete!"
echo ""
echo "To start developing:"
echo "  cd /path/to/mus-1"
echo "  source .venv/bin/activate"
echo "  ./dev-launch.sh <command>"
echo ""
echo "Available commands:"
echo "  ./dev-launch.sh --help          # Show CLI help"
echo "  ./dev-launch.sh plugins list    # List installed plugins"
echo "  ./dev-launch.sh project list    # List projects"
