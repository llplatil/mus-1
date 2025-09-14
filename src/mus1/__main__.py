"""Executable entrypoint for `python -m mus1`.

Delegates to the clean simple CLI.
"""
from .core.simple_cli import app

if __name__ == "__main__":
    app()
