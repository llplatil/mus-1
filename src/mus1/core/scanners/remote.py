from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Iterator, List, Tuple, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

from ..metadata import ScanTarget
from ..job_provider import SshJobProvider, SshWslJobProvider


def _iter_json_lines(text: str) -> Iterator[dict]:
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            continue


def _build_remote_scan_command(target: ScanTarget, *, extensions: Optional[List[str]] = None, exclude_dirs: Optional[List[str]] = None, non_recursive: bool = False) -> List[str]:
    """Build a remote mus1 scan command (without ssh wrapper)."""
    cmd: List[str] = ["mus1", "scan", "videos"]
    for r in target.roots:
        cmd.append(str(r))
    if extensions:
        for ext in extensions:
            cmd.extend(["--ext", ext])
    if exclude_dirs:
        for ex in exclude_dirs:
            cmd.extend(["--exclude-dirs", ex])
    if non_recursive:
        cmd.append("--non-recursive")
    cmd.extend(["--progress", "false"])  # clean JSONL
    return cmd


def collect_from_target(
    state_manager,  # deprecated in this module; kept for signature compatibility
    data_manager,   # deprecated in this module; kept for signature compatibility
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

    # Remote: run mus1 over SSH/WSL via job providers and parse stdout JSONL
    if not target.ssh_alias:
        raise ValueError("ssh_alias is required for remote targets")

    cmd = _build_remote_scan_command(
        target,
        extensions=extensions,
        exclude_dirs=exclude_dirs,
        non_recursive=non_recursive,
    )
    if target.kind == "ssh":
        provider = SshJobProvider()
        result = provider.run(target.ssh_alias, cmd, stream_output=False, log_prefix=f"scan:{target.name}")
    elif target.kind == "wsl":
        provider = SshWslJobProvider()
        result = provider.run(target.ssh_alias, cmd, stream_output=False, log_prefix=f"scan:{target.name}")
    else:
        raise ValueError("Remote command requested for non-remote target")

    if result.return_code != 0:
        err = (result.stderr or "").strip()
        raise RuntimeError(f"Remote scan failed for {target.name} ({target.ssh_alias}): {err}")
    items: List[Tuple[Path, str]] = []
    for rec in _iter_json_lines(result.stdout or ""):
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


