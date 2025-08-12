import logging
from pathlib import Path
from typing import Iterable, Iterator, Tuple, Callable, Optional
import os
from ..utils.file_hash import compute_sample_hash
try:
    import xattr
except ImportError:
    xattr = None

from .base_scanner import BaseScanner

logger = logging.getLogger(__name__)

class MacOSVideoScanner(BaseScanner):
    PLACEHOLDER_SUFFIX = ".icloud"

    def _is_placeholder(self, p: Path) -> bool:
        try:
            stat = p.stat()
            if stat.st_size == 0:
                return True
            if p.suffix.lower() == self.PLACEHOLDER_SUFFIX:
                return True
            if xattr is not None:
                xa = xattr.xattr(p)
                finfo = xa.get(b'com.apple.FinderInfo', b'')
                if len(finfo) >= 9 and finfo[8] & 0x01:  # kIsUbiquitousItem
                    return True
        except OSError:
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
                    for filename in filenames:
                        p = Path(dirpath) / filename
                        if self._is_placeholder(p):
                            continue
                        if any(sub in str(p) for sub in exclude_subs):
                            continue
                        if p.suffix.lower() in ext_set:
                            all_files.append(p)
            else:
                for entry in os.scandir(root_path):
                    p = Path(entry.path)
                    if entry.is_file() and not self._is_placeholder(p) and not any(sub in str(p) for sub in exclude_subs) and p.suffix.lower() in ext_set:
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
