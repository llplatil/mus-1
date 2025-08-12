"""Executable entrypoint for `python -m Mus1_Refactor`.

Delegates to Typer CLI defined in `cli_ty.py`.
"""
from .cli_ty import run

if __name__ == "__main__":
    run()
