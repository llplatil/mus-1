#!/usr/bin/env bash
# dev-launch.sh – MUS1 Development Launcher
#
# Launches MUS1 in development mode with automatic environment setup.
# Handles virtual environment activation and dependency management.
#
# Usage: ./dev-launch.sh [gui|COMMAND...]
#   gui          Launch GUI mode (recommended)
#   COMMAND...   Run CLI commands

set -euo pipefail

# Configuration
VENV_DIR=".venv"
PYPROJECT_FILE="pyproject.toml"
HASH_FILE="$VENV_DIR/.pyproject.sha256"
ROOT_HINT_FILE=".mus1_root"

###############################################################################
# Helper Functions
###############################################################################

calc_hash() {
    shasum -a 256 "$PYPROJECT_FILE" | awk '{print $1}'
}

ensure_venv() {
    if [ ! -d "$VENV_DIR" ]; then
        echo "🔧 Creating virtual environment..."
        python3 -m venv "$VENV_DIR"
        setup_venv
    elif [ ! -f "$VENV_DIR/bin/activate" ]; then
        echo "🔧 Recreating incomplete virtual environment..."
        rm -rf "$VENV_DIR"
        python3 -m venv "$VENV_DIR"
        setup_venv
    elif [ ! -f "$HASH_FILE" ] || [ "$(calc_hash)" != "$(cat "$HASH_FILE")" ]; then
        echo "🔧 Dependencies changed, updating environment..."
        setup_venv
    fi
}

setup_venv() {
    # shellcheck source=/dev/null
    source "$VENV_DIR/bin/activate"
    python -m pip install --quiet --upgrade pip
    python -m pip install --quiet -e .
    calc_hash > "$HASH_FILE"
    echo "✅ Environment ready"
}

load_root_hint() {
    if [ -f "$ROOT_HINT_FILE" ]; then
        MUS1_ROOT_PATH=$(cat "$ROOT_HINT_FILE" | tr -d '\n')
        if [ -n "$MUS1_ROOT_PATH" ] && [ -d "$MUS1_ROOT_PATH" ]; then
            export MUS1_ROOT="$MUS1_ROOT_PATH"
        fi
    fi
}

###############################################################################
# Main Logic
###############################################################################

# Ensure we're in project root
if [ ! -f "$PYPROJECT_FILE" ]; then
    echo "❌ Error: Must run from MUS1 project root (pyproject.toml not found)"
    exit 1
fi

# Set up environment
ensure_venv

# Activate virtual environment
# shellcheck source=/dev/null
source "$VENV_DIR/bin/activate"

# Ensure dev imports work reliably with editable install
export PYTHONPATH="$(pwd)/src:${PYTHONPATH:-}"

# Load MUS1 root hint if present to avoid re-running setup wizard
load_root_hint

# Launch appropriate mode
if [ "${1:-}" = "set-root" ]; then
    # Persist a MUS1 root hint for dev launches
    if [ -z "${2:-}" ]; then
        echo "❌ Usage: ./dev-launch.sh set-root /path/to/MUS1_ROOT"
        exit 1
    fi
    echo "$2" > "$ROOT_HINT_FILE"
    echo "✅ Saved MUS1 root to $ROOT_HINT_FILE"
    exit 0
elif [ "${1:-}" = "gui" ]; then
    echo "🚀 Launching MUS1 GUI..."

    # Configure Qt for macOS - resolve plugin paths from the installed binding inside the venv
    if [[ "$OSTYPE" == "darwin"* ]]; then
        # Optional: set to 1 to debug plugin loading
        : "${QT_DEBUG_PLUGINS:=0}"
        export QT_DEBUG_PLUGINS

        if python -c "import PyQt6" 2>/dev/null; then
            PYQT6_BASE=$(python -c 'import pathlib, PyQt6; print(pathlib.Path(PyQt6.__file__).parent)')
            export QT_QPA_PLATFORM_PLUGIN_PATH="${PYQT6_BASE}/Qt6/plugins/platforms"
            export QT_PLUGIN_PATH="${PYQT6_BASE}/Qt6/plugins"
            export DYLD_FRAMEWORK_PATH="${PYQT6_BASE}/Qt6/lib"
            export QT_QPA_PLATFORM="cocoa"
        elif python -c "import PySide6" 2>/dev/null; then
            PYSIDE6_BASE=$(python -c 'import pathlib, PySide6; print(pathlib.Path(PySide6.__file__).parent)')
            export QT_QPA_PLATFORM_PLUGIN_PATH="${PYSIDE6_BASE}/Qt/plugins/platforms"
            export QT_PLUGIN_PATH="${PYSIDE6_BASE}/Qt/plugins"
            export DYLD_FRAMEWORK_PATH="${PYSIDE6_BASE}/Qt/lib"
            export QT_QPA_PLATFORM="cocoa"
        fi
    fi

    # Pass remaining arguments to local main.py
    shift
    exec python -m mus1.main "$@"
else
    # Run CLI command
    exec mus1 "$@"
fi
