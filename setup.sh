#!/usr/bin/env bash
# setup.sh – MUS1 Installation and Development Setup
#
# This script handles environment setup for MUS1 development and production use.
# Creates virtual environment and installs MUS1 in editable mode.
#
# Usage: ./setup.sh [--dev|--prod|--help]
#   --dev:  Development setup (default)
#   --prod: Production setup (minimal output)
#   --help: Show usage

set -euo pipefail

# Default mode
MODE="dev"
QUIET=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --dev) MODE="dev" ;;
        --prod) MODE="prod"; QUIET=true ;;
        --help|-h)
            echo "Usage: $0 [--dev|--prod|--help]"
            echo "  --dev   Development setup with verbose output (default)"
            echo "  --prod  Production setup with minimal output"
            echo "  --help  Show this help"
            exit 0
            ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
    shift
done

# Output functions
info() { if ! $QUIET; then echo "ℹ️  $1"; fi; }
success() { echo "✅ $1"; }
error() { echo "❌ $1" >&2; }
warning() { echo "⚠️  $1" >&2; }

if $QUIET; then
    echo "🎯 MUS1 Setup (Production Mode)"
else
    echo "🎯 MUS1 Setup Script"
    echo "==================="
fi

# Check if we're in the right directory
if [ ! -f "pyproject.toml" ]; then
    error "pyproject.toml not found. Please run this script from the MUS1 root directory."
    exit 1
fi

info "Working directory: $(pwd)"

# Check Python version
PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
info "Python version: $PYTHON_VERSION"

# Create virtual environment
VENV_DIR=".venv"
if [ -d "$VENV_DIR" ]; then
    warning "Virtual environment already exists at $VENV_DIR"
    if ! $QUIET; then
        read -p "Remove and recreate? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            info "Using existing virtual environment"
        else
            info "Removing existing virtual environment..."
            rm -rf "$VENV_DIR"
        fi
    fi
fi

if [ ! -d "$VENV_DIR" ]; then
    info "Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
fi

# Activate virtual environment
info "Activating virtual environment..."
# shellcheck source=/dev/null
source "$VENV_DIR/bin/activate"

# Upgrade pip
info "Upgrading pip..."
python -m pip install --upgrade pip >/dev/null 2>&1

# Install MUS1
info "Installing MUS1..."
if $QUIET; then
    python -m pip install -e . >/dev/null 2>&1
else
    python -m pip install -e .
fi

# Platform-specific Qt setup
if [[ "$OSTYPE" == "darwin"* ]]; then
    info "macOS detected - ensuring Qt platform support..."

    # Check if PyQt6 is available and working
    if python3 -c "import PyQt6.QtWidgets; import sys; app = PyQt6.QtWidgets.QApplication(sys.argv); print('PyQt6 OK')" 2>/dev/null; then
        info "PyQt6 is working correctly on macOS"
    elif python3 -c "import PySide6.QtWidgets; import sys; app = PySide6.QtWidgets.QApplication(sys.argv); print('PySide6 OK')" 2>/dev/null; then
        warning "PyQt6 failed, but PySide6 appears to work - you may experience GUI issues"
    else
        warning "Neither PyQt6 nor PySide6 can initialize QApplication on macOS"
        warning "GUI may not work - try: brew install qt6 && pip install PyQt6 --force-reinstall"
    fi
fi

success "MUS1 installation complete!"

if ! $QUIET; then
    echo ""
    echo "🚀 Launch MUS1:"
    echo "   ./dev-launch.sh gui     # GUI mode (recommended)"
    echo "   ./dev-launch.sh set-root /path/to/mus1-root  # Persist MUS1 root hint for dev launches"
    echo "   ./dev-launch.sh --help  # CLI commands"
    echo ""
    echo "📚 For Production Users:"
    echo "   After 'pip install mus1':"
    echo "   mus1-gui               # GUI mode"
    echo "   mus1 --help           # CLI commands"
    echo ""
    echo "⚠️  Development vs Production:"
    echo "   Dev: Uses ./dev-launch.sh (auto-setup venv, deps)"
    echo "   Prod: Uses mus1-gui/mus1 commands (system-installed)"
fi
