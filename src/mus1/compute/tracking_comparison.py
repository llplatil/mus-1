"""Compare two DLC trackings of the same video.

Pure compute — no UI, no disk writes beyond reading the two CSVs it is
given. Produces per-bodypart agreement / coverage statistics, a per-frame
disagreement timeline, and a catalogue of the worst-disagreement frames so
a reviewer can jump straight to where two models diverge.

Interpolation is OFF by default (``max_interp_gap=0``): we want to see raw
model disagreement, not gaps smoothed over by interpolation.

Undefined statistics (e.g. median distance when no frame has both
bodyparts above threshold) are ``float('nan')`` in-memory. Callers that
serialize to JSON should convert NaN to ``None`` at the boundary
(:func:`comparison_to_jsonable` does this).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

from .tracking import bp_track, list_bodyparts, try_read_dlc_csv


@dataclass(frozen=True)
class PerBodypartComparison:
    bodypart: str
    n_frames: int
    n_both_ok: int
    n_only_a_ok: int
    n_only_b_ok: int
    n_neither_ok: int
    coverage_a: float
    coverage_b: float
    coverage_delta: float          # coverage_b - coverage_a (positive = B better)
    median_distance_px: float      # over both-ok frames
    mean_distance_px: float
    p95_distance_px: float
    agreement_frac: float          # fraction of both-ok frames within agreement radius


@dataclass(frozen=True)
class FrameDisagreement:
    frame: int
    bodypart: str
    distance_px: float


@dataclass(frozen=True)
class TrackingComparison:
    run_a_id: str
    run_b_id: str
    pcutoff: float
    agreement_radius_px: float
    n_frames: int
    bodyparts: List[str]
    unmatched_bodyparts: List[str]
    per_bodypart: Dict[str, PerBodypartComparison]
    overall: Dict[str, Any]
    top_disagreements: List[FrameDisagreement]
    disagreement_timeline: np.ndarray  # (n_frames,), NaN where no bp both-ok
    warnings: List[str] = field(default_factory=list)
    computed_at: str = ""


def _safe_stat(fn, arr: np.ndarray) -> float:
    """Apply a reducer to a 1-D array, returning NaN when empty."""
    if arr.size == 0:
        return float("nan")
    return float(fn(arr))


def compare_tracks(
    csv_a: Path,
    csv_b: Path,
    *,
    run_a_id: str,
    run_b_id: str,
    pcutoff: float = 0.6,
    max_interp_gap: int = 0,
    bodyparts: Optional[List[str]] = None,
    top_n: int = 50,
    agreement_radius_px: float = 10.0,
) -> Optional[TrackingComparison]:
    """Compare DLC trackings A and B for one video.

    Returns None if either CSV is unreadable. Bodyparts compared are the
    intersection present in both CSVs (optionally restricted to
    *bodyparts*); the symmetric difference is reported in
    ``unmatched_bodyparts``.
    """
    df_a = try_read_dlc_csv(Path(csv_a))
    df_b = try_read_dlc_csv(Path(csv_b))
    if df_a is None or df_b is None:
        return None

    warnings: List[str] = []

    bps_a = set(list_bodyparts(df_a))
    bps_b = set(list_bodyparts(df_b))
    common = bps_a & bps_b
    if bodyparts is not None:
        requested = set(bodyparts)
        common &= requested
    unmatched = sorted((bps_a | bps_b) - common)
    bp_list = sorted(common)
    if not bp_list:
        warnings.append("no common bodyparts between the two trackings")

    n_a, n_b = len(df_a), len(df_b)
    n_frames = min(n_a, n_b)
    if n_a != n_b:
        warnings.append(
            f"frame-count mismatch: A={n_a}, B={n_b}; truncated to {n_frames}"
        )

    per_bp: Dict[str, PerBodypartComparison] = {}
    dist_by_bp: Dict[str, np.ndarray] = {}  # NaN where not both-ok

    for bp in bp_list:
        xa, ya, oka = bp_track(df_a, bp, pcutoff, max_interp_gap)
        xb, yb, okb = bp_track(df_b, bp, pcutoff, max_interp_gap)
        xa, ya, oka = xa[:n_frames], ya[:n_frames], oka[:n_frames]
        xb, yb, okb = xb[:n_frames], yb[:n_frames], okb[:n_frames]

        both = oka & okb
        dist_full = np.full(n_frames, np.nan, dtype=float)
        if both.any():
            d = np.sqrt((xa[both] - xb[both]) ** 2 + (ya[both] - yb[both]) ** 2)
            dist_full[both] = d
        dist_by_bp[bp] = dist_full

        both_d = dist_full[both]
        n_both = int(both.sum())
        cov_a = float(oka.mean()) if n_frames else 0.0
        cov_b = float(okb.mean()) if n_frames else 0.0
        agree = (
            float((both_d <= agreement_radius_px).mean()) if both_d.size else float("nan")
        )
        per_bp[bp] = PerBodypartComparison(
            bodypart=bp,
            n_frames=n_frames,
            n_both_ok=n_both,
            n_only_a_ok=int((oka & ~okb).sum()),
            n_only_b_ok=int((~oka & okb).sum()),
            n_neither_ok=int((~oka & ~okb).sum()),
            coverage_a=cov_a,
            coverage_b=cov_b,
            coverage_delta=cov_b - cov_a,
            median_distance_px=_safe_stat(np.median, both_d),
            mean_distance_px=_safe_stat(np.mean, both_d),
            p95_distance_px=_safe_stat(lambda a: np.percentile(a, 95), both_d),
            agreement_frac=agree,
        )

    # Per-frame timeline: max disagreement across bodyparts (NaN if none).
    if bp_list and n_frames:
        stacked = np.vstack([dist_by_bp[bp] for bp in bp_list])  # (n_bp, n_frames)
        all_nan = np.all(np.isnan(stacked), axis=0)
        timeline = np.full(n_frames, np.nan, dtype=float)
        if (~all_nan).any():
            timeline[~all_nan] = np.nanmax(stacked[:, ~all_nan], axis=0)
    else:
        stacked = np.empty((0, n_frames), dtype=float)
        timeline = np.full(n_frames, np.nan, dtype=float)

    # Top disagreements: worst frames by timeline value, with the worst bp.
    top: List[FrameDisagreement] = []
    valid_frames = np.where(~np.isnan(timeline))[0]
    if valid_frames.size and bp_list:
        order = valid_frames[np.argsort(timeline[valid_frames])[::-1]]
        for f in order[: max(0, int(top_n))]:
            col = stacked[:, f]
            worst_idx = int(np.nanargmax(col))
            top.append(
                FrameDisagreement(
                    frame=int(f),
                    bodypart=bp_list[worst_idx],
                    distance_px=float(col[worst_idx]),
                )
            )

    # Overall rollup across bodyparts.
    med_per_bp = np.array(
        [per_bp[bp].median_distance_px for bp in bp_list], dtype=float
    )
    overall = {
        "n_bodyparts": len(bp_list),
        "median_distance_px": _safe_stat(np.nanmedian, med_per_bp[~np.isnan(med_per_bp)])
        if med_per_bp.size else float("nan"),
        "mean_coverage_delta": float(
            np.mean([per_bp[bp].coverage_delta for bp in bp_list])
        ) if bp_list else float("nan"),
        "coverage_delta_by_bodypart": {
            bp: per_bp[bp].coverage_delta for bp in bp_list
        },
        "max_disagreement_px": _safe_stat(np.nanmax, timeline[~np.isnan(timeline)])
        if np.any(~np.isnan(timeline)) else float("nan"),
    }

    return TrackingComparison(
        run_a_id=run_a_id,
        run_b_id=run_b_id,
        pcutoff=pcutoff,
        agreement_radius_px=agreement_radius_px,
        n_frames=n_frames,
        bodyparts=bp_list,
        unmatched_bodyparts=unmatched,
        per_bodypart=per_bp,
        overall=overall,
        top_disagreements=top,
        disagreement_timeline=timeline,
        warnings=warnings,
        computed_at=datetime.now(timezone.utc).isoformat(),
    )


def _nan_to_none(value: Any) -> Any:
    if isinstance(value, float) and np.isnan(value):
        return None
    if isinstance(value, dict):
        return {k: _nan_to_none(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_nan_to_none(v) for v in value]
    return value


def comparison_to_jsonable(
    comp: TrackingComparison,
    *,
    include_timeline: bool = False,
    top_n: Optional[int] = 20,
) -> Dict[str, Any]:
    """Serialize a comparison to a JSON-safe dict (NaN -> None).

    The per-frame ``disagreement_timeline`` is large; it is omitted unless
    *include_timeline* is True. ``top_disagreements`` is capped to *top_n*.
    """
    out: Dict[str, Any] = {
        "run_a_id": comp.run_a_id,
        "run_b_id": comp.run_b_id,
        "pcutoff": comp.pcutoff,
        "agreement_radius_px": comp.agreement_radius_px,
        "n_frames": comp.n_frames,
        "bodyparts": list(comp.bodyparts),
        "unmatched_bodyparts": list(comp.unmatched_bodyparts),
        "per_bodypart": {
            bp: _nan_to_none(asdict(pbc)) for bp, pbc in comp.per_bodypart.items()
        },
        "overall": _nan_to_none(comp.overall),
        "warnings": list(comp.warnings),
        "computed_at": comp.computed_at,
    }
    cap = len(comp.top_disagreements) if top_n is None else max(0, int(top_n))
    out["top_disagreements"] = [
        {"frame": fd.frame, "bodypart": fd.bodypart, "distance_px": fd.distance_px}
        for fd in comp.top_disagreements[:cap]
    ]
    if include_timeline:
        out["disagreement_timeline"] = [
            None if np.isnan(v) else float(v) for v in comp.disagreement_timeline
        ]
    return out
