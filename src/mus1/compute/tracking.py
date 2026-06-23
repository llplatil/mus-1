"""Shared DLC/SLEAP tracking utilities.

Functions for reading pose-estimation CSVs, filtering by likelihood,
interpolating gaps, and extracting bodypart tracks. Used by both
EZM and NOR/NOF compute pipelines.

These are the same patterns duplicated in ezm_compute_bridge._bp_track(),
nor_nof_object_interactions._bp_track(), and overlay.load_dlc_tracks().
Consolidated here as the single implementation.

Schema-duality resolver ``resolve_dlc_csv_path`` also lives here (moved
2026-05-04 from ``mus1.web.discovery`` per ROADMAP §5.4b — it is a
pure function over an ``extraction`` dict with no UI coupling).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# DLC run registry — multiple trackings per experiment
# ---------------------------------------------------------------------------
#
# An experiment may have several DLC trackings (e.g. a v1 production model
# and a v2 candidate). Each is recorded as an entry under
# ``extraction.dlc_runs[]``. Two older schemas also exist and are folded
# into the same view by :func:`list_dlc_runs`:
#   • Legacy (publication batches): ``extraction.tracking_file_path`` +
#     ``extraction.dlc_model_path`` (the scorer string).
#   • New (validation_2026 batches): ``extraction.dlc_runs[]`` with no
#     legacy flat field.
#
# ``run_id`` is the stable, cross-experiment identifier for a model. We use
# the DLC ``scorer`` string because it is DLC-canonical (uniquely encodes
# net + project-task + shuffle + snapshot) and is recorded consistently,
# whereas ``dlc_project`` is stored inconsistently across batches (full dir
# name vs. short task name). When a scorer is absent we fall back to
# ``{project_basename}__{snapshot}``.


def derive_run_id(scorer: str = "", dlc_project: str = "", snapshot: str = "") -> str:
    """Return the stable cross-experiment identifier for a DLC model run.

    Prefers the DLC ``scorer`` string; falls back to
    ``{project_basename}__{snapshot}`` when the scorer is unavailable.
    Returns ``""`` when nothing identifying is present.
    """
    s = (scorer or "").strip()
    if s:
        return s
    proj = Path((dlc_project or "").strip()).name if (dlc_project or "").strip() else ""
    snap = (snapshot or "").strip()
    if proj or snap:
        return f"{proj}__{snap}"
    return ""


@dataclass(frozen=True)
class DlcRun:
    """Normalized view of one DLC tracking registered against an experiment."""

    run_id: str
    csv_path: str
    scorer: str = ""
    dlc_project: str = ""
    snapshot: str = ""
    shuffle: int = 1
    h5_path: str = ""
    config: str = ""
    analysis_at: str = ""
    primary: bool = False
    source: str = "dlc_runs"  # "dlc_runs" | "legacy"
    note: str = ""

    @property
    def model_label(self) -> str:
        """Short human label for UI selectors."""
        proj = Path(self.dlc_project).name if self.dlc_project else ""
        snap = self.snapshot or ""
        if proj and snap:
            return f"{proj} @ {snap}"
        if proj:
            return proj
        return self.run_id or "(unknown)"


def list_dlc_runs(extraction: Optional[Dict[str, Any]]) -> List[DlcRun]:
    """Return every DLC tracking registered against an experiment.

    Unions ``extraction.dlc_runs[]`` with a synthetic entry built from the
    legacy ``tracking_file_path`` / ``dlc_model_path`` fields (deduplicated
    by CSV path). Order: ``dlc_runs[]`` entries first (in file order), then
    the legacy entry if its CSV is not already present.
    """
    if not isinstance(extraction, dict):
        return []
    out: List[DlcRun] = []
    seen_csv: set[str] = set()
    for entry in extraction.get("dlc_runs") or []:
        if not isinstance(entry, dict):
            continue
        output = entry.get("output") or {}
        csv = str(output.get("csv") or "")
        scorer = str(entry.get("scorer") or "")
        dlc_project = str(entry.get("dlc_project") or "")
        snapshot = str(entry.get("snapshot") or "")
        try:
            shuffle = int(entry.get("shuffle", 1))
        except (TypeError, ValueError):
            shuffle = 1
        out.append(
            DlcRun(
                run_id=derive_run_id(scorer, dlc_project, snapshot),
                csv_path=csv,
                scorer=scorer,
                dlc_project=dlc_project,
                snapshot=snapshot,
                shuffle=shuffle,
                h5_path=str(output.get("h5") or ""),
                config=str(entry.get("config") or ""),
                analysis_at=str(entry.get("analysis_at") or ""),
                primary=bool(entry.get("primary")),
                source="dlc_runs",
                note=str(entry.get("note") or ""),
            )
        )
        if csv:
            seen_csv.add(csv)
    legacy_csv = str(extraction.get("tracking_file_path") or "")
    if legacy_csv and legacy_csv not in seen_csv:
        scorer = str(extraction.get("dlc_model_path") or "")
        out.append(
            DlcRun(
                run_id=derive_run_id(scorer, "", ""),
                csv_path=legacy_csv,
                scorer=scorer,
                source="legacy",
            )
        )
    return out


def get_dlc_run(extraction: Optional[Dict[str, Any]], run_id: str) -> Optional[DlcRun]:
    """Return the registered run whose ``run_id`` matches, or None."""
    if not run_id:
        return None
    for run in list_dlc_runs(extraction):
        if run.run_id == run_id:
            return run
    return None


def resolve_dlc_csv_path(
    extraction: Optional[Dict[str, Any]],
    *,
    cohort: Optional[Dict[str, Any]] = None,
) -> str:
    """Return the DLC tracking CSV path for an experiment.

    Selection precedence:
      1. A per-experiment override: a ``dlc_runs[]`` entry flagged
         ``primary: true`` wins (manual "use this model for this session").
      2. The cohort's selected model, when *cohort* is given:
         ``cohort.analysis_config.dlc_model.run_id`` is matched against the
         registered runs.
      3. Legacy ``extraction.tracking_file_path`` (publication batches).
      4. The last ``extraction.dlc_runs[]`` entry (validation_2026 batches).

    When *cohort* is ``None`` and no entry is flagged ``primary``, steps 1-2
    are skipped and behavior is identical to the original resolver (legacy
    field, else last ``dlc_runs[]`` entry) — preserving every existing
    call site.
    """
    if not isinstance(extraction, dict):
        return ""

    # 1. Per-experiment primary override.
    for run in list_dlc_runs(extraction):
        if run.primary and run.source == "dlc_runs" and run.csv_path:
            return run.csv_path

    # 2. Cohort-level model selection.
    if isinstance(cohort, dict):
        selected = (
            ((cohort.get("analysis_config") or {}).get("dlc_model") or {})
        ).get("run_id") or ""
        if selected:
            run = get_dlc_run(extraction, selected)
            if run is not None and run.csv_path:
                return run.csv_path

    # 3-4. Original behavior, preserved byte-for-byte for back-compat.
    legacy = extraction.get("tracking_file_path") or ""
    if legacy:
        return legacy
    runs = extraction.get("dlc_runs") or []
    if runs:
        last = runs[-1] if isinstance(runs[-1], dict) else {}
        out = last.get("output") or {}
        return out.get("csv") or ""
    return ""


def selected_dlc_run(
    extraction: Optional[Dict[str, Any]],
    *,
    cohort: Optional[Dict[str, Any]] = None,
) -> Optional[DlcRun]:
    """Return the full :class:`DlcRun` chosen by :func:`resolve_dlc_csv_path`.

    Single source of truth for selection: resolves the CSV path, then
    returns the registered run that owns it.
    """
    csv = resolve_dlc_csv_path(extraction, cohort=cohort)
    if not csv:
        return None
    for run in list_dlc_runs(extraction):
        if run.csv_path == csv:
            return run
    return None


def make_dlc_run_entry(
    *,
    dlc_project: str,
    snapshot: str,
    csv: str,
    scorer: str = "",
    shuffle: int = 1,
    config: str = "",
    h5: str = "",
    note: str = "",
    primary: bool = False,
    analysis_at: Optional[str] = None,
) -> Dict[str, Any]:
    """Build a well-formed ``extraction.dlc_runs[]`` entry.

    Mirrors the schema written by the dlc_workspace registration scripts.
    The caller appends the returned dict to ``extraction.dlc_runs``.
    """
    entry: Dict[str, Any] = {
        "analysis_at": analysis_at or datetime.now(timezone.utc).isoformat(),
        "dlc_project": dlc_project,
        "config": config,
        "scorer": scorer,
        "shuffle": int(shuffle),
        "snapshot": snapshot,
        "output": {"csv": csv, "h5": h5},
        "run_id": derive_run_id(scorer, dlc_project, snapshot),
    }
    if primary:
        entry["primary"] = True
    if note:
        entry["note"] = note
    return entry


def try_read_dlc_csv(path: Path) -> Optional[pd.DataFrame]:
    """Read a DLC CSV with 3-row header into a (bodypart, coord) MultiIndex DataFrame.

    Returns None if the file is unreadable or has the wrong structure.
    """
    try:
        df = pd.read_csv(path, header=[0, 1, 2], index_col=0)
    except Exception:
        return None
    if not isinstance(df.columns, pd.MultiIndex) or df.columns.nlevels != 3:
        return None
    try:
        df.columns = df.columns.droplevel(0)
    except Exception:
        return None
    if not isinstance(df.columns, pd.MultiIndex) or df.columns.nlevels != 2:
        return None
    return df


def bp_track(
    df: pd.DataFrame,
    bodypart: str,
    likelihood_threshold: float = 0.6,
    max_interp_gap: int = 10,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Extract a single bodypart track with likelihood filtering + interpolation.

    Returns (x, y, ok) arrays of length len(df).
    """
    x = pd.to_numeric(df[(bodypart, "x")], errors="coerce")
    y = pd.to_numeric(df[(bodypart, "y")], errors="coerce")
    p = pd.to_numeric(df[(bodypart, "likelihood")], errors="coerce")
    above = p >= likelihood_threshold
    xf = x.where(above)
    yf = y.where(above)
    # max_interp_gap <= 0 means "do not interpolate" (raw filtered track).
    # pandas raises on interpolate(limit=0), so guard explicitly. This is
    # what tracking-comparison needs to see unsmoothed model disagreement.
    if max_interp_gap and max_interp_gap > 0:
        xf = xf.interpolate(limit=max_interp_gap, limit_direction="both")
        yf = yf.interpolate(limit=max_interp_gap, limit_direction="both")
    ok = (xf.notna() & yf.notna()).to_numpy(dtype=bool)
    return xf.to_numpy(dtype=float), yf.to_numpy(dtype=float), ok


