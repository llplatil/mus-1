import logging
from pathlib import Path
from typing import Iterable, Iterator, Tuple, Callable, Optional
import os
from ..utils.file_hash import compute_sample_hash

logger = logging.getLogger(__name__)

class BaseScanner:
    DEFAULT_EXTS = {".mp4", ".mkv", ".avi", ".mov", ".mpg", ".mpeg"}

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
                    for filename in filenames:
                        p = Path(dirpath) / filename
                        if any(sub in str(p) for sub in exclude_subs):
                            continue
                        if p.suffix.lower() in ext_set:
                            all_files.append(p)
            else:
                for entry in os.scandir(root_path):
                    if entry.is_file() and entry.name.lower().endswith(tuple(ext_set)):
                        p = Path(entry.path)
                        if not any(sub in str(p) for sub in exclude_subs):
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

