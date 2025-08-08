import platform
from pathlib import Path
from typing import Iterable
from .base_scanner import BaseScanner
from .macos_scanner import MacOSVideoScanner

def get_scanner() -> BaseScanner:
    system = platform.system().lower()
    if system == 'darwin':
        return MacOSVideoScanner()
    elif system == 'windows':
        # TODO: Implement WindowsVideoScanner
        return BaseScanner()
    elif system == 'linux':
        # TODO: Implement LinuxVideoScanner
        return BaseScanner()
    else:
        return BaseScanner()


def default_roots_if_missing(roots: Iterable[str | Path] | None) -> list[Path]:
    """Return provided roots or sensible OS-specific defaults when none supplied.

    On macOS, defaults to common user media locations.
    """
    if roots:
        return [Path(r).expanduser() for r in roots]
    system = platform.system().lower()
    if system == 'darwin':
        candidates = [
            Path.home() / 'Movies',
            Path.home() / 'Videos',
            Path('/Volumes'),
        ]
        return [p for p in candidates if p.exists()]
    # For other OSes, return empty to force explicit roots for now
    return []
