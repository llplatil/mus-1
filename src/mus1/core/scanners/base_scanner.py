import logging
import platform
from pathlib import Path
from typing import Iterable, Iterator, Tuple, Callable, Optional, Set
import os
from ..utils.file_hash import compute_sample_hash

logger = logging.getLogger(__name__)

class BaseScanner:
    DEFAULT_EXTS = {".mp4", ".mkv", ".avi", ".mov", ".mpg", ".mpeg"}

    def __init__(self):
        self.system = platform.system().lower()
        self._skip_dirs: Set[str] = self._get_platform_skip_dirs()
        self._skip_files: Set[str] = self._get_platform_skip_files()

    def _get_platform_skip_dirs(self) -> Set[str]:
        """Get directories to skip based on platform."""
        if self.system == "windows":
            return {"System Volume Information", "$RECYCLE.BIN", "$WinREAgent"}
        elif self.system == "linux":
            return {"/proc", "/sys", "/dev", "/run"}
        else:  # macOS and others
            return set()

    def _get_platform_skip_files(self) -> Set[str]:
        """Get file patterns to skip based on platform."""
        # Skip hidden files on all platforms
        return {".*"}

    def _should_skip_dir(self, dir_path: Path) -> bool:
        """Check if directory should be skipped."""
        name = dir_path.name

        # Skip hidden directories
        if name.startswith('.'):
            return True

        # Skip platform-specific system directories
        if name in self._skip_dirs:
            return True

        # Linux-specific: skip virtual filesystems
        if self.system == "linux":
            try:
                resolved = str(dir_path.resolve())
                if any(resolved.startswith(root) for root in {"/proc", "/sys", "/dev", "/run"}):
                    return True
            except Exception:
                return True

        return False

    def _should_skip_file(self, file_path: Path) -> bool:
        """Check if file should be skipped."""
        name = file_path.name

        # Skip hidden files
        if name.startswith('.'):
            return True

        # macOS-specific: skip iCloud placeholders
        if self.system == "darwin":
            if name.endswith('.icloud'):
                return True
            # Check for zero-size files (potential placeholders)
            try:
                if file_path.stat().st_size == 0:
                    return True
            except Exception:
                return True

        return False

    def _is_icloud_placeholder(self, file_path: Path) -> bool:
        """Check if file is an iCloud placeholder (macOS-specific)."""
        if self.system != "darwin":
            return False

        try:
            import xattr
            xa = xattr.xattr(file_path)
            finfo = xa.get(b'com.apple.FinderInfo', b'')
            if len(finfo) >= 9 and finfo[8] & 0x01:  # kIsUbiquitousItem
                return True
        except (ImportError, OSError, KeyError):
            pass
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
                    # Filter directories in-place to skip unwanted ones
                    current_dir = Path(dirpath)
                    dirnames[:] = [d for d in dirnames if not self._should_skip_dir(current_dir / d)]

                    for filename in filenames:
                        p = current_dir / filename
                        if self._should_skip_file(p) or self._is_icloud_placeholder(p):
                            continue
                        if any(sub in str(p) for sub in exclude_subs):
                            continue
                        if p.suffix.lower() in ext_set:
                            all_files.append(p)
            else:
                try:
                    for entry in os.scandir(root_path):
                        if entry.is_file():
                            p = Path(entry.path)
                            if (not self._should_skip_file(p) and
                                not self._is_icloud_placeholder(p) and
                                not any(sub in str(p) for sub in exclude_subs) and
                                p.suffix.lower() in ext_set):
                                all_files.append(p)
                except PermissionError:
                    logger.debug(f"Permission denied accessing: {root_path}")
                    continue

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

