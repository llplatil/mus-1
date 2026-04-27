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

from .nor_nof_object_qc import _ExperimentRow, _load_nor_nof_experiments

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BUCKET_DIAMETER_MM = 441.325  # 17 3/8 inches
DEFAULT_FLOOR_DIAMETER_PX = 705.0  # fallback when arena_boundary is missing
RADII_CM = [2.0, 3.0, 4.0]
LIKELIHOOD_THRESHOLD = 0.6


def _get_px_to_mm(meta: dict) -> float:
    """Per-session px-to-mm from arena_boundary ellipse axes."""
    ab = meta.get("arena_boundary", {})
    ell = ab.get("ellipse") if ab else None
    if ell and ell.get("axes"):
        mean_diam = (ell["axes"][0] + ell["axes"][1]) / 2.0
        if mean_diam > 0:
            return BUCKET_DIAMETER_MM / mean_diam
    return BUCKET_DIAMETER_MM / DEFAULT_FLOOR_DIAMETER_PX
MAX_INTERP_GAP = 10
BODYPART_BOUND_PX = 60.0

EXPERIMENT_DATA_ROOT = Path("/import/c1/WDMOSEQ2/llplatil/WDMOSEQ2/data/experiment_data")


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
def _load_nose_track_corrected(csv_path: str) -> Optional[Tuple[np.ndarray, np.ndarray, np.ndarray]]:
    """Load DLC CSV, apply likelihood filter + bodypart-bound correction.

    Returns (nose_x, nose_y, ok_mask) with ghost points removed.
    """
    p = Path(csv_path)
    if not p.exists():
        return None
    try:
        df = pd.read_csv(p, header=[0, 1, 2], index_col=0)
    except Exception:
        return None
    if not isinstance(df.columns, pd.MultiIndex) or df.columns.nlevels != 3:
        return None
    try:
        df.columns = df.columns.droplevel(0)
    except Exception:
        return None
    if ("nose", "x") not in df.columns:
        return None

    # Nose: likelihood filter + interpolation
    nx = pd.to_numeric(df[("nose", "x")], errors="coerce")
    ny = pd.to_numeric(df[("nose", "y")], errors="coerce")
    nl = pd.to_numeric(df[("nose", "likelihood")], errors="coerce")
    above_n = nl >= LIKELIHOOD_THRESHOLD
    nx_f = nx.where(above_n).interpolate(limit=MAX_INTERP_GAP, limit_direction="both")
    ny_f = ny.where(above_n).interpolate(limit=MAX_INTERP_GAP, limit_direction="both")
    nose_ok = (nx_f.notna() & ny_f.notna()).to_numpy(dtype=bool)
    nose_x = nx_f.to_numpy(dtype=float)
    nose_y = ny_f.to_numpy(dtype=float)

    # Head: likelihood filter + interpolation (for bounding)
    hx = pd.to_numeric(df[("head", "x")], errors="coerce")
    hy = pd.to_numeric(df[("head", "y")], errors="coerce")
    hl = pd.to_numeric(df[("head", "likelihood")], errors="coerce")
    above_h = hl >= LIKELIHOOD_THRESHOLD
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
            if d > BODYPART_BOUND_PX:
                nose_x[i] = np.nan
                nose_y[i] = np.nan
                nose_ok[i] = False

    # Re-interpolate after correction
    xs = pd.Series(nose_x).interpolate(limit=MAX_INTERP_GAP, limit_direction="both")
    ys = pd.Series(nose_y).interpolate(limit=MAX_INTERP_GAP, limit_direction="both")
    ok2 = (xs.notna() & ys.notna()).to_numpy(dtype=bool)
    return xs.to_numpy(dtype=float), ys.to_numpy(dtype=float), ok2


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
    px_to_mm: float = BUCKET_DIAMETER_MM / DEFAULT_FLOOR_DIAMETER_PX,
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
    st.header("NOR/NOF Interaction QC")
    st.caption("Visual overlay of object interaction zones and nose trajectory on arena frame.")

    # --- Load experiments ---
    experiment_data_root = project_path / "experiment_data"
    if not experiment_data_root.is_dir():
        # Tolerate projects whose only data root is e.g. validation_data;
        # the loader scans every configured root via mus1.toml anyway.
        experiment_data_root = EXPERIMENT_DATA_ROOT
    experiments = _load_nor_nof_experiments(experiment_data_root)
    if not experiments:
        st.error("No NOR/NOF experiments found.")
        return

    # --- Sidebar controls ---
    st.sidebar.header("Interaction QC Settings")

    radius_cm = st.sidebar.radio(
        "Zone radius",
        options=[2.0, 3.0, 4.0],
        index=2,
        format_func=lambda x: f"{x:.0f} cm",
        key="iqc_radius",
    )
    radius_key = f"r{int(radius_cm)}cm"

    show_trajectory = st.sidebar.checkbox("Show trajectory", value=True, key="iqc_show_traj")
    show_divider = st.sidebar.checkbox("Show hemisphere divider", value=False, key="iqc_show_div")
    show_dim_zone = st.sidebar.checkbox("Show dim zone", value=False, key="iqc_show_dim")
    use_clean_dim = st.sidebar.checkbox("Clean dim zone (morph filter)", value=True, key="iqc_clean_dim")
    show_arena_fit = st.sidebar.checkbox("Show arena fit", value=False, key="iqc_show_arena_fit")

    exp_type_filter = st.sidebar.selectbox(
        "Experiment type",
        options=["All", "NOR", "NOF"],
        index=0,
        key="iqc_exp_type",
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
        key="iqc_genotype",
    )

    qc_filter = st.sidebar.selectbox(
        "QC status",
        options=["All", "Unreviewed only", "Reviewed only", "Flagged tracking"],
        index=0,
        key="iqc_qc_filter",
    )

    # --- Filter experiments ---
    filtered = experiments
    if exp_type_filter != "All":
        filtered = [e for e in filtered if e.experiment_type == exp_type_filter]
    if genotype_filter != "All":
        filtered = [e for e in filtered if genotype_by_eid.get(e.experiment_id) == genotype_filter]

    # Only keep experiments with computed_metrics (implies arena markings + tracking exist)
    def _has_computed(row: _ExperimentRow) -> bool:
        d = _read_experiment_json(row)
        return d is not None and "computed_metrics" in d
    filtered = [e for e in filtered if _has_computed(e)]

    # Apply QC filter
    if qc_filter != "All":
        def _qc_match(row: _ExperimentRow) -> bool:
            d = _read_experiment_json(row)
            if d is None:
                return False
            iqc = d.get("interaction_qc", {})
            tqc = d.get("tracking_qc", {})
            if qc_filter == "Unreviewed only":
                return "reviewed_at" not in iqc
            elif qc_filter == "Reviewed only":
                return "reviewed_at" in iqc
            elif qc_filter == "Flagged tracking":
                return not tqc.get("nose_reliable", True)
            return True
        filtered = [e for e in filtered if _qc_match(e)]

    if not filtered:
        st.warning("No experiments match the selected filters (with computed metrics).")
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
    cm = data.get("computed_metrics", {})
    md = data.get("metadata", {})
    el = md.get("experiment_level", {})
    am = data.get("arena_markings", {})

    # Per-session calibration from arena boundary
    px_to_mm = _get_px_to_mm(data)
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
    video_path = (data.get("video", {}).get("path", "") or row.video_path).replace("/center1/", "/import/c1/")

    # --- Load frame ---
    frame = _read_mid_frame(video_path, row.frame_count)
    if frame is None:
        st.error(f"Could not load video frame: {video_path}")
        return

    # --- Load corrected nose track ---
    tp = data.get("extraction", {}).get("tracking_file_path", "")
    tracking_path = tp.replace("/center1/", "/import/c1/") if tp else None
    nose_data = _load_nose_track_corrected(tracking_path) if tracking_path else None
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
        # Session info
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

        # Interaction metrics from computed_metrics
        interaction = cm.get("interaction", {})
        radius_data = interaction.get(radius_key, {})
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
            st.info("No interaction data for this radius.")

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

    # --- QC Notes ---
    st.markdown("---")
    iqc = data.get("interaction_qc", {})
    existing_notes = iqc.get("notes", "")
    reviewed_at = iqc.get("reviewed_at", "")

    st.markdown("**QC Notes**")
    if reviewed_at:
        st.caption(f"Last reviewed: {reviewed_at}")

    notes_key = f"iqc_notes_{row.experiment_id}"
    new_notes = st.text_area(
        "Notes",
        value=existing_notes,
        placeholder="e.g., tracking looks off near right object, exclude from d2...",
        key=notes_key,
        label_visibility="collapsed",
        height=100,
    )

    if st.button("Save QC notes", key=f"iqc_save_{row.experiment_id}"):
        data["interaction_qc"] = {
            "notes": new_notes,
            "reviewed_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            row.json_path.write_text(json.dumps(data, indent=2) + "\n")
            st.success("Notes saved.")
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
