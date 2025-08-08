import logging
from pathlib import Path
from typing import Iterable, Iterator, Tuple, Callable
import os
from .base_scanner import BaseScanner
from ..utils.file_hash import compute_sample_hash

logger = logging.getLogger(__name__)

class WindowsVideoScanner(BaseScanner):
    SYSTEM_DIRS = {"System Volume Information", "$RECYCLE.BIN", "$WinREAgent"}

    def _skip_dir(self, dir_path: Path) -> bool:
        name = dir_path.name
        if name in self.SYSTEM_DIRS:
            return True
        # Hidden dot-folders (rare on Windows but possible)
        if name.startswith('.'):
            return True
        return False

    def _skip_file(self, path: Path) -> bool:
        name = path.name
        if name.startswith('.'):  # hidden-like
            return True
        return False

    def iter_videos(
        self,
        roots: Iterable[str | Path],
        extensions: Iterable[str] | None = None,
        recursive: bool = True,
        excludes: Iterable[str] | None = None,
        progress_cb: Callable[[int, int], None] | None = None,
    ) -> Iterator[Tuple[Path, str]]:
        ext_set = {e.lower() if e.startswith(".") else f".{e.lower()}" for e in (extensions or self.DEFAULT_EXTS)}
        exclude_subs = set(excludes or [])

        all_files: list[Path] = []
        for root in roots:
            root_path = Path(root).expanduser().resolve()
            if not root_path.is_dir():
                continue
            if recursive:
                for dirpath, dirnames, filenames in os.walk(root_path):
                    # filter dirnames in-place to skip system/hidden dirs
                    dirnames[:] = [d for d in dirnames if not self._skip_dir(Path(dirpath) / d)]
                    for filename in filenames:
                        p = Path(dirpath) / filename
                        if self._skip_file(p):
                            continue
                        if any(sub in str(p) for sub in exclude_subs):
                            continue
                        if p.suffix.lower() in ext_set:
                            all_files.append(p)
            else:
                for entry in os.scandir(root_path):
                    if entry.is_file():
                        p = Path(entry.path)
                        if not self._skip_file(p) and not any(sub in str(p) for sub in exclude_subs) and p.suffix.lower() in ext_set:
                            all_files.append(p)

        total = len(all_files)
        done = 0
        for p in all_files:
            try:
                sample_hash = compute_sample_hash(p)
                yield (p, sample_hash)
            except Exception as e:
                logger.debug(f"Skipping unreadable file: {p} ({e})")
            done += 1
            if progress_cb:
                progress_cb(done, total)