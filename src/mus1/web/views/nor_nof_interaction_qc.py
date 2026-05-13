"""NOR/NOF Interaction QC -- overlay object zones and nose trajectory on arena frame.

Visual validation of computed interaction metrics and total distance.
Shows: object centers, interaction zone circles at selectable radius,
nose trajectory with bodypart-bounded correction, and per-session metrics
read from the experiment JSON's computed_metrics block.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional, Tuple

import cv2
import numpy as np
import pandas as pd
import streamlit as st

from ...compute.tracking import resolve_dlc_csv_path
from ...paths import resolve_with_mount_aliases
from ..filters import (
    SCOPE_KEY,
    _cohort_member_ids,
    invalidate_after_write,
    mode_settings,
    pkey,
    render_scope_banner,
)

PANE = "nor_nof_iqc"

from .nor_nof_object_qc import _ExperimentRow, _load_nor_nof_experiments

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

RADII_CM = [2.0, 3.0, 4.0]
LIKELIHOOD_THRESHOLD = 0.6


def _get_px_to_mm(experiment_data: dict, task_id: str) -> tuple:
    """Per-session px-to-mm via the canonical scaling cascade.

    Returns ``(value_or_None, source_str)`` per
    :func:`mus1.compute.scaling.compute_px_to_mm`. Pane code surfaces
    *source* in a caption so reviewers see whether scaling came from
    a per-experiment override, the task's default arena profile, or
    is missing because no arena_boundary was marked.

    *task_id* is the experiment's task type (``NOR`` / ``NOF``); we
    look up the TaskDefinition lazily through the registry to avoid
    threading it from every call site.
    """
    from ...compute.scaling import compute_px_to_mm
    from ...tasks.registry import TaskRegistry

    task_def = TaskRegistry().get_or_none(task_id)
    if task_def is None:
        return None, "missing_task"
    return compute_px_to_mm(experiment_data, task_def)


MAX_INTERP_GAP = 10
BODYPART_BOUND_PX = 60.0



# ---------------------------------------------------------------------------
# Cached data loaders
# ---------------------------------------------------------------------------

@st.cache_resource(show_spinner=False)
def _read_mid_frame(video_path: str, frame_count: Optional[int]) -> Optional[np.ndarray]:
    """Return mid-video frame as RGB numpy array."""
    vp = Path(video_path)
    if not vp.exists():
        return None
    cap = cv2.VideoCapture(str(vp))
    if not cap.isOpened():
        return None
    total = frame_count or int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    mid = max(0, total // 2)
    cap.set(cv2.CAP_PROP_POS_FRAMES, mid)
    ret, bgr = cap.read()
    cap.release()
    if not ret:
        return None
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)


N_BRIGHTNESS_FRAMES = 20


def _make_ellipse_mask(
    shape: Tuple[int, int],
    center: Tuple[float, float],
    axes: Tuple[float, float],
    angle_deg: float,
) -> np.ndarray:
    """Create a boolean mask from arena boundary ellipse parameters."""
    h, w = shape
    mask = np.zeros((h, w), dtype=np.uint8)
    cx, cy = int(round(center[0])), int(round(center[1]))
    ax = max(1, int(round(axes[0] / 2.0)))
    ay = max(1, int(round(axes[1] / 2.0)))
    cv2.ellipse(mask, (cx, cy), (ax, ay), float(angle_deg), 0, 360, 1, -1)
    return mask.astype(bool)


@st.cache_resource(show_spinner=False)
def _compute_dim_mask(
    video_path: str,
    arena_ellipse: Optional[Dict] = None,
) -> Optional[Tuple[np.ndarray, float, np.ndarray]]:
    """Compute dim zone mask from median-of-N-frames brightness map.

    Uses per-session arena boundary ellipse if provided, otherwise falls back
    to a hardcoded frame-center circle (legacy behavior).

    Returns (dim_mask, arena_median_brightness, arena_mask).
    """
    vp = Path(video_path)
    if not vp.exists():
        return None
    cap = cv2.VideoCapture(str(vp))
    if not cap.isOpened():
        return None
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total < N_BRIGHTNESS_FRAMES:
        cap.release()
        return None
    indices = np.linspace(0, total - 1, N_BRIGHTNESS_FRAMES, dtype=int)
    frames = []
    for idx in indices:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(idx))
        ret, bgr = cap.read()
        if ret:
            frames.append(cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY))
    cap.release()
    if len(frames) < 3:
        return None
    bmap = np.median(np.stack(frames), axis=0).astype(np.uint8)
    h, w = bmap.shape

    # Use per-session arena boundary if available
    if arena_ellipse is not None:
        arena_mask = _make_ellipse_mask(
            (h, w),
            center=arena_ellipse["center"],
            axes=arena_ellipse["axes"],
            angle_deg=arena_ellipse.get("angle_deg", 0.0),
        )
    else:
        # Legacy fallback: hardcoded circle
        Y, X = np.ogrid[:h, :w]
        cx, cy = w // 2, h // 2
        r = min(cx, cy) - 10
        arena_mask = ((X - cx) ** 2 + (Y - cy) ** 2) <= r ** 2

    arena_median = float(np.median(bmap[arena_mask]))
    dim_mask = (bmap < arena_median) & arena_mask

    # Morphologically cleaned dim mask: remove pixel noise, keep largest blob
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    cleaned = cv2.morphologyEx(dim_mask.astype(np.uint8), cv2.MORPH_OPEN, kernel)
    # Keep only the largest connected component
    n_labels, labels, stats, _ = cv2.connectedComponentsWithStats(cleaned, connectivity=8)
    if n_labels > 1:
        # Label 0 is background; find largest foreground component
        largest = 1 + np.argmax(stats[1:, cv2.CC_STAT_AREA])
        cleaned = (labels == largest).astype(np.uint8)
    clean_dim_mask = cleaned.astype(bool) & arena_mask

    # Brightness gradient: fit linear plane to arena pixels
    ys, xs = np.where(arena_mask)
    vals = bmap[arena_mask].astype(np.float64)
    # Fit: brightness = a*x + b*y + c
    A = np.column_stack([xs, ys, np.ones(len(xs))])
    coeffs, _, _, _ = np.linalg.lstsq(A, vals, rcond=None)
    grad_x, grad_y = coeffs[0], coeffs[1]
    gradient_angle_deg = float(np.degrees(np.arctan2(grad_y, grad_x)))
    gradient_magnitude = float(np.sqrt(grad_x**2 + grad_y**2))
    # R-squared
    predicted = A @ coeffs
    ss_res = np.sum((vals - predicted) ** 2)
    ss_tot = np.sum((vals - np.mean(vals)) ** 2)
    gradient_r2 = float(1.0 - ss_res / ss_tot) if ss_tot > 0 else 0.0
    gradient_info = {
        "angle_deg": gradient_angle_deg,
        "magnitude": gradient_magnitude,
        "r_squared": gradient_r2,
        "dim_direction_deg": gradient_angle_deg + 180.0,  # direction toward dimmer side
    }

    return dim_mask, arena_median, arena_mask, clean_dim_mask, gradient_info


@st.cache_resource(show_spinner=False)
def _load_nose_track_corrected(
    csv_path: str,
    likelihood_threshold: float = LIKELIHOOD_THRESHOLD,
    bodypart_bound_px: float = BODYPART_BOUND_PX,
) -> Optional[Tuple[np.ndarray, np.ndarray, np.ndarray]]:
    """Load DLC CSV, apply likelihood filter + bodypart-bound correction.

    Returns (nose_x, nose_y, ok_mask) with ghost points removed. Cache
    key includes the params so changing variant axes in the pane
    correctly invalidates.
    """
    from ...compute.tracking import try_read_dlc_csv
    df = try_read_dlc_csv(Path(csv_path))
    if df is None:
        return None
    if ("nose", "x") not in df.columns:
        return None

    # Nose: likelihood filter + interpolation
    nx = pd.to_numeric(df[("nose", "x")], errors="coerce")
    ny = pd.to_numeric(df[("nose", "y")], errors="coerce")
    nl = pd.to_numeric(df[("nose", "likelihood")], errors="coerce")
    above_n = nl >= likelihood_threshold
    nx_f = nx.where(above_n).interpolate(limit=MAX_INTERP_GAP, limit_direction="both")
    ny_f = ny.where(above_n).interpolate(limit=MAX_INTERP_GAP, limit_direction="both")
    nose_ok = (nx_f.notna() & ny_f.notna()).to_numpy(dtype=bool)
    nose_x = nx_f.to_numpy(dtype=float)
    nose_y = ny_f.to_numpy(dtype=float)

    # Head: likelihood filter + interpolation (for bounding)
    hx = pd.to_numeric(df[("head", "x")], errors="coerce")
    hy = pd.to_numeric(df[("head", "y")], errors="coerce")
    hl = pd.to_numeric(df[("head", "likelihood")], errors="coerce")
    above_h = hl >= likelihood_threshold
    hx_f = hx.where(above_h).interpolate(limit=MAX_INTERP_GAP, limit_direction="both")
    hy_f = hy.where(above_h).interpolate(limit=MAX_INTERP_GAP, limit_direction="both")
    head_ok = (hx_f.notna() & hy_f.notna()).to_numpy(dtype=bool)
    head_x = hx_f.to_numpy(dtype=float)
    head_y = hy_f.to_numpy(dtype=float)

    # Bodypart-bound correction: flag nose frames too far from head
    n = len(nose_x)
    for i in range(n):
        if nose_ok[i] and head_ok[i]:
            d = ((nose_x[i] - head_x[i])**2 + (nose_y[i] - head_y[i])**2) ** 0.5
            if d > bodypart_bound_px:
                nose_x[i] = np.nan
                nose_y[i] = np.nan
                nose_ok[i] = False

    # Re-interpolate after correction
    xs = pd.Series(nose_x).interpolate(limit=MAX_INTERP_GAP, limit_direction="both")
    ys = pd.Series(nose_y).interpolate(limit=MAX_INTERP_GAP, limit_direction="both")
    ok2 = (xs.notna() & ys.notna()).to_numpy(dtype=bool)
    return xs.to_numpy(dtype=float), ys.to_numpy(dtype=float), ok2


# ---------------------------------------------------------------------------
# Variant slug + parameter helpers (per docs/web/SCHEMA_VARIANTS.md §2)
# ---------------------------------------------------------------------------

def _build_variant_slug(
    radius_cm: float, lh: float, buffer_mode: str, bb_px: float,
) -> str:
    """Deterministic, reversible variant name.

    Format: ``r{N}cm_lh{NN}_{fix|ots}_bb{NN}`` — e.g. ``r3cm_lh06_fix_bb60``.
    The slug is for display + dedup; the ``parameters`` field is
    authoritative.
    """
    lh_short = f"{int(round(lh * 10)):02d}"
    buf_short = "fix" if buffer_mode == "fixed" else "ots"
    return f"r{int(radius_cm)}cm_lh{lh_short}_{buf_short}_bb{int(bb_px)}"


def _build_exploratory_run(
    *,
    radius_cm: float, lh: float, buffer_mode: str, bb_px: float,
    metrics: Dict, fps: float,
) -> Dict:
    """Construct an ``exploratory_runs[]`` entry per SCHEMA_VARIANTS.md."""
    return {
        "name": _build_variant_slug(radius_cm, lh, buffer_mode, bb_px),
        "parameters": {
            "radius_cm": radius_cm,
            "likelihood_threshold": lh,
            "buffer_mode": buffer_mode,
            "bodypart_bound_px": bb_px,
            "fps": fps,
        },
        "metrics": metrics,
        "computed_at": datetime.now(timezone.utc)
                       .replace(microsecond=0).isoformat(),
        "computed_by": "mus1_browser",
    }


@st.cache_resource(show_spinner=False)
def _compute_baseline_confidence(csv_path: str, pcutoff: float = 0.6) -> Optional[Dict]:
    """Run mus1.compute.tracking_confidence on the resolved DLC CSV."""
    from ...compute.tracking_confidence import compute_tracking_confidence
    return compute_tracking_confidence(Path(csv_path), pcutoff=pcutoff)


def _resolve_task_for_row(row: "_ExperimentRow"):
    """Look up the TaskDefinition for an experiment row's task type.

    Lazy-imports the registry so the module remains usable without the
    task registry initialized at import time.
    """
    from ...tasks.registry import TaskRegistry
    return TaskRegistry().get_or_none(row.experiment_type)


def _compute_interaction_for_pane(
    csv_path: str,
    left_xy: Tuple[float, float], right_xy: Tuple[float, float],
    *,
    radius_cm: float, px_to_mm: float,
    likelihood_threshold: float, bodypart_bound_px: float,
    buffer_mode: str,
    novel_side: str, is_nor: bool,
) -> Dict:
    """Run the interaction compute pipeline for one experiment.

    Returns ``{"metrics": <dict>, "fps": <float>}`` to be stored in
    session state. Pure-ish: no JSON write, no logging — pane code
    decides when to persist via ``_persist_exploratory_run``.
    """
    from ...compute.nor_nof_interaction import (
        ObjectROI, compute_interaction_metrics,
    )
    nose_data = _load_nose_track_corrected(
        csv_path, likelihood_threshold, bodypart_bound_px)
    if nose_data is None:
        return {"metrics": {"error": "could not load DLC CSV"}, "fps": 30.0}
    nx, ny, nok = nose_data

    # Roles for novelty (NOR-only)
    role_left, role_right = "", ""
    if is_nor:
        ns = (novel_side or "").lower()
        if ns == "left":
            role_left, role_right = "novel", "familiar"
        elif ns == "right":
            role_left, role_right = "familiar", "novel"

    radius_px = radius_cm * 10.0 / px_to_mm
    objects = [
        ObjectROI(name="left", cx=left_xy[0], cy=left_xy[1],
                  radius_px=radius_px, role=role_left),
        ObjectROI(name="right", cx=right_xy[0], cy=right_xy[1],
                  radius_px=radius_px, role=role_right),
    ]
    arena_cx = (left_xy[0] + right_xy[0]) / 2.0
    fps = 30.0  # NOR/NOF videos. (TODO: read from video metadata once
                # the per-experiment fps probe is unified — Phase E.)
    metrics = compute_interaction_metrics(
        x=nx, y=ny, ok=nok,
        objects=objects, arena_center_x=arena_cx,
        fps=fps, buffer_mode=buffer_mode, buffer_px=20.0,
    )
    return {"metrics": metrics, "fps": fps}


def _persist_exploratory_run(json_path: Path, run: Dict) -> None:
    """Append *run* to ``computed_metrics.nor_nof_interaction.qc_review.exploratory_runs[]``.

    Per SCHEMA_VARIANTS.md: the canonical home for exploratory runs is
    inside the QC review block of the task-specific computed_metrics
    namespace. Append-only.
    """
    data = json.loads(json_path.read_text())
    cm = data.setdefault("computed_metrics", {})
    nn = cm.setdefault("nor_nof_interaction", {})
    qc = nn.setdefault("qc_review", {})
    runs = qc.setdefault("exploratory_runs", [])
    runs.append(run)
    json_path.write_text(json.dumps(data, indent=2) + "\n")


def _save_qc_review(
    json_path: Path,
    *,
    status: str,
    notes: str,
    migrated_from_legacy: bool,
) -> None:
    """Persist QC review to ``computed_metrics.nor_nof_interaction.qc_review``.

    On first save for an experiment that has a legacy top-level
    ``interaction_qc`` block, copies its contents into the new home and
    records the migration in ``qc_review.history``. Subsequent saves
    update the new home in-place and append history entries.
    """
    data = json.loads(json_path.read_text())
    cm = data.setdefault("computed_metrics", {})
    nn = cm.setdefault("nor_nof_interaction", {})
    qc = nn.setdefault("qc_review", {})

    if migrated_from_legacy:
        legacy = data.get("interaction_qc") or {}
        # Preserve the legacy block in history so prior reviews aren't lost.
        qc.setdefault("history", []).append({
            "action": "migrated_from_legacy",
            "at": datetime.now(timezone.utc).isoformat(),
            "by": "mus1_browser",
            "detail": json.dumps({
                "from": "interaction_qc",
                "to": "computed_metrics.nor_nof_interaction.qc_review",
                "legacy_value": legacy,
            }),
        })

    prior_status = qc.get("status", "")
    qc["status"] = status
    qc["notes"] = notes
    qc["reviewed_at"] = datetime.now(timezone.utc).isoformat()
    if prior_status != status:
        qc.setdefault("history", []).append({
            "action": "status_change",
            "at": qc["reviewed_at"],
            "by": "mus1_browser",
            "detail": f"{prior_status or '(not_set)'} -> {status or '(cleared)'}",
        })

    json_path.write_text(json.dumps(data, indent=2) + "\n")


def _load_saved_exploratory_runs(data: Dict) -> List[Dict]:
    """Return the list of saved exploratory runs for the current experiment.

    Reads the new schema home (per SCHEMA_VARIANTS.md). Legacy
    pre-2026-05-04 metric blocks under ``computed_metrics.interaction.r{N}cm``
    are not surfaced here — they are batch-canonical-candidates, not
    exploratory runs (different audience).
    """
    cm = data.get("computed_metrics") or {}
    nn = cm.get("nor_nof_interaction") or {}
    qc = nn.get("qc_review") or {}
    runs = qc.get("exploratory_runs") or []
    return runs if isinstance(runs, list) else []


def _render_metrics_table(
    metrics: Dict, fps: float, *, is_nor: bool, title: Optional[str] = None,
) -> None:
    """Render an interaction-metrics dict as a small table.

    Shared by the unsaved-compute display and the compare-against-saved
    display so layout stays consistent. Field names match
    ``compute_interaction_metrics`` (left/right object prefix) plus the
    novelty-index aliases when roles are set.
    """
    if title:
        st.caption(title)
    if metrics.get("error"):
        st.warning(f"Compute error: {metrics['error']}")
        return
    rows = [
        ("Left time (s)",  f"{metrics.get('left_time_s', 0):.1f}"),
        ("Right time (s)", f"{metrics.get('right_time_s', 0):.1f}"),
        ("Left bouts",     f"{metrics.get('left_bouts', 0)}"),
        ("Right bouts",    f"{metrics.get('right_bouts', 0)}"),
    ]
    if is_nor and metrics.get("novel_time_s") is not None:
        rows.append(("Novel time (s)",    f"{metrics.get('novel_time_s', 0):.1f}"))
        rows.append(("Familiar time (s)", f"{metrics.get('familiar_time_s', 0):.1f}"))
        ni = metrics.get("novelty_index")
        if ni is not None:
            rows.append(("d2 (novelty index)", f"{ni:.3f}"
                         if isinstance(ni, (int, float)) and ni == ni  # NaN check
                         else "N/A"))
    rows.append(("ok fraction", f"{metrics.get('ok_fraction', 0):.3f}"))
    st.dataframe(
        pd.DataFrame(rows, columns=["Metric", "Value"]),
        hide_index=True, width="stretch",
    )


# ---------------------------------------------------------------------------
# JSON helpers
# ---------------------------------------------------------------------------

def _read_experiment_json(row: _ExperimentRow) -> Optional[Dict]:
    """Read and return the full experiment JSON."""
    try:
        return json.loads(row.json_path.read_text())
    except Exception:
        return None


def _parse_xy(raw) -> Optional[Tuple[float, float]]:
    """Parse coordinate from string '(x, y)' or list [x, y]."""
    if raw is None:
        return None
    if isinstance(raw, str):
        raw = raw.strip("() ")
        parts = raw.split(",")
        return (float(parts[0]), float(parts[1]))
    return (float(raw[0]), float(raw[1]))


# ---------------------------------------------------------------------------
# Overlay drawing
# ---------------------------------------------------------------------------

def _draw_interaction_qc_overlay(
    frame: np.ndarray,
    left_xy: Tuple[float, float],
    right_xy: Tuple[float, float],
    radius_px: float,
    nose_x: Optional[np.ndarray],
    nose_y: Optional[np.ndarray],
    ok: Optional[np.ndarray],
    experiment_type: str,
    novel_side: str,
    *,
    show_trajectory: bool = True,
    show_divider: bool = False,
    dim_mask: Optional[np.ndarray] = None,
    clean_dim_mask: Optional[np.ndarray] = None,
    use_clean_dim: bool = True,
    arena_mask: Optional[np.ndarray] = None,
    arena_ellipse: Optional[Dict] = None,
    gradient_info: Optional[Dict] = None,
    px_to_mm: float = 0.626,  # placeholder default; callers always pass via the scaling cascade
    show_arena_fit: bool = False,
    fit_params: Optional[Dict] = None,
) -> np.ndarray:
    """Draw object zones and nose trajectory on frame."""
    img = frame.copy()
    h, w = img.shape[:2]

    # Dim zone overlay (draw first so other elements are on top)
    active_dim_mask = None
    if dim_mask is not None:
        active_dim_mask = clean_dim_mask if (use_clean_dim and clean_dim_mask is not None) else dim_mask
        # Semi-transparent blue tint on dim pixels
        tint = np.zeros_like(img)
        tint[active_dim_mask] = [60, 80, 180]  # blue-purple tint
        img = cv2.addWeighted(img, 0.75, tint, 0.25, 0)

    # Draw gradient direction arrow if gradient info available and dim zone shown
    if gradient_info is not None and dim_mask is not None and arena_ellipse is not None:
        ecx = int(round(arena_ellipse["center"][0]))
        ecy = int(round(arena_ellipse["center"][1]))
        dim_dir_rad = np.radians(gradient_info["dim_direction_deg"])
        arrow_len = 80
        ax_end = int(ecx + arrow_len * np.cos(dim_dir_rad))
        ay_end = int(ecy + arrow_len * np.sin(dim_dir_rad))
        cv2.arrowedLine(img, (ecx, ecy), (ax_end, ay_end), (255, 180, 0), 2, cv2.LINE_AA, tipLength=0.25)

    # Draw arena boundary ellipse outline
    if arena_ellipse is not None:
        ecx = int(round(arena_ellipse["center"][0]))
        ecy = int(round(arena_ellipse["center"][1]))
        eax = max(1, int(round(arena_ellipse["axes"][0] / 2.0)))
        eay = max(1, int(round(arena_ellipse["axes"][1] / 2.0)))
        eang = arena_ellipse.get("angle_deg", 0.0)
        cv2.ellipse(img, (ecx, ecy), (eax, eay), eang, 0, 360,
                     (0, 255, 255), 2, cv2.LINE_AA)  # cyan outline

    # Draw edge detection points from geometric fit
    if show_arena_fit and fit_params is not None:
        edge_pts = fit_params.get("edge_points_px", [])
        ray_accepted = fit_params.get("ray_accepted", [])
        ray_angles = fit_params.get("ray_angles_deg", [])
        # Draw accepted edge points as green dots
        for pt in edge_pts:
            px_x, px_y = int(round(pt[0])), int(round(pt[1]))
            if 0 <= px_x < w and 0 <= px_y < h:
                cv2.circle(img, (px_x, px_y), 3, (0, 255, 0), -1, cv2.LINE_AA)
        # Draw rejected rays as small red marks at the search radius
        if arena_ellipse is not None and ray_angles:
            cx_f = arena_ellipse["center"][0]
            cy_f = arena_ellipse["center"][1]
            r_f = arena_ellipse["axes"][0] / 2.0
            for i, accepted in enumerate(ray_accepted):
                if not accepted and i < len(ray_angles):
                    angle_rad = np.radians(ray_angles[i])
                    rx = int(round(cx_f + np.cos(angle_rad) * r_f))
                    ry = int(round(cy_f + np.sin(angle_rad) * r_f))
                    if 0 <= rx < w and 0 <= ry < h:
                        cv2.circle(img, (rx, ry), 3, (255, 60, 60), -1, cv2.LINE_AA)

    lx, ly = int(round(left_xy[0])), int(round(left_xy[1]))
    rx, ry = int(round(right_xy[0])), int(round(right_xy[1]))
    ri = max(1, int(round(radius_px)))

    # Determine colors based on novel side
    if experiment_type == "NOR" and novel_side == "left":
        left_color = (255, 80, 80)   # red for novel
        right_color = (0, 220, 0)    # green for familiar
        left_label = "L (novel)"
        right_label = "R (familiar)"
    elif experiment_type == "NOR" and novel_side == "right":
        left_color = (0, 220, 0)
        right_color = (255, 80, 80)
        left_label = "L (familiar)"
        right_label = "R (novel)"
    else:
        left_color = (0, 200, 255)   # cyan for NOF (identical objects)
        right_color = (0, 200, 255)
        left_label = "L"
        right_label = "R"

    # Interaction zone circles
    cv2.circle(img, (lx, ly), ri, left_color, 2, cv2.LINE_AA)
    cv2.circle(img, (rx, ry), ri, right_color, 2, cv2.LINE_AA)

    # Object center dots
    cv2.circle(img, (lx, ly), 6, (255, 255, 255), -1, cv2.LINE_AA)
    cv2.circle(img, (lx, ly), 6, left_color, 2, cv2.LINE_AA)
    cv2.circle(img, (rx, ry), 6, (255, 255, 255), -1, cv2.LINE_AA)
    cv2.circle(img, (rx, ry), 6, right_color, 2, cv2.LINE_AA)

    # Labels
    cv2.putText(img, left_label, (max(5, lx - 50), max(15, ly - ri - 10)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, left_color, 1, cv2.LINE_AA)
    cv2.putText(img, right_label, (max(5, rx - 50), max(15, ry - ri - 10)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, right_color, 1, cv2.LINE_AA)

    # Hemisphere divider
    if show_divider:
        vx = right_xy[0] - left_xy[0]
        vy = right_xy[1] - left_xy[1]
        mid_x = (left_xy[0] + right_xy[0]) / 2.0
        mid_y = (left_xy[1] + right_xy[1]) / 2.0
        dx, dy = -vy, vx
        norm = (dx**2 + dy**2) ** 0.5
        if norm > 0:
            dx /= norm
            dy /= norm
            span = max(h, w) * 2
            p1 = (int(round(mid_x - dx * span)), int(round(mid_y - dy * span)))
            p2 = (int(round(mid_x + dx * span)), int(round(mid_y + dy * span)))
            cv2.line(img, p1, p2, (255, 255, 255), 1, cv2.LINE_AA)

    # Nose trajectory
    if show_trajectory and nose_x is not None and ok is not None:
        segments = []
        seg_start = None
        for i in range(len(ok)):
            if ok[i] and np.isfinite(nose_x[i]) and np.isfinite(nose_y[i]):
                if seg_start is None:
                    seg_start = i
            else:
                if seg_start is not None and i - seg_start >= 2:
                    segments.append((seg_start, i))
                seg_start = None
        if seg_start is not None and len(ok) - seg_start >= 2:
            segments.append((seg_start, len(ok)))

        total_frames = len(ok)
        for s, e in segments:
            n_pts = e - s
            if n_pts < 2:
                continue
            chunk_size = max(1, n_pts // 20)
            for ci in range(0, n_pts - 1, chunk_size):
                cs = s + ci
                ce = min(s + ci + chunk_size + 1, e)
                if ce - cs < 2:
                    continue
                t = (cs + ce) / 2.0 / max(1, total_frames)
                r_c = int(255 * t)
                g_c = int(200 + 55 * t)
                b_c = int(255 * (1 - t))
                color = (r_c, g_c, b_c)
                pts = np.column_stack([
                    nose_x[cs:ce], nose_y[cs:ce]
                ]).astype(np.int32).reshape((-1, 1, 2))
                cv2.polylines(img, [pts], isClosed=False, color=color, thickness=1, lineType=cv2.LINE_AA)

    # Radius label in corner
    radius_mm = radius_px * px_to_mm
    cv2.putText(img, f"r={radius_mm:.0f}mm ({radius_mm/10:.1f}cm) [{radius_px:.0f}px]",
                (10, h - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)

    # Color legend for trajectory
    if show_trajectory and nose_x is not None:
        legend_x, legend_y = w - 180, h - 60
        cv2.rectangle(img, (legend_x, legend_y), (legend_x + 20, legend_y + 10), (0, 200, 255), -1)
        cv2.putText(img, "early", (legend_x + 25, legend_y + 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.35, (200, 200, 200), 1, cv2.LINE_AA)
        cv2.rectangle(img, (legend_x, legend_y + 16), (legend_x + 20, legend_y + 26), (128, 228, 128), -1)
        cv2.putText(img, "mid", (legend_x + 25, legend_y + 26),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.35, (200, 200, 200), 1, cv2.LINE_AA)
        cv2.rectangle(img, (legend_x, legend_y + 32), (legend_x + 20, legend_y + 42), (255, 255, 0), -1)
        cv2.putText(img, "late", (legend_x + 25, legend_y + 42),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.35, (200, 200, 200), 1, cv2.LINE_AA)

    # Dim zone / arena fit legend
    legend_y_cur = 15
    if dim_mask is not None:
        cv2.rectangle(img, (10, legend_y_cur), (30, legend_y_cur + 10), (60, 80, 180), -1)
        dim_label = "dim zone (cleaned, largest blob)" if (use_clean_dim and clean_dim_mask is not None) else "dim zone (raw, < median)"
        cv2.putText(img, dim_label, (35, legend_y_cur + 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 200, 255), 1, cv2.LINE_AA)
        legend_y_cur += 16
    if gradient_info is not None and dim_mask is not None:
        cv2.rectangle(img, (10, legend_y_cur), (30, legend_y_cur + 10), (255, 180, 0), -1)
        cv2.putText(img, f"gradient dir (R2={gradient_info['r_squared']:.2f})", (35, legend_y_cur + 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 200, 100), 1, cv2.LINE_AA)
        legend_y_cur += 16
    if arena_ellipse is not None:
        cv2.rectangle(img, (10, legend_y_cur), (30, legend_y_cur + 10), (0, 255, 255), -1)
        cv2.putText(img, "arena floor boundary", (35, legend_y_cur + 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 255), 1, cv2.LINE_AA)
        legend_y_cur += 16
    if show_arena_fit and fit_params is not None:
        cv2.circle(img, (20, legend_y_cur + 5), 3, (0, 255, 0), -1, cv2.LINE_AA)
        n_acc = fit_params.get("n_accepted_rays", 0)
        n_tot = fit_params.get("n_rays", 72)
        cv2.putText(img, f"edge points ({n_acc}/{n_tot} rays)", (35, legend_y_cur + 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 0), 1, cv2.LINE_AA)

    return img


# ---------------------------------------------------------------------------
# Main render
# ---------------------------------------------------------------------------

def render_nor_nof_interaction_qc(
    *,
    project_path: Path,
    workspace_root: Optional[str] = None,
) -> None:
    st.header("NOR/NOF Tracking QC")
    st.caption(
        "Approve DLC tracks against marked objects (per-experiment). "
        "Mirrors EZM Tracking QC for the NOR/NOF lifecycle: object zones, "
        "nose trajectory, and (when computed) interaction metrics."
    )
    render_scope_banner()

    if st.button("Refresh (clear cache)", key=pkey(PANE, "refresh")):
        invalidate_after_write()
        st.rerun()

    # --- Load experiments ---
    # The loader scans every configured root via discovery.task_dirs_across_roots;
    # an `experiment_data` subdir under project_path is the canonical anchor
    # but not strictly required (validation_data alone is fine).
    experiment_data_root = project_path / "experiment_data"
    experiments = _load_nor_nof_experiments(experiment_data_root)
    if not experiments:
        st.error("No NOR/NOF experiments found.")
        return

    # --- Sidebar controls ---
    # Universal cohort scope from web/filters.py:render_scope_picker.
    # Filters / Display split per the three-tier model documented in
    # docs/web/ROADMAP.md ("UI standardization").
    st.sidebar.subheader("Filters")

    exp_type_filter = st.sidebar.selectbox(
        "Experiment type",
        options=["All", "NOR", "NOF"],
        index=0,
        key=pkey(PANE, "exp_type"),
    )

    # Build genotype lookup from experiment JSONs (cached via _load_nor_nof_experiments)
    genotype_by_eid = {}
    for e in experiments:
        d = _read_experiment_json(e)
        if d:
            genotype_by_eid[e.experiment_id] = d.get("metadata", {}).get("genotype", "")

    all_genotypes = sorted(set(v for v in genotype_by_eid.values() if v))
    genotype_filter = st.sidebar.selectbox(
        "Genotype",
        options=["All"] + all_genotypes,
        index=0,
        key=pkey(PANE, "genotype"),
    )

    qc_filter = st.sidebar.selectbox(
        "QC status",
        options=["All", "Unreviewed only", "Reviewed only", "Flagged tracking"],
        index=0,
        key=pkey(PANE, "qc_filter"),
    )

    with mode_settings("Display", key_prefix=PANE):
        st.markdown("**Tracking variant**")
        st.caption(
            "Sets parameters for the in-pane Compute button below. "
            "Changing axes here updates the variant slug + the next "
            "Compute result; existing displayed metrics from prior runs "
            "(legacy or saved) do not retroactively change."
        )
        radius_cm = st.radio(
            "Zone radius",
            options=[2.0, 3.0, 4.0],
            index=2,
            format_func=lambda x: f"{x:.0f} cm",
            key=pkey(PANE, "radius"),
            horizontal=True,
        )
        var_lh = st.slider(
            "Likelihood threshold",
            min_value=0.4, max_value=0.95, value=LIKELIHOOD_THRESHOLD, step=0.05,
            key=pkey(PANE, "var_lh"),
        )
        var_buf_mode = st.radio(
            "Buffer mode",
            options=["fixed", "otsu"],
            index=0,
            key=pkey(PANE, "var_buf_mode"),
            horizontal=True,
            help="`fixed` adds a constant 20px buffer beyond the radius; "
                 "`otsu` derives the buffer from the per-session "
                 "nose-to-object distance distribution. Effect only "
                 "shows after clicking Compute.",
        )
        var_bb = st.slider(
            "Bodypart bound (px)",
            min_value=20.0, max_value=120.0, value=BODYPART_BOUND_PX, step=10.0,
            key=pkey(PANE, "var_bb"),
            help="Max nose-to-head distance before a nose frame is "
                 "treated as a tracking glitch and re-interpolated.",
        )
        st.divider()
        show_trajectory = st.checkbox("Show trajectory", value=True, key=pkey(PANE, "show_traj"))
        show_divider = st.checkbox("Show hemisphere divider", value=False, key=pkey(PANE, "show_div"))
        show_dim_zone = st.checkbox("Show dim zone", value=False, key=pkey(PANE, "show_dim"))
        use_clean_dim = st.checkbox("Clean dim zone (morph filter)", value=True, key=pkey(PANE, "clean_dim"))
        show_arena_fit = st.checkbox("Show arena fit", value=False, key=pkey(PANE, "show_arena_fit"))
    radius_key = f"r{int(radius_cm)}cm"
    variant_slug = _build_variant_slug(radius_cm, var_lh, var_buf_mode, var_bb)

    # --- Filter experiments ---
    filtered = experiments
    # Apply universal cohort scope
    scope_cohort = st.session_state.get(SCOPE_KEY)
    if scope_cohort:
        member_ids = _cohort_member_ids(project_path, scope_cohort)
        filtered = [e for e in filtered if e.experiment_id in member_ids]
    if exp_type_filter != "All":
        filtered = [e for e in filtered if e.experiment_type == exp_type_filter]
    if genotype_filter != "All":
        filtered = [e for e in filtered if genotype_by_eid.get(e.experiment_id) == genotype_filter]

    # QC pane contract (see docs/web/ROADMAP.md): filter by *input* prereqs
    # only — object markings + a readable JSON. The metrics this pane
    # reviews (`computed_metrics.interaction.*`) may be absent on freshly
    # tracked cohorts; the per-experiment view degrades gracefully.
    def _has_inputs(row: _ExperimentRow) -> bool:
        d = _read_experiment_json(row)
        if d is None:
            return False
        am = d.get("arena_markings") or {}
        return bool(am.get("object_left_xy") and am.get("object_right_xy"))
    filtered = [e for e in filtered if _has_inputs(e)]

    # Apply QC filter (reads new schema home first, falls back to legacy
    # top-level ``interaction_qc``; covers experiments that haven't been
    # re-saved into the new home yet).
    if qc_filter != "All":
        def _qc_match(row: _ExperimentRow) -> bool:
            d = _read_experiment_json(row)
            if d is None:
                return False
            qc_review = (
                ((d.get("computed_metrics") or {})
                 .get("nor_nof_interaction") or {})
                .get("qc_review") or {}
            )
            legacy_iqc = d.get("interaction_qc") or {}
            tqc = d.get("tracking_qc") or {}
            reviewed = bool(qc_review.get("reviewed_at")
                            or legacy_iqc.get("reviewed_at"))
            if qc_filter == "Unreviewed only":
                return not reviewed
            elif qc_filter == "Reviewed only":
                return reviewed
            elif qc_filter == "Flagged tracking":
                return not tqc.get("nose_reliable", True)
            return True
        filtered = [e for e in filtered if _qc_match(e)]

    if not filtered:
        st.warning(
            "No experiments match the selected filters. "
            "(Pane requires `arena_markings.object_left_xy` + "
            "`object_right_xy`; metric blocks are not required — the per-"
            "experiment view degrades gracefully when metrics are absent.)"
        )
        return

    filtered.sort(key=lambda e: e.experiment_id)

    # --- Navigation ---
    n = len(filtered)
    if "iqc_nav_idx" not in st.session_state:
        st.session_state["iqc_nav_idx"] = 0
    idx = st.session_state["iqc_nav_idx"]
    idx = max(0, min(n - 1, idx))

    col_prev, col_idx, col_next, col_count = st.columns([1, 2, 1, 2])
    with col_prev:
        if st.button("Prev", key="iqc_prev", disabled=idx <= 0):
            idx = max(0, idx - 1)
            st.session_state["iqc_nav_idx"] = idx
            st.rerun()
    with col_next:
        if st.button("Next", key="iqc_next", disabled=idx >= n - 1):
            idx = min(n - 1, idx + 1)
            st.session_state["iqc_nav_idx"] = idx
            st.rerun()
    with col_idx:
        new_idx = st.number_input(
            "Index", min_value=0, max_value=n - 1, value=idx,
            step=1, key="iqc_idx_input",
        )
        if new_idx != idx:
            idx = new_idx
            st.session_state["iqc_nav_idx"] = idx
    with col_count:
        st.markdown(f"**{idx + 1} / {n}** sessions")

    row = filtered[idx]
    data = _read_experiment_json(row)
    if data is None:
        st.error(f"Could not read JSON: {row.json_path}")
        return
    # `computed_metrics` may be absent (fresh cohorts) or None (some legacy
    # JSONs). Coerce to dict so downstream `.get()` calls don't crash.
    cm = data.get("computed_metrics") or {}
    md = data.get("metadata", {})
    el = md.get("experiment_level", {})
    am = data.get("arena_markings", {})

    # Per-session calibration via the scaling cascade (per-experiment
    # override → task default → missing). Source label is surfaced in
    # the right column so reviewers see which fallback fired.
    px_to_mm, scaling_source = _get_px_to_mm(data, row.experiment_type)
    if px_to_mm is None or px_to_mm <= 0:
        # No usable calibration. Set a placeholder so layout doesn't
        # crash and let the right-column banner explain the situation.
        px_to_mm = 0.626  # Tamco default; flagged via scaling_source
    mm_to_px = 1.0 / px_to_mm
    radius_px = radius_cm * 10.0 * mm_to_px

    st.subheader(f"{row.experiment_id}")

    # --- Parse coordinates ---
    left_xy = _parse_xy(am.get("object_left_xy"))
    right_xy = _parse_xy(am.get("object_right_xy"))
    if left_xy is None or right_xy is None:
        st.error("Missing arena markings for this session.")
        return

    novel_side = el.get("novel_side", "") if row.experiment_type == "NOR" else ""
    raw_vp = data.get("video", {}).get("path", "") or row.video_path
    resolved_vp = resolve_with_mount_aliases(raw_vp)
    video_path = str(resolved_vp) if resolved_vp else str(raw_vp)

    # --- Load frame ---
    frame = _read_mid_frame(video_path, row.frame_count)
    if frame is None:
        st.error(f"Could not load video frame: {video_path}")
        return

    # --- Load corrected nose track (with variant params) ---
    tp = resolve_dlc_csv_path(data.get("extraction"))
    resolved_tp = resolve_with_mount_aliases(tp) if tp else None
    tracking_path = str(resolved_tp) if resolved_tp else None
    nose_data = (
        _load_nose_track_corrected(tracking_path, var_lh, var_bb)
        if tracking_path else None
    )
    nose_x = nose_data[0] if nose_data else None
    nose_y = nose_data[1] if nose_data else None
    ok = nose_data[2] if nose_data else None

    # --- Load dim zone mask (if toggled on) ---
    dim_mask = None
    clean_dim_mask = None
    gradient_info = None
    arena_mask = None
    ab = data.get("arena_boundary", {})
    ab_ellipse = ab.get("ellipse")  # may be None for sessions without boundary
    ab_fit_params = ab.get("fit_params")  # geometric fit diagnostics (v2)
    if show_dim_zone:
        dim_result = _compute_dim_mask(video_path, arena_ellipse=ab_ellipse)
        if dim_result is not None:
            dim_mask = dim_result[0]
            arena_mask = dim_result[2]
            clean_dim_mask = dim_result[3]
            gradient_info = dim_result[4]

    # Show arena boundary if either dim zone or arena fit is toggled
    show_boundary = show_dim_zone or show_arena_fit

    # --- Draw overlay ---
    overlay = _draw_interaction_qc_overlay(
        frame, left_xy, right_xy, radius_px,
        nose_x, nose_y, ok,
        row.experiment_type, novel_side,
        show_trajectory=show_trajectory,
        show_divider=show_divider,
        dim_mask=dim_mask,
        clean_dim_mask=clean_dim_mask,
        use_clean_dim=use_clean_dim,
        arena_mask=arena_mask,
        arena_ellipse=ab_ellipse if show_boundary else None,
        gradient_info=gradient_info if show_dim_zone else None,
        px_to_mm=px_to_mm,
        show_arena_fit=show_arena_fit,
        fit_params=ab_fit_params if show_arena_fit else None,
    )

    # --- Layout: image + metrics ---
    col_img, col_metrics = st.columns([3, 2])

    with col_img:
        st.image(overlay, width="stretch")

    with col_metrics:
        # ── Arena scaling banner ─────────────────────────────────────
        # Shows the resolved px-to-mm + which fallback fired
        # (per-experiment override / task default / missing). Critical
        # context for any millimetre measurements that follow.
        from ...compute.scaling import (
            SOURCE_MISSING_BOUNDARY,
            SOURCE_MISSING,
            SOURCE_PER_EXPERIMENT_OVERRIDE,
            SOURCE_TASK_DEFAULT,
            resolve_arena_state,
        )
        state_id, profile = resolve_arena_state(data, _resolve_task_for_row(row))
        profile_label = (
            f"{profile.id}{f' [{state_id}]' if state_id else ''}"
            if profile else "(no profile)"
        )
        if scaling_source in (SOURCE_TASK_DEFAULT, SOURCE_PER_EXPERIMENT_OVERRIDE):
            st.caption(
                f"Scaling: {px_to_mm:.4f} mm/px • {scaling_source} • {profile_label}"
            )
        elif scaling_source == SOURCE_MISSING_BOUNDARY:
            st.warning(
                f"⚠ No `arena_markings.arena_boundary` for this experiment "
                f"({profile_label}). Falling back to a placeholder px/mm; "
                "millimetre numbers below are unreliable until the arena "
                "is marked."
            )
        else:
            st.warning(
                f"⚠ Could not resolve arena scaling (source: `{scaling_source}`). "
                "Mark the arena boundary or set "
                "`arena_markings.arena_profile.profile_id`."
            )

        # ── Baseline DLC tracking confidence (always-shown gate) ────
        # The "don't try to polish garbage" check — surfaces DLC quality
        # before any task-specific compute. See compute.tracking_confidence.
        st.markdown("**Tracking confidence (DLC baseline)**")
        if tracking_path:
            tc_summary = _compute_baseline_confidence(tracking_path, var_lh)
        else:
            tc_summary = None
        if tc_summary is None:
            st.caption("No DLC CSV linked — baseline confidence unavailable.")
        elif tc_summary.get("error"):
            st.warning(f"Confidence: {tc_summary['error']}")
        else:
            o = tc_summary.get("overall") or {}
            n_frames = o.get("n_frames", 0)
            mfa = o.get("median_frac_above_pcutoff") or 0.0
            mba = o.get("min_bodypart_frac_above_pcutoff") or 0.0
            st.caption(
                f"frames={n_frames} | median ≥{var_lh:.2f}: {mfa*100:.1f}% | "
                f"min bp: {mba*100:.1f}% | longest dropout: "
                f"{o.get('longest_any_dropout_run_frames', 0)} fr"
            )
            flags = tc_summary.get("flags") or []
            if flags:
                st.warning("Tracking quality flags: " + ", ".join(flags))
            else:
                st.success("No tracking-quality flags.")
            with st.expander("Per-bodypart detail", expanded=False):
                rows_bp = []
                for bp, st_bp in (tc_summary.get("per_bodypart") or {}).items():
                    rows_bp.append({
                        "bodypart": bp,
                        "mean_lh": f"{st_bp.get('mean_likelihood', 0) or 0:.3f}",
                        "frac ≥pcutoff": f"{(st_bp.get('frac_above_pcutoff') or 0)*100:.1f}%",
                        "longest dropout": st_bp.get('longest_dropout_run_frames', 0),
                    })
                if rows_bp:
                    st.dataframe(pd.DataFrame(rows_bp), hide_index=True,
                                 width="stretch")

        st.divider()

        # ── Session info ─────────────────────────────────────────────
        st.markdown("**Session info**")
        info_items = {
            "Type": row.experiment_type,
            "Subject": row.subject_id,
            "Date": row.date_recorded,
            "Genotype": md.get("genotype", ""),
            "Sex": md.get("sex", ""),
            "Timepoint": el.get("timepoint", ""),
            "Bucket": el.get("bucket", ""),
        }
        if row.experiment_type == "NOR":
            info_items["Novel side"] = novel_side
            info_items["Object L"] = el.get("object_left", "")
            info_items["Object R"] = el.get("object_right", "")
        else:
            info_items["Objects"] = el.get("object_left", "") or row.toys_raw

        info_df = pd.DataFrame([(k, str(v)) for k, v in info_items.items()], columns=["Field", "Value"])
        st.dataframe(info_df, hide_index=True, width="stretch")

        # ── Compute exploratory metrics (variant-driven, append-only on Save) ──
        # Per SCHEMA_VARIANTS.md, exploratory runs append to
        # qc_review.exploratory_runs[] only when the user clicks Save —
        # not on every Compute click. This block manages session state
        # for the unsaved compute result and the comparison dropdown.
        st.markdown("**Compute exploratory metrics**")
        st.caption(f"Variant: `{variant_slug}`")
        unsaved_key = f"iqc_unsaved_{row.experiment_id}"
        compute_disabled = (
            tracking_path is None or left_xy is None or right_xy is None
        )
        cb1, cb2 = st.columns([1, 1])
        with cb1:
            if st.button(
                "Compute (unsaved)",
                key=f"iqc_compute_{row.experiment_id}",
                type="secondary", disabled=compute_disabled,
                help="Run interaction-metric compute with the current "
                     "variant. Result is held in session state — click "
                     "Save below to append it to exploratory_runs[].",
            ):
                _result = _compute_interaction_for_pane(
                    tracking_path, left_xy, right_xy,
                    radius_cm=radius_cm,
                    px_to_mm=px_to_mm,
                    likelihood_threshold=var_lh,
                    bodypart_bound_px=var_bb,
                    buffer_mode=var_buf_mode,
                    novel_side=novel_side,
                    is_nor=(row.experiment_type == "NOR"),
                )
                # Stamp the result with the variant slug it was computed
                # with — distinct from the *current* slug if the user
                # changes the axes after Compute.
                _result["variant_slug"] = variant_slug
                st.session_state[unsaved_key] = _result
                st.rerun()
        with cb2:
            if st.button(
                "Save exploratory run",
                key=f"iqc_save_explore_{row.experiment_id}",
                type="primary",
                disabled=unsaved_key not in st.session_state,
                help="Append the current unsaved compute result to "
                     "computed_metrics.nor_nof_interaction.qc_review.exploratory_runs[].",
            ):
                _persist_exploratory_run(
                    row.json_path,
                    _build_exploratory_run(
                        radius_cm=radius_cm, lh=var_lh,
                        buffer_mode=var_buf_mode, bb_px=var_bb,
                        metrics=st.session_state[unsaved_key]["metrics"],
                        fps=st.session_state[unsaved_key]["fps"],
                    ),
                )
                st.session_state.pop(unsaved_key, None)
                invalidate_after_write()
                st.toast("Saved exploratory run.")
                st.rerun()

        if compute_disabled:
            missing = []
            if not tracking_path:
                missing.append("DLC CSV")
            if not left_xy or not right_xy:
                missing.append("object markings")
            st.caption(
                f"Compute disabled — missing: {', '.join(missing)}. "
                "Visual QC and tracking-confidence above still work."
            )

        if unsaved_key in st.session_state:
            unsaved = st.session_state[unsaved_key]
            stale = unsaved.get("variant_slug") != variant_slug
            st.markdown("**Computed (unsaved)**")
            if stale:
                st.caption(
                    f"⚠ Computed for `{unsaved.get('variant_slug', '?')}` "
                    f"— current variant is now `{variant_slug}`. "
                    "Click Compute again to refresh."
                )
            else:
                st.caption(f"Variant: `{unsaved['variant_slug']}`")
            _render_metrics_table(unsaved["metrics"], unsaved["fps"],
                                  is_nor=(row.experiment_type == "NOR"))

        # ── Compare against a saved exploratory run ─────────────────
        # Reads from BOTH the new schema home (qc_review.exploratory_runs)
        # and the legacy in-JSON variant blocks so users can diff against
        # batch-computed `computed_metrics.interaction.r{N}cm` too.
        saved_runs = _load_saved_exploratory_runs(data)
        if saved_runs:
            st.markdown("**Compare against saved**")
            options = ["(none)"] + [
                f"{r['name']}  ({r.get('computed_at', '')[:10]})"
                for r in saved_runs
            ]
            sel = st.selectbox(
                "Saved run", options=options,
                key=f"iqc_compare_{row.experiment_id}",
                label_visibility="collapsed",
            )
            if sel != "(none)":
                idx_sel = options.index(sel) - 1
                _render_metrics_table(
                    saved_runs[idx_sel].get("metrics", {}),
                    saved_runs[idx_sel].get("parameters", {}).get("fps", 30.0),
                    is_nor=(row.experiment_type == "NOR"),
                    title=f"Saved: {saved_runs[idx_sel]['name']}",
                )

        st.divider()

        # Interaction metrics from computed_metrics (may be absent on
        # freshly tracked cohorts — see QC pane contract in ROADMAP.md).
        interaction = cm.get("interaction") or {}
        if not interaction:
            st.info(
                "Interaction metrics not yet computed for this experiment. "
                "Visual QC of object zones and trajectory above is "
                "independent of metrics and works without them. Run "
                "`mus1 compute nor-nof-interaction` (or wait for the "
                "scheduled batch) to populate `computed_metrics.interaction`."
            )
        else:
            radius_data = interaction.get(radius_key) or {}
            if radius_data:
                st.markdown(f"**Interaction metrics ({radius_cm:.0f} cm)**")
                metrics = {
                    "Left time (s)": f"{radius_data.get('left_time_s', 0):.1f}",
                    "Right time (s)": f"{radius_data.get('right_time_s', 0):.1f}",
                    "Left bouts": f"{radius_data.get('left_bouts', 0)}",
                    "Right bouts": f"{radius_data.get('right_bouts', 0)}",
                    "Total interaction (s)": f"{radius_data.get('total_interaction_s', 0):.1f}",
                }
                if row.experiment_type == "NOR" and "d2" in radius_data:
                    d2_val = radius_data["d2"]
                    metrics["d2"] = f"{d2_val:.3f}" if d2_val is not None else "N/A"
                    metrics["Novel time (s)"] = f"{radius_data.get('novel_time_s', 0):.1f}"
                    metrics["Familiar time (s)"] = f"{radius_data.get('familiar_time_s', 0):.1f}"
                left_lat = radius_data.get("left_latency_s")
                right_lat = radius_data.get("right_latency_s")
                metrics["Left latency (s)"] = f"{left_lat:.1f}" if left_lat is not None else "N/A"
                metrics["Right latency (s)"] = f"{right_lat:.1f}" if right_lat is not None else "N/A"

                metrics_df = pd.DataFrame(list(metrics.items()), columns=["Metric", "Value"])
                st.dataframe(metrics_df, hide_index=True, width="stretch")
            else:
                st.info(f"No interaction data for radius {radius_cm:.0f} cm (other radii may be present).")

        # Dim zone metrics (shown when dim zone overlay is active)
        if show_dim_zone:
            dz = cm.get("dim_zone", {})
            if dz:
                st.markdown("**Dim zone metrics**")
                dz_metrics = {
                    "Frac time in dim": f"{dz.get('frac_time_dim', 0):.3f}",
                    "Dim pref index": f"{dz.get('dim_pref_index', 0):+.3f}",
                    "Dim area frac": f"{dz.get('dim_zone_area_frac', 0):.3f}",
                    "Arena mask": dz.get("arena_mask_source", ab.get("source", "unknown")),
                    "Boundary quality": ab.get("quality_flag", "unknown"),
                }
                if gradient_info:
                    dz_metrics["Gradient dir (dim)"] = f"{gradient_info['dim_direction_deg']:.0f}°"
                    dz_metrics["Gradient R²"] = f"{gradient_info['r_squared']:.3f}"
                    dz_metrics["Gradient mag"] = f"{gradient_info['magnitude']:.3f}"
                dz_df = pd.DataFrame(list(dz_metrics.items()), columns=["Metric", "Value"])
                st.dataframe(dz_df, hide_index=True, width="stretch")

        # Arena fit diagnostics (shown when arena fit toggle is on)
        if show_arena_fit:
            st.markdown("**Arena boundary fit**")
            fit_items = {
                "Source": ab.get("source", "unknown"),
                "Version": ab.get("version", "unknown"),
                "Quality": ab.get("quality_flag", "unknown"),
            }
            if ab_fit_params:
                fit_items["Radius (px)"] = f"{ab_fit_params.get('radius_px', 0):.1f}"
                fit_items["Rays accepted"] = f"{ab_fit_params.get('n_accepted_rays', 0)}/{ab_fit_params.get('n_rays', 72)}"
                fit_items["Fit residual (px)"] = f"{ab_fit_params.get('fit_residual_px', 0):.2f}"
                fit_items["Used fallback"] = str(ab_fit_params.get("used_fallback", False))
            elif ab_ellipse:
                fit_items["Radius (px)"] = f"{(ab_ellipse['axes'][0] + ab_ellipse['axes'][1]) / 4.0:.1f}"
            fit_df = pd.DataFrame(list(fit_items.items()), columns=["Metric", "Value"])
            st.dataframe(fit_df, hide_index=True, width="stretch")

        # Arena boundary quality warnings
        if show_dim_zone or show_arena_fit:
            qf = ab.get("quality_flag", "")
            if qf == "review_elongated":
                st.warning("Arena boundary flagged: elongated ellipse (axis ratio > 1.3). Visual check recommended.")
            elif qf == "review_no_boundary":
                st.warning("No arena boundary available for this session. Dim zone uses legacy fallback.")
            elif qf == "review_low_edge_count":
                n_acc = ab_fit_params.get("n_accepted_rays", 0) if ab_fit_params else "?"
                st.warning(f"Arena boundary: only {n_acc}/72 edge points detected. Boundary based on geometric prior + partial edge fit.")
            elif qf == "review_fallback_prior":
                st.warning("Arena boundary: edge fit failed constraints, using geometric prior (object midpoint + learned offset). Visual check recommended.")

        # Distance metrics from computed_metrics
        dist = cm.get("distance", {})
        nose_qc = cm.get("nose_qc", {})
        if dist:
            st.markdown("**Distance metrics**")
            dist_metrics = {
                "Distance (mm)": f"{dist.get('total_distance_mm', 0):.0f}",
                "Velocity (mm/s)": f"{dist.get('mean_velocity_mm_s', 0):.1f}",
                "Duration (s)": f"{dist.get('duration_s', 0):.0f}",
                "Nose likelihood": f"{nose_qc.get('mean_likelihood', 0):.3f}",
                "Low-lh frames": f"{nose_qc.get('frac_below_threshold', 0):.1%}",
                "Nose corrections": f"{nose_qc.get('n_nose_corrections', 0)} ({nose_qc.get('frac_nose_corrections', 0):.2%})",
            }
            dist_df = pd.DataFrame(list(dist_metrics.items()), columns=["Metric", "Value"])
            st.dataframe(dist_df, hide_index=True, width="stretch")

    # --- Tracking QC Review ---
    # Canonical home is computed_metrics.nor_nof_interaction.qc_review
    # (per docs/web/SCHEMA_VARIANTS.md). On first save, any existing
    # legacy ``interaction_qc`` block is migrated into the new home and
    # noted in qc_review.history. Reads consult the new home first, then
    # fall back to the legacy block, so saved-state stays visible during
    # the rollout window.
    st.markdown("---")
    qc_review_block = (
        ((data.get("computed_metrics") or {})
         .get("nor_nof_interaction") or {})
        .get("qc_review") or {}
    )
    legacy_iqc = data.get("interaction_qc") or {}
    # Prefer the new home, fall back to legacy.
    existing_status = qc_review_block.get("status") or legacy_iqc.get("status", "")
    existing_notes = qc_review_block.get("notes") or legacy_iqc.get("notes", "")
    reviewed_at = qc_review_block.get("reviewed_at") or legacy_iqc.get("reviewed_at", "")

    st.markdown("**Tracking QC Review**")
    if reviewed_at:
        st.caption(f"Last reviewed: {reviewed_at[:19]}")
    if legacy_iqc and not qc_review_block:
        st.caption(
            "ⓘ Legacy `interaction_qc` block detected; will migrate to "
            "`computed_metrics.nor_nof_interaction.qc_review` on next Save."
        )

    _STATUS_OPTIONS = [
        "(not reviewed)", "good", "poor_tracking", "exclude", "needs_re_review",
    ]
    status_key = f"iqc_status_{row.experiment_id}"
    if status_key not in st.session_state:
        st.session_state[status_key] = (
            existing_status if existing_status in _STATUS_OPTIONS
            else "(not reviewed)"
        )
    qc_status = st.radio(
        "Status",
        options=_STATUS_OPTIONS,
        horizontal=True,
        key=status_key,
    )

    notes_key = f"iqc_notes_{row.experiment_id}"
    if notes_key not in st.session_state:
        st.session_state[notes_key] = existing_notes
    new_notes = st.text_area(
        "Notes",
        placeholder="e.g., tracking looks off near right object, exclude from d2...",
        key=notes_key,
        label_visibility="collapsed",
        height=100,
    )

    if st.button(
        "Save QC review",
        key=f"iqc_save_{row.experiment_id}",
        type="primary",
    ):
        status_val = qc_status if qc_status != "(not reviewed)" else ""
        try:
            _save_qc_review(
                row.json_path,
                status=status_val,
                notes=new_notes.strip(),
                migrated_from_legacy=bool(legacy_iqc and not qc_review_block),
            )
            invalidate_after_write()
            st.toast("Saved tracking QC review.")
        except Exception as exc:
            st.error(f"Failed to save: {exc}")

    # --- Tracking QC warning ---
    tqc = data.get("tracking_qc", {})
    if tqc and not tqc.get("nose_reliable", True):
        st.warning(
            f"**Tracking QC flag:** {tqc.get('issue', 'unknown')} -- "
            f"{tqc.get('description', '')}"
        )

    # Footer info
    st.caption(
        f"Left object: ({left_xy[0]:.1f}, {left_xy[1]:.1f}) | "
        f"Right object: ({right_xy[0]:.1f}, {right_xy[1]:.1f}) | "
        f"Radius: {radius_px:.1f} px = {radius_px * px_to_mm:.1f} mm"
    )
    if nose_data:
        n_valid = int(np.sum(ok))
        n_total = len(ok)
        st.caption(f"Nose track: {n_valid}/{n_total} valid frames ({n_valid/n_total:.1%}) | Pipeline: {cm.get('pipeline', 'unknown')} v{cm.get('version', '?')}")
