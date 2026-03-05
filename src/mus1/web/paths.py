from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Tuple


def resolve_db_path(project_path: Path) -> Tuple[Path, Path]:
    """
    Accept either:
    - a project directory containing mus1.db
    - a direct path to mus1.db

    Returns (project_dir, db_path).
    """
    p = Path(project_path).expanduser()
    if p.is_file() and p.name.endswith(".db"):
        return p.parent, p
    return p, (p / "mus1.db")


def resolve_session_index_csv(workspace_root: Optional[str]) -> Optional[Path]:
    """
    Prefer the workspace contract CSV, but fall back to the curated copy under MUS1.
    """
    if not workspace_root:
        return None

    ws = Path(str(workspace_root)).expanduser()
    # workspace_root is now the WDMOSEQ2 repo root
    p0 = ws / "ml_workspace" / "ml_tracking_metadata_model" / "index" / "session_index_filtered.csv"
    if p0.exists():
        return p0

    repo_root = Path(__file__).resolve().parents[3]
    p1 = repo_root / "workspace" / "contracts" / "ml_tracking_metadata_model" / "index" / "session_index_filtered.csv"
    if p1.exists():
        return p1
    return None


def resolve_dlc_config_path(p: Path) -> Optional[Path]:
    """
    Accept either:
    - a DLC project directory containing config.yaml
    - a direct path to config.yaml
    """
    pp = Path(p).expanduser()
    if pp.is_file() and pp.name == "config.yaml":
        return pp
    cfg = pp / "config.yaml"
    return cfg if cfg.exists() else None


def resolve_dlc_project_config_from_id(workspace_root: Optional[str], dlc_project_id: str) -> Optional[Path]:
    """
    Convert a DLC project id (folder name under dlc_projects/ or dlc_workspace/projects/) into a config.yaml path.
    Prefers Stage 2 layout: WDMOSEQ2/dlc_workspace/projects/<id>/config.yaml.
    """
    if not dlc_project_id:
        return None
    ws = Path(str(workspace_root)).expanduser() if workspace_root else None
    candidates: List[Path] = []
    if ws:
        # Stage 2: DLC at repo root dlc_workspace/projects/
        repo = ws.parent
        candidates.append(repo / "dlc_workspace" / "projects" / dlc_project_id / "config.yaml")
        # Legacy: under moseq2_workspace/data/behavior_videos/dlc_projects
        candidates.append(ws / "data" / "behavior_videos" / "dlc_projects" / dlc_project_id / "config.yaml")
    # Common mount alias between workspace and project config.
    for c in list(candidates):
        s = str(c)
        if s.startswith("/center1/"):
            candidates.append(Path("/import/c1/" + s[len("/center1/") :]))
        elif s.startswith("/import/c1/"):
            candidates.append(Path("/center1/" + s[len("/import/c1/") :]))
    # Fallback absolute lookups (Stage 2 layout first).
    base = Path("/center1/WDMOSEQ2/llplatil/WDMOSEQ2")
    for base_path in (base, Path("/import/c1/WDMOSEQ2/llplatil/WDMOSEQ2")):
        candidates.append(base_path / "dlc_workspace" / "projects" / dlc_project_id / "config.yaml")
        candidates.append(base_path / "moseq2_workspace" / "data" / "behavior_videos" / "dlc_projects" / dlc_project_id / "config.yaml")
    seen: set[str] = set()
    for c in candidates:
        cs = str(c)
        if cs in seen:
            continue
        seen.add(cs)
        if c.exists():
            return c
    # Fall back to the first candidate (useful for display even if missing)
    return candidates[0] if candidates else None


def path_aliases(p: Path) -> List[str]:
    """
    Return a small set of canonical/aliased path strings for matching.

    This workspace commonly references the same files via both:
    - /center1/... (canonical)
    - /import/c1/... (alternate mount path)
    """
    out: List[str] = []
    s = str(p)
    out.append(s)
    try:
        out.append(str(p.resolve()))
    except Exception:
        pass
    if s.startswith("/import/c1/"):
        out.append("/center1/" + s[len("/import/c1/") :])
    elif s.startswith("/center1/"):
        out.append("/import/c1/" + s[len("/center1/") :])
    # unique, preserve order
    uniq: List[str] = []
    seen: set[str] = set()
    for x in out:
        if x in seen:
            continue
        seen.add(x)
        uniq.append(x)
    return uniq


def normalize_basename(basename: Optional[str]) -> Optional[str]:
    if not basename:
        return None
    b = str(basename)
    if "DLC_" in b:
        b = b.split("DLC_")[0]
        if not b.endswith(".mp4"):
            b = b + ".mp4"
    return b


def safe_stem_annotator(video_path: str) -> str:
    # Match arena annotator's safe stem behavior.
    return Path(str(video_path)).stem.replace(" ", "_").replace("/", "_")


def default_nor_nof_outdir(repo_root: Path) -> Path:
    return repo_root / "workspace" / "arena_zones" / "nor_nof_per_video_v2"


def _safe_token(s: str) -> str:
    import re
    tok = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(s or "").strip()).strip("._-")
    return tok or "unknown"


def find_nor_nof_roi_json(
    outdir: Path,
    video_path: str,
    session_id: str = "",
) -> Optional[Path]:
    """Find the saved ROI JSON for a video, checking both filename patterns.

    The annotator saves as ``{session_id}__{safe_stem}_nor_nof_objects_v2.json``
    when *session_id* is present and ``{safe_stem}_nor_nof_objects_v2.json``
    otherwise.  This helper returns the first existing path it finds.
    """
    stem = safe_stem_annotator(video_path)
    # Pattern with session_id prefix (annotator's default when available)
    if session_id:
        prefixed = outdir / f"{_safe_token(session_id)}__{stem}_nor_nof_objects_v2.json"
        if prefixed.exists():
            return prefixed
    # Pattern without session_id prefix
    plain = outdir / f"{stem}_nor_nof_objects_v2.json"
    if plain.exists():
        return plain
    # Also check session-id prefix even when session_id not supplied (best-effort glob)
    if not session_id:
        hits = sorted(outdir.glob(f"*__{stem}_nor_nof_objects_v2.json"))
        if hits:
            return hits[0]
    return None

