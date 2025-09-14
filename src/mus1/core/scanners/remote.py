from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Iterable, Iterator, List, Tuple, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

# TODO: Update to use new clean architecture
# from ..data_manager import DataManager
# from ..state_manager import StateManager
from ..metadata import ScanTarget


def _iter_json_lines(text: str) -> Iterator[dict]:
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            continue


def _build_scan_cmd_for_target(target: ScanTarget, *, extensions: Optional[List[str]] = None, exclude_dirs: Optional[List[str]] = None, non_recursive: bool = False) -> List[str]:
    """Build a remote command that produces JSONL path/hash records using mus1 scan videos.

    For kind == local we do not build a command; local scanning is handled via DataManager.
    """
    if target.kind not in ("ssh", "wsl"):
        raise ValueError("Remote command requested for non-remote target")
    if not target.ssh_alias:
        raise ValueError("ssh_alias is required for remote targets")

    remote_prog: List[str]
    if target.kind == "ssh":
        remote_prog = ["ssh", "-o", "BatchMode=yes", target.ssh_alias, "mus1", "scan", "videos"]
    else:  # wsl
        # Run WSL mus1 via wsl.exe on the remote Windows host
        remote_prog = ["ssh", "-o", "BatchMode=yes", target.ssh_alias, "wsl.exe", "-e", "mus1", "scan", "videos"]

    # Add roots
    for r in target.roots:
        remote_prog.append(str(r))
    # Add options
    if extensions:
        for ext in extensions:
            remote_prog.extend(["--ext", ext])
    if exclude_dirs:
        for ex in exclude_dirs:
            remote_prog.extend(["--exclude-dirs", ex])
    if non_recursive:
        remote_prog.append("--non-recursive")
    # Disable progress for clean stdout
    remote_prog.extend(["--progress", "false"])
    return remote_prog


def collect_from_target(
    state_manager: StateManager,
    data_manager: DataManager,
    target: ScanTarget,
    *,
    extensions: Optional[List[str]] = None,
    exclude_dirs: Optional[List[str]] = None,
    non_recursive: bool = False,
) -> List[Tuple[Path, str]]:
    """Collect (path, hash) tuples for a single target.

    Local targets use DataManager; remote targets invoke mus1 remotely via SSH.
    Returns a materialized list for progress/dedup convenience.
    """
    if target.kind == "local":
        return list(
            data_manager.discover_video_files(
                [Path(r) for r in target.roots],
                extensions=extensions,
                recursive=not non_recursive,
                excludes=exclude_dirs,
            )
        )

    # Remote: run mus1 over SSH/WSL and parse stdout JSONL
    cmd = _build_scan_cmd_for_target(
        target,
        extensions=extensions,
        exclude_dirs=exclude_dirs,
        non_recursive=non_recursive,
    )
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        err = (proc.stderr or "").strip()
        raise RuntimeError(f"Remote scan failed for {target.name} ({target.ssh_alias}): {err}")
    items: List[Tuple[Path, str]] = []
    for rec in _iter_json_lines(proc.stdout or ""):
        try:
            p = Path(rec["path"])  # path as seen on remote; may not be directly accessible locally
            h = str(rec["hash"]) 
            items.append((p, h))
        except Exception:
            continue
    return items


def collect_from_targets(
    state_manager: StateManager,
    data_manager: DataManager,
    targets: Iterable[ScanTarget],
    *,
    extensions: Optional[List[str]] = None,
    exclude_dirs: Optional[List[str]] = None,
    non_recursive: bool = False,
) -> List[Tuple[Path, str]]:
    """Collect and concatenate lists across all targets.

    This function does not deduplicate; callers can pass the result into
    DataManager.deduplicate_video_list.
    """
    all_items: List[Tuple[Path, str]] = []
    for t in targets:
        all_items.extend(
            collect_from_target(
                state_manager,
                data_manager,
                t,
                extensions=extensions,
                exclude_dirs=exclude_dirs,
                non_recursive=non_recursive,
            )
        )
    return all_items


def collect_from_targets_parallel(
    state_manager: StateManager,
    data_manager: DataManager,
    targets: Iterable[ScanTarget],
    *,
    extensions: Optional[List[str]] = None,
    exclude_dirs: Optional[List[str]] = None,
    non_recursive: bool = False,
    max_workers: int = 4,
) -> List[Tuple[Path, str]]:
    """Parallel version of collect_from_targets using threads.

    Each target is collected independently; failures are isolated and logged to stderr.
    """
    all_items: List[Tuple[Path, str]] = []
    targets_list = list(targets)
    if not targets_list:
        return all_items

    def _task(t: ScanTarget) -> List[Tuple[Path, str]]:
        return collect_from_target(
            state_manager,
            data_manager,
            t,
            extensions=extensions,
            exclude_dirs=exclude_dirs,
            non_recursive=non_recursive,
        )

    with ThreadPoolExecutor(max_workers=max_workers) as exe:
        future_map = {exe.submit(_task, t): t for t in targets_list}
        for fut in as_completed(future_map):
            t = future_map[fut]
            try:
                items = fut.result()
                all_items.extend(items)
            except Exception as e:
                # Best-effort propagate information without stopping the entire run
                print(f"Warning: scan failed for target '{t.name}': {e}")
    return all_items


