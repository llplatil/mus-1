"""Baseline DLC tracking confidence — task-agnostic.

Computes a small fixed set of statistics from a DLC predictions CSV that
operators can use to decide whether an experiment is worth a deeper QC
pass *before* running task-specific compute (zone classification,
interaction metrics, ...).  The principle: ``don't try to polish
garbage`` — surface tracking quality at the top of every Tracking QC
pane.

This module is **pure-functional and deterministic** (no side effects,
no I/O outside of opening the path it is given). The output shape is
authoritative for ``extraction.tracking_confidence`` per
``docs/web/SCHEMA_VARIANTS.md``.

Threshold defaults follow DeepLabCut's documented conventions:

- ``pcutoff = 0.6`` is DLC's default likelihood cutoff
  (``deeplabcut/pose_cfg.yaml`` default; cited in the DLC user guide
  filtering docs).
- The "≥80% above pcutoff is analyzable" convention appears in the
  DLC user-guide section on filtering predictions and in the
  community follow-up papers on DLC quality control.

Thresholds are overridable via ``mus1.preferences.compute.tracking_confidence``
when wired through the CLI / pane (see Phase A5).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd


MODULE_VERSION = "1.0"

#: DeepLabCut default likelihood cutoff. See DLC ``pose_cfg.yaml``.
DEFAULT_PCUTOFF: float = 0.6

#: Below this fraction of frames-above-pcutoff (median across bodyparts),
#: an experiment is flagged ``LOW_LIKELIHOOD_OVERALL``. Mirrors the
#: ≥80% community convention.
DEFAULT_OVERALL_FRAC_THRESHOLD: float = 0.80

#: Below this fraction for any single bodypart → ``BODYPART_FAILURE``.
#: A failing bodypart usually signals occlusion or a labelling gap;
#: even if the rest of the animal is tracked, downstream zone/interaction
#: compute that depends on this bodypart will be unreliable.
DEFAULT_BODYPART_FRAC_THRESHOLD: float = 0.50

#: Continuous run of frames where *every* bodypart is below pcutoff
#: ≥ this many frames → ``LIKELIHOOD_DROPOUT_RUN``. 30 frames ~ 0.5 s
#: at 60 fps and ~1 s at 30 fps; long enough to matter, short enough to
#: catch real lapses without false-positives on momentary occlusions.
DEFAULT_DROPOUT_MIN_FRAMES: int = 30


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_tracking_confidence(
    csv_path: Path | str,
    *,
    pcutoff: float = DEFAULT_PCUTOFF,
    overall_frac_threshold: float = DEFAULT_OVERALL_FRAC_THRESHOLD,
    bodypart_frac_threshold: float = DEFAULT_BODYPART_FRAC_THRESHOLD,
    dropout_min_frames: int = DEFAULT_DROPOUT_MIN_FRAMES,
) -> Dict[str, Any]:
    """Return a baseline DLC confidence summary for one experiment.

    Parameters
    ----------
    csv_path : path to the DLC predictions CSV (3-row multi-index header).
    pcutoff : likelihood cutoff used for ``frac_above_pcutoff``.
    overall_frac_threshold : fires ``LOW_LIKELIHOOD_OVERALL`` below this.
    bodypart_frac_threshold : fires ``BODYPART_FAILURE`` per-bodypart.
    dropout_min_frames : fires ``LIKELIHOOD_DROPOUT_RUN`` for runs ≥ this.

    Returns
    -------
    dict matching the schema in ``SCHEMA_VARIANTS.md``::

        {
            "computed_at": ISO-8601 UTC,
            "module_version": "...",
            "pcutoff": 0.6,
            "per_bodypart": {bp: {mean_likelihood, median_likelihood,
                                  frac_above_pcutoff,
                                  longest_dropout_run_frames}, ...},
            "overall": {n_frames, median_frac_above_pcutoff,
                        min_bodypart_frac_above_pcutoff,
                        longest_any_dropout_run_frames},
            "flags": ["LOW_LIKELIHOOD_OVERALL", ...],   ← may be empty
            "thresholds": {pcutoff, overall_frac_threshold, ...},
            "csv_path": "...",
            "error": null | "..."   ← present on parse failure
        }

    Never raises; on parse failure returns a populated ``error`` string
    and zeroed stats so callers can record the attempt.
    """
    csv_path = Path(csv_path)
    base = _empty_result(pcutoff, overall_frac_threshold,
                         bodypart_frac_threshold, dropout_min_frames,
                         csv_path)

    df = _try_read_dlc_csv(csv_path)
    if df is None:
        base["error"] = f"could not read DLC CSV at {csv_path}"
        return base

    likelihood_by_bp = _likelihood_columns(df)
    if not likelihood_by_bp:
        base["error"] = "DLC CSV has no recognizable likelihood columns"
        return base

    n_frames = int(len(df))
    base["overall"]["n_frames"] = n_frames

    # Per-bodypart stats
    bodypart_fracs: List[float] = []
    bodypart_dropouts: List[int] = []
    for bp, lh in likelihood_by_bp.items():
        lh_arr = pd.to_numeric(lh, errors="coerce").to_numpy(dtype=float)
        valid = np.isfinite(lh_arr)
        if not valid.any():
            base["per_bodypart"][bp] = _empty_bodypart_stats()
            continue
        above = lh_arr >= pcutoff
        # Dropout runs for THIS bodypart: continuous below-pcutoff frames
        bp_longest_dropout = _longest_run(~above & valid)
        mean_lh = float(np.nanmean(lh_arr))
        median_lh = float(np.nanmedian(lh_arr))
        frac_above = float(above.sum() / n_frames) if n_frames > 0 else 0.0
        base["per_bodypart"][bp] = {
            "mean_likelihood": _round(mean_lh, 4),
            "median_likelihood": _round(median_lh, 4),
            "frac_above_pcutoff": _round(frac_above, 4),
            "longest_dropout_run_frames": int(bp_longest_dropout),
        }
        bodypart_fracs.append(frac_above)
        bodypart_dropouts.append(int(bp_longest_dropout))

    # All-bodyparts-low frame mask: dropout when *every* bodypart < pcutoff
    all_below = np.ones(n_frames, dtype=bool)
    for bp, lh in likelihood_by_bp.items():
        lh_arr = pd.to_numeric(lh, errors="coerce").to_numpy(dtype=float)
        all_below &= (lh_arr < pcutoff) | ~np.isfinite(lh_arr)
    longest_any_dropout = int(_longest_run(all_below))

    if bodypart_fracs:
        base["overall"]["median_frac_above_pcutoff"] = _round(
            float(np.median(bodypart_fracs)), 4)
        base["overall"]["min_bodypart_frac_above_pcutoff"] = _round(
            float(min(bodypart_fracs)), 4)
    base["overall"]["longest_any_dropout_run_frames"] = longest_any_dropout

    # Flags
    flags: List[str] = []
    if (base["overall"]["median_frac_above_pcutoff"] is not None
            and base["overall"]["median_frac_above_pcutoff"] < overall_frac_threshold):
        flags.append("LOW_LIKELIHOOD_OVERALL")
    if (base["overall"]["min_bodypart_frac_above_pcutoff"] is not None
            and base["overall"]["min_bodypart_frac_above_pcutoff"] < bodypart_frac_threshold):
        flags.append("BODYPART_FAILURE")
    if longest_any_dropout >= dropout_min_frames:
        flags.append("LIKELIHOOD_DROPOUT_RUN")
    base["flags"] = flags

    return base


def render_summary_text(result: Dict[str, Any]) -> str:
    """One-screen human-readable summary, suitable for CLI stdout."""
    if result.get("error"):
        return f"tracking_confidence: ERROR — {result['error']}"
    o = result.get("overall") or {}
    flags = result.get("flags") or []
    lines = [
        f"frames           : {o.get('n_frames', 0)}",
        f"median frac >= {result.get('pcutoff', 0):.2f} : "
        f"{(o.get('median_frac_above_pcutoff') or 0)*100:.1f}%",
        f"min bp  frac >= {result.get('pcutoff', 0):.2f} : "
        f"{(o.get('min_bodypart_frac_above_pcutoff') or 0)*100:.1f}%",
        f"longest all-low run     : {o.get('longest_any_dropout_run_frames', 0)} frames",
        f"flags                  : {', '.join(flags) if flags else '(none)'}",
        "",
        "per-bodypart:",
    ]
    for bp, st in (result.get("per_bodypart") or {}).items():
        lines.append(
            f"  {bp:<14s} mean={st.get('mean_likelihood', 0):.3f} "
            f"frac={st.get('frac_above_pcutoff', 0)*100:.1f}% "
            f"longest_dropout={st.get('longest_dropout_run_frames', 0)} fr"
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Helpers — kept module-private; reuse compute.tracking when possible
# ---------------------------------------------------------------------------

def _try_read_dlc_csv(csv_path: Path) -> Optional[pd.DataFrame]:
    """Read a 3-level-header DLC CSV; return None if unreadable.

    Mirrors the pattern in ``mus1.compute.tracking.try_read_dlc_csv`` but
    uses the local 3-level read directly so this module has zero coupling
    to the rest of the compute library.
    """
    if not csv_path.exists():
        return None
    try:
        df = pd.read_csv(csv_path, header=[0, 1, 2], index_col=0)
    except Exception:
        return None
    if not isinstance(df.columns, pd.MultiIndex) or df.columns.nlevels != 3:
        return None
    try:
        df.columns = df.columns.droplevel(0)
    except Exception:
        return None
    return df


def _likelihood_columns(df: pd.DataFrame) -> Dict[str, pd.Series]:
    """Return ``{bodypart: likelihood_series}`` for every bp present."""
    out: Dict[str, pd.Series] = {}
    if not isinstance(df.columns, pd.MultiIndex):
        return out
    bodyparts = sorted(set(df.columns.get_level_values(0)))
    for bp in bodyparts:
        try:
            out[bp] = df[(bp, "likelihood")]
        except KeyError:
            continue
    return out


def _longest_run(mask: np.ndarray) -> int:
    """Length of the longest contiguous True run in *mask*. 0 if none."""
    if mask.size == 0:
        return 0
    longest = 0
    cur = 0
    for v in mask:
        if v:
            cur += 1
            if cur > longest:
                longest = cur
        else:
            cur = 0
    return longest


def _round(value: float, places: int) -> Optional[float]:
    if value is None or not np.isfinite(value):
        return None
    return round(float(value), places)


def _empty_bodypart_stats() -> Dict[str, Any]:
    return {
        "mean_likelihood": None,
        "median_likelihood": None,
        "frac_above_pcutoff": None,
        "longest_dropout_run_frames": 0,
    }


def _empty_result(pcutoff: float, overall_frac: float, bp_frac: float,
                  dropout_min: int, csv_path: Path) -> Dict[str, Any]:
    return {
        "computed_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "module_version": MODULE_VERSION,
        "pcutoff": pcutoff,
        "per_bodypart": {},
        "overall": {
            "n_frames": 0,
            "median_frac_above_pcutoff": None,
            "min_bodypart_frac_above_pcutoff": None,
            "longest_any_dropout_run_frames": 0,
        },
        "flags": [],
        "thresholds": {
            "pcutoff": pcutoff,
            "overall_frac_threshold": overall_frac,
            "bodypart_frac_threshold": bp_frac,
            "dropout_min_frames": dropout_min,
        },
        "csv_path": str(csv_path),
        "error": None,
    }