def load_all_tracks(
    path: Path,
    likelihood_threshold: float = 0.6,
    max_interp_gap: int = 10,
) -> Optional[Dict[str, Dict[str, np.ndarray]]]:
    """Read DLC CSV and return filtered tracks for all bodyparts.

    Returns ``{bodypart: {"x": ..., "y": ..., "ok": ...}}`` or None.
    """
    df = try_read_dlc_csv(path)
    if df is None:
        return None
    bodyparts = sorted(set(df.columns.get_level_values(0)))
    out: Dict[str, Dict[str, np.ndarray]] = {}
    for bp in bodyparts:
        try:
            x, y, ok = bp_track(df, bp, likelihood_threshold, max_interp_gap)
        except KeyError:
            continue
        out[bp] = {"x": x, "y": y, "ok": ok}
    return out if out else None


def list_bodyparts(df: pd.DataFrame) -> list[str]:
    """Return sorted list of bodypart names in a DLC DataFrame."""
    return sorted(set(df.columns.get_level_values(0)))


def speed_px_per_frame(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Frame-to-frame speed in pixels. First frame is NaN."""
    dx = np.diff(np.asarray(x, dtype=float))
    dy = np.diff(np.asarray(y, dtype=float))
    return np.concatenate([[np.nan], np.sqrt(dx * dx + dy * dy)])
