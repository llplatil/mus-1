import platform
from pathlib import Path
from typing import Iterable
from .base_scanner import BaseScanner

def get_scanner() -> BaseScanner:
    """Get a unified scanner that handles platform differences internally."""
    return BaseScanner()


def default_roots_if_missing(roots: Iterable[str | Path] | None) -> list[Path]:
    """Return provided roots or sensible OS-specific defaults when none supplied.

    On macOS, defaults to common user media locations.
    On Windows, defaults to typical video folders and mounted drives roots.
    On Linux, defaults to mounted removable/media locations where present.
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
    if system == 'windows':
        candidates = [
            Path.home() / 'Videos',
            Path('C:/'),
            Path('D:/'),
            Path('E:/'),
        ]
        return [p for p in candidates if p.exists()]
    if system == 'linux':
        candidates = [
            Path('/media'),
            Path('/mnt'),
            Path.home() / 'Videos',
        ]
        return [p for p in candidates if p.exists()]
    return []


def select_local_scanner() -> BaseScanner:
    """Return an OS-appropriate scanner instance (thin wrapper).

    Core code should use this to avoid importing specific OS scanners directly.
    """
    return get_scanner()
