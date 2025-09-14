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

success "MUS1 installation complete!"

if ! $QUIET; then
    echo ""
    echo "🚀 Launch MUS1:"
    echo "   ./dev-launch.sh gui     # GUI mode (recommended)"
    echo "   ./dev-launch.sh --help  # CLI commands"
    echo ""
    echo "📚 First-time setup:"
    echo "   ./dev-launch.sh gui     # Launches setup wizard automatically"
fi
