from __future__ import annotations

"""
EZM Border QC view -- review UNet inference results ranked by quality
and draw 4 border lines to correct the open/closed arm boundaries.

Produces zone JSONs (``ezm_open_closed_v2``) and pixel masks (uint8 {0,1,2})
suitable for retraining.
"""

import csv
import json
import math
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np  # type: ignore
import streamlit as st

from ..ezm_masks import blend_mask_overlay
from ..io import read_csv_rows

TAU = 2.0 * math.pi


# ---------------------------------------------------------------------------
# Cached helpers
# ---------------------------------------------------------------------------

@st.cache_data(show_spinner=False, ttl=60)
def _load_frame_rgb(video_abs: str, frame_idx: int) -> Optional[Any]:
    import cv2  # type: ignore

    cap = cv2.VideoCapture(str(video_abs))
    if not cap.isOpened():
        return None
    cap.set(cv2.CAP_PROP_POS_FRAMES, int(frame_idx))
    ok, frame_bgr = cap.read()
    cap.release()
    if not ok or frame_bgr is None:
        return None
    return cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB).astype(np.uint8, copy=False)


@st.cache_data(show_spinner=False, ttl=120)
def _list_infer_runs(calc_dir: str) -> List[str]:
    """Return sorted list of ``ezm_infer_rank_*`` directory names."""
    p = Path(calc_dir)
    if not p.is_dir():
        return []
    return sorted(
        [d.name for d in p.iterdir() if d.is_dir() and d.name.startswith("ezm_infer_rank_")],
        reverse=True,
    )


@st.cache_data(show_spinner=False, ttl=60)
def _build_manifest_from_rank_info(run_dir: str) -> List[Dict[str, Any]]:
    """
    Build a ranked manifest from individual ``rank_info/<stem>.json`` files.

    Returns a list of dicts sorted by ``rank_score`` ascending (worst first).
    """
    ri_dir = Path(run_dir) / "rank_info"
    if not ri_dir.is_dir():
        return []
    rows: List[Dict[str, Any]] = []
    for jf in sorted(ri_dir.glob("*.json")):
        try:
            payload = json.loads(jf.read_text())
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        rows.append(payload)
    rows.sort(key=lambda r: float(r.get("rank_score", 999.0)))
    return rows


@st.cache_data(show_spinner=False, ttl=60)
def _load_ranked_manifest_csv(csv_path: str) -> List[Dict[str, Any]]:
    """Load a pre-built ``ranked_manifest.csv`` if available."""
    p = Path(csv_path)
    if not p.exists():
        return []
    return read_csv_rows(p, limit=5000)


@st.cache_data(show_spinner=False, ttl=120)
def _load_overlay_image(overlay_path: str) -> Optional[Any]:
    import cv2  # type: ignore

    if not Path(overlay_path).exists():
        return None
    img = cv2.imread(str(overlay_path), cv2.IMREAD_COLOR)
    if img is None:
        return None
    return cv2.cvtColor(img, cv2.COLOR_BGR2RGB).astype(np.uint8, copy=False)


def _best_frame_idx_from_overlays(overlay_dir: Path) -> int:
    """
    Parse frame index from the first ``frame_NNNNNN_overlay.png`` filename.

    If only ``best_overlay.png`` exists, return 0.
    """
    if not overlay_dir.is_dir():
        return 0
    for fn in sorted(overlay_dir.iterdir()):
        nm = fn.name
        if nm.startswith("frame_") and nm.endswith("_overlay.png"):
            try:
                return int(nm.split("_")[1])
            except Exception:
                pass
    return 0


# ---------------------------------------------------------------------------
# Canvas extraction
# ---------------------------------------------------------------------------

def _extract_line_midpoints_from_canvas(canvas_result: Any) -> List[Tuple[float, float]]:
    """
    Extract (mx, my) midpoints for Fabric.js line objects drawn on the canvas.
    """
    if canvas_result is None or canvas_result.json_data is None:
        return []
    objs = canvas_result.json_data.get("objects", [])
    out: List[Tuple[float, float]] = []
    for obj in objs:
        if obj.get("type") != "line":
            continue
        x1 = float(obj.get("x1", 0)) + float(obj.get("left", 0))
        y1 = float(obj.get("y1", 0)) + float(obj.get("top", 0))
        x2 = float(obj.get("x2", 0)) + float(obj.get("left", 0))
        y2 = float(obj.get("y2", 0)) + float(obj.get("top", 0))
        out.append(((x1 + x2) / 2.0, (y1 + y2) / 2.0))
    return out


# ---------------------------------------------------------------------------
# Ellipse fitting from overlay foreground
# ---------------------------------------------------------------------------

def _fit_ellipse_from_overlay(overlay_rgb: Any) -> Optional[Dict[str, Any]]:
    """
    Fit an ellipse to the foreground (non-black) pixels of a mask overlay image.

    Returns dict with ``center``, ``axes``, ``angle_deg``, ``r_inner`` or None.
    """
    import cv2  # type: ignore

    gray = cv2.cvtColor(overlay_rgb, cv2.COLOR_RGB2GRAY)
    _, thresh = cv2.threshold(gray, 15, 255, cv2.THRESH_BINARY)
    pts = np.column_stack(np.where(thresh > 0))
    if len(pts) < 50:
        return None
    pts_xy = pts[:, ::-1].astype(np.float32).reshape(-1, 1, 2)
    try:
        (cx, cy), (w_d, h_d), ang = cv2.fitEllipse(pts_xy)
    except Exception:
        return None
    # Estimate inner radius from contour distance
    dists = np.sqrt((pts[:, 1] - cx) ** 2 + (pts[:, 0] - cy) ** 2)
    r_outer = max(float(w_d), float(h_d)) / 2.0
    if r_outer < 1.0:
        return None
    r_inner_px = float(np.percentile(dists, 5))
    r_inner = r_inner_px / r_outer if r_outer > 0 else 0.5
    return {
        "center": [float(cx), float(cy)],
        "axes": [float(w_d), float(h_d)],
        "angle_deg": float(ang),
        "r_inner": float(r_inner),
    }


# ---------------------------------------------------------------------------
# Sector classification from overlay colors
# ---------------------------------------------------------------------------

def _classify_sectors_from_overlay(
    overlay_rgb: Any,
    cx: float,
    cy: float,
    boundary_angles: List[float],
) -> List[List[float]]:
    """
    For each of the 4 sectors between ``boundary_angles``, sample the overlay
    at the sector midpoint and classify as open (yellow-ish) or closed (blue-ish).

    Returns ``open_angle_ranges`` -- the 2 sectors that are open arms.
    """
    h, w = overlay_rgb.shape[:2]
    open_ranges: List[List[float]] = []
    ba = sorted(boundary_angles)

    for i in range(4):
        a_start = ba[i]
        a_end = ba[(i + 1) % 4]
        if a_end <= a_start:
            mid_angle = ((a_start + a_end + TAU) / 2.0) % TAU
        else:
            mid_angle = (a_start + a_end) / 2.0
        # Sample at ~80% of the way from center to edge
        radius = min(h, w) * 0.35
        sx = int(round(cx + math.cos(mid_angle) * radius))
        sy = int(round(cy + math.sin(mid_angle) * radius))
        sx = max(0, min(sx, w - 1))
        sy = max(0, min(sy, h - 1))
        pixel = overlay_rgb[sy, sx]
        r_val, g_val, b_val = int(pixel[0]), int(pixel[1]), int(pixel[2])
        # Yellow (open) has high R+G, low B; blue (closed) has high B, low R+G
        is_open = (r_val + g_val) > (b_val * 2 + 60) and g_val > 80
        if is_open:
            open_ranges.append([float(a_start), float(a_end)])

    # Expect exactly 2 open sectors; if not, return whatever we found
    return open_ranges


# ---------------------------------------------------------------------------
# Mask generation from corrected zone
# ---------------------------------------------------------------------------

def _make_corrected_mask(
    zone: Dict[str, Any],
    out_hw: Tuple[int, int],
) -> Any:
    """
    Generate a uint8 {0,1,2} pixel mask from a corrected zone JSON.

    Uses image-space angles (atan2(y-cy, x-cx)) everywhere.
    """
    outer = zone.get("outer_ellipse") or {}
    cx, cy = float(outer["center"][0]), float(outer["center"][1])
    ax_w, ax_h = float(outer["axes"][0]), float(outer["axes"][1])
    ang_deg = float(outer["angle_deg"])
    r_inner = float(zone.get("r_inner", 0.5))
    open_ranges = zone.get("open_angle_ranges", [])
    boundary_angles = zone.get("boundary_angles", [])

    h, w = int(out_hw[0]), int(out_hw[1])
    yy, xx = np.mgrid[0:h, 0:w]

    # Ellipse-normalized distance
    ang_rad = math.radians(ang_deg)
    c_rot = math.cos(-ang_rad)
    s_rot = math.sin(-ang_rad)
    dx = xx.astype(np.float64) - cx
    dy = yy.astype(np.float64) - cy
    xn = (dx * c_rot - dy * s_rot) / (ax_w / 2.0) if ax_w > 0 else dx
    yn = (dx * s_rot + dy * c_rot) / (ax_h / 2.0) if ax_h > 0 else dy
    r = np.sqrt(xn * xn + yn * yn)
    in_track = (r >= r_inner) & (r <= 1.0)

    # Image-space angle from center
    phi = np.arctan2(dy, dx) % TAU

    # Classify sectors
    ba = sorted(boundary_angles)
    mask = np.zeros((h, w), dtype=np.uint8)
    if len(ba) == 4 and len(open_ranges) >= 1:
        for rng in open_ranges:
            a_start = float(rng[0]) % TAU
            a_end = float(rng[1]) % TAU
            if a_start <= a_end:
                is_in = (phi >= a_start) & (phi <= a_end)
            else:
                is_in = (phi >= a_start) | (phi <= a_end)
            mask[in_track & is_in] = 1
        mask[(mask == 0) & in_track] = 2
    else:
        mask[in_track] = 2

    return mask


# ---------------------------------------------------------------------------
# Progress tracker
# ---------------------------------------------------------------------------

def _load_progress(run_dir: Path) -> Dict[str, Any]:
    p = run_dir / "border_qc_progress.json"
    if not p.exists():
        return {"corrected": {}}
    try:
        obj = json.loads(p.read_text())
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass
    return {"corrected": {}}


def _save_progress(run_dir: Path, progress: Dict[str, Any]) -> None:
    p = run_dir / "border_qc_progress.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(progress, indent=2, sort_keys=True) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Main render
# ---------------------------------------------------------------------------

def render_ezm_border_qc(*, project_path: Path, workspace_root: Optional[str]) -> None:
    """EZM Border QC view: review inference results and correct open/closed boundaries."""
    st.header("EZM Border QC (inference review)")
    st.caption(
        "Review UNet inference results ranked by quality. "
        "Draw 4 border lines to correct open/closed arm boundaries, "
        "then export corrected zones and masks for retraining."
    )

    if st.button("Refresh (clear cache)", key="ezm_bqc_refresh"):
        st.cache_data.clear()
        st.rerun()

    calc_dir = project_path / "calculated_ezms"
    if not calc_dir.is_dir():
        st.warning(f"No `calculated_ezms/` directory found at: `{calc_dir}`")
        st.info("Run EZM inference ranking first to generate inference results.")
        st.stop()

    # ------------------------------------------------------------------
    # Section 1: Select inference run
    # ------------------------------------------------------------------
    st.subheader("1. Select inference run")
    run_names = _list_infer_runs(str(calc_dir))
    if not run_names:
        st.warning("No `ezm_infer_rank_*` directories found under `calculated_ezms/`.")
        st.info("Run the inference ranking pipeline to produce ranked results.")
        st.stop()

    chosen_run = st.selectbox("Inference run", options=run_names, index=0, key="ezm_bqc_run")
    run_dir = calc_dir / str(chosen_run)
    st.caption(f"Run dir: `{run_dir}`")

    # Try pre-built CSV first, fall back to building from rank_info JSONs
    manifest_csv = run_dir / "ranked_manifest.csv"
    if manifest_csv.exists():
        manifest = _load_ranked_manifest_csv(str(manifest_csv))
        st.caption(f"Loaded manifest from: `{manifest_csv}`")
    else:
        manifest = _build_manifest_from_rank_info(str(run_dir))
        if manifest:
            st.caption(f"Built manifest from `rank_info/` ({len(manifest)} videos)")
        else:
            st.warning("No `ranked_manifest.csv` and no `rank_info/` JSONs found in this run.")
            st.stop()

    if not manifest:
        st.warning("Manifest is empty.")
        st.stop()

    # Summary stats
    n_total = len(manifest)
    n_with_4 = sum(1 for r in manifest if int(float(r.get("n_with_4_crossings", 0))) > 0)
    mean_conf_vals = [float(r.get("mean_confidence", 0)) for r in manifest if r.get("mean_confidence")]
    mean_conf = float(np.mean(mean_conf_vals)) if mean_conf_vals else 0.0
    st.write({
        "total_videos": n_total,
        "videos_with_4_boundaries": n_with_4,
        "mean_confidence": round(mean_conf, 4),
    })

    # ------------------------------------------------------------------
    # Section 2: Video list sorted worst-first
    # ------------------------------------------------------------------
    st.subheader("2. Video list (worst first)")

    display_rows = []
    for r in manifest:
        display_rows.append({
            "video_stem": str(r.get("video_stem", "")),
            "rank_score": float(r.get("rank_score", 0)),
            "boundary_4_frac": float(r.get("boundary_4_frac", 0)),
            "mean_confidence": round(float(r.get("mean_confidence", 0)), 4),
            "open_fraction": round(float(r.get("open_fraction", 0)), 3),
            "n_with_4_crossings": int(float(r.get("n_with_4_crossings", 0))),
        })

    with st.expander("Full ranked table", expanded=False):
        st.dataframe(display_rows, width="stretch", hide_index=True)

    # Navigation state
    nav_sig = (str(run_dir), n_total)
    if st.session_state.get("ezm_bqc_nav_sig") != nav_sig:
        st.session_state["ezm_bqc_nav_sig"] = nav_sig
        st.session_state["ezm_bqc_idx"] = 0
    if "ezm_bqc_idx" not in st.session_state:
        st.session_state["ezm_bqc_idx"] = 0

    cur_idx = int(max(0, min(int(st.session_state["ezm_bqc_idx"]), n_total - 1)))
    st.session_state["ezm_bqc_idx"] = cur_idx

    nav1, nav2, nav3 = st.columns([1, 1, 4])
    with nav1:
        if st.button("Prev", disabled=cur_idx <= 0, key="ezm_bqc_prev"):
            st.session_state["ezm_bqc_idx"] = cur_idx - 1
            st.rerun()
    with nav2:
        if st.button("Next", disabled=cur_idx >= n_total - 1, key="ezm_bqc_next"):
            st.session_state["ezm_bqc_idx"] = cur_idx + 1
            st.rerun()
    with nav3:
        jump = st.number_input(
            "Go to index",
            min_value=0,
            max_value=max(0, n_total - 1),
            value=cur_idx,
            step=1,
            key="ezm_bqc_jump",
        )
        if int(jump) != cur_idx:
            st.session_state["ezm_bqc_idx"] = int(jump)
            st.rerun()

    cur_idx = int(st.session_state["ezm_bqc_idx"])
    cur_row = manifest[cur_idx]
    video_stem = str(cur_row.get("video_stem", ""))
    video_path_str = str(cur_row.get("video_path", ""))

    st.markdown(f"**Item {cur_idx + 1} / {n_total}** -- `{video_stem}`")
    st.write({
        "rank_score": float(cur_row.get("rank_score", 0)),
        "boundary_4_frac": float(cur_row.get("boundary_4_frac", 0)),
        "mean_confidence": round(float(cur_row.get("mean_confidence", 0)), 4),
        "n_with_4_crossings": int(float(cur_row.get("n_with_4_crossings", 0))),
    })

    # ------------------------------------------------------------------
    # Section 3: Overlay display + border drawing
    # ------------------------------------------------------------------
    st.subheader("3. Overlay + border drawing")

    overlay_dir = run_dir / "overlays" / video_stem
    best_overlay_path = overlay_dir / "best_overlay.png"

    if not best_overlay_path.exists():
        st.warning(f"No `best_overlay.png` found at: `{overlay_dir}`")
        st.stop()

    overlay_rgb = _load_overlay_image(str(best_overlay_path))
    if overlay_rgb is None:
        st.error(f"Could not load overlay image: `{best_overlay_path}`")
        st.stop()

    # Determine frame index for the best overlay
    frame_idx = _best_frame_idx_from_overlays(overlay_dir)
    st.caption(f"Video: `{video_path_str}`  |  Best frame idx: `{frame_idx}`")

    # Load raw video frame
    frame_rgb = None
    if video_path_str and Path(video_path_str).exists():
        frame_rgb = _load_frame_rgb(str(video_path_str), frame_idx)

    # Display overlay
    st.markdown("#### Inference overlay")
    if frame_rgb is not None:
        cols = st.columns(2)
        with cols[0]:
            st.image(frame_rgb, caption=f"Raw frame ({video_stem} f={frame_idx})", width="stretch")
        with cols[1]:
            st.image(overlay_rgb, caption="UNet overlay (yellow=open, blue=closed)", width="stretch")
    else:
        st.image(overlay_rgb, caption="UNet overlay (yellow=open, blue=closed)", width="stretch")
        if video_path_str:
            st.warning(f"Could not load raw frame from: `{video_path_str}`")

    # Canvas for drawing border lines
    st.markdown("#### Draw border lines")
    st.caption(
        "Draw **4 lines** marking the open/closed arm boundaries on the overlay. "
        "Each line's midpoint defines a boundary angle from the arena center."
    )

    import PIL.Image  # type: ignore

    orig_h, orig_w = overlay_rgb.shape[:2]
    display_w = 800
    scale = display_w / orig_w if orig_w > 0 else 1.0
    display_h = int(round(orig_h * scale))

    bg_pil = PIL.Image.fromarray(overlay_rgb).resize((display_w, display_h), PIL.Image.LANCZOS)

    try:
        from streamlit_drawable_canvas import st_canvas  # type: ignore
    except ImportError:
        st.error(
            "Missing `streamlit-drawable-canvas-fix` package. "
            "Install with: `pip install streamlit-drawable-canvas-fix`"
        )
        st.stop()

    canvas_result = st_canvas(
        fill_color="rgba(0, 0, 0, 0)",
        stroke_width=3,
        stroke_color="#FF00FF",
        background_image=bg_pil,
        drawing_mode="line",
        height=display_h,
        width=display_w,
        key=f"ezm_border_canvas_{video_stem}",
    )

    midpoints_canvas = _extract_line_midpoints_from_canvas(canvas_result)
    n_lines = len(midpoints_canvas)
    if n_lines == 4:
        st.success(f"Lines drawn: {n_lines} / 4")
    elif n_lines > 0:
        st.info(f"Lines drawn: {n_lines} / 4 (need exactly 4)")
    else:
        st.caption("Lines drawn: 0 / 4")

    # ------------------------------------------------------------------
    # Section 4: Save corrected zone
    # ------------------------------------------------------------------
    st.subheader("4. Save corrected zone")

    can_save = n_lines == 4
    if st.button("Save Zone", type="primary", disabled=(not can_save), key="ezm_bqc_save"):
        # Map canvas midpoints back to original image coordinates
        inv_scale = 1.0 / scale if scale > 0 else 1.0
        midpoints_orig = [
            (mx * inv_scale, my * inv_scale) for (mx, my) in midpoints_canvas
        ]

        # Get ellipse center: try fitting from overlay foreground
        ellipse_info = _fit_ellipse_from_overlay(overlay_rgb)
        if ellipse_info is None:
            st.error("Could not fit ellipse from overlay foreground. The overlay may be empty.")
            st.stop()

        cx = float(ellipse_info["center"][0])
        cy = float(ellipse_info["center"][1])
        ax_w = float(ellipse_info["axes"][0])
        ax_h = float(ellipse_info["axes"][1])
        ang_deg = float(ellipse_info["angle_deg"])
        r_inner = float(ellipse_info["r_inner"])

        # Compute boundary angles (image-space atan2)
        boundary_angles = sorted([
            float(math.atan2(my - cy, mx - cx)) % TAU
            for (mx, my) in midpoints_orig
        ])

        # Classify sectors by sampling overlay colors
        open_ranges = _classify_sectors_from_overlay(overlay_rgb, cx, cy, boundary_angles)

        zone: Dict[str, Any] = {
            "version": "ezm_open_closed_v2",
            "outer_ellipse": {
                "center": [cx, cy],
                "axes": [ax_w, ax_h],
                "angle_deg": ang_deg,
            },
            "r_inner": r_inner,
            "open_angle_ranges": open_ranges,
            "boundary_angles": boundary_angles,
            "annotations": {
                "video_path": video_path_str,
                "frame_idx": frame_idx,
                "borders_canvas": canvas_result.json_data if canvas_result else None,
                "source": "ezm_border_qc_view",
                "canvas_scale": scale,
                "midpoints_orig": midpoints_orig,
            },
        }

        # Save zone JSON
        zone_dir = run_dir / "corrected_zones"
        zone_dir.mkdir(parents=True, exist_ok=True)
        zone_path = zone_dir / f"{video_stem}_ezm_open_closed_v2.json"
        zone_path.write_text(json.dumps(zone, indent=2, sort_keys=False) + "\n", encoding="utf-8")
        st.success(f"Saved zone JSON: `{zone_path}`")

        # Generate and save corrected mask
        ref_frame = frame_rgb if frame_rgb is not None else overlay_rgb
        mask_hw = (ref_frame.shape[0], ref_frame.shape[1])
        mask = _make_corrected_mask(zone, mask_hw)

        mask_dir = run_dir / "corrected_masks"
        mask_dir.mkdir(parents=True, exist_ok=True)
        mask_path = mask_dir / f"{video_stem}_mask.png"

        import cv2  # type: ignore

        cv2.imwrite(str(mask_path), mask)
        st.success(f"Saved mask: `{mask_path}`")

        # Show preview of the corrected mask overlay
        corrected_overlay = blend_mask_overlay(ref_frame, mask)
        st.image(corrected_overlay, caption="Corrected mask overlay", width="stretch")
        st.caption(
            f"mask pixels: open={(mask == 1).sum()}  "
            f"closed={(mask == 2).sum()}  "
            f"bg={(mask == 0).sum()}"
        )

        # Update progress tracker
        progress = _load_progress(run_dir)
        corrected = progress.get("corrected", {})
        corrected[video_stem] = {
            "zone_json": str(zone_path),
            "mask_path": str(mask_path),
            "timestamp": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "rank_score": float(cur_row.get("rank_score", 0)),
        }
        progress["corrected"] = corrected
        progress["last_updated"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        _save_progress(run_dir, progress)
        st.cache_data.clear()

    if not can_save and n_lines > 0:
        st.warning(f"Need exactly 4 border lines to save. Currently have {n_lines}.")

    # ------------------------------------------------------------------
    # Section 5: Progress summary
    # ------------------------------------------------------------------
    st.subheader("5. Progress summary")
    progress = _load_progress(run_dir)
    corrected = progress.get("corrected", {})
    n_corrected = len(corrected)
    st.write({"corrected": n_corrected, "total": n_total})

    if corrected:
        progress_rows = []
        for stem, info in sorted(corrected.items()):
            progress_rows.append({
                "video_stem": stem,
                "rank_score": info.get("rank_score", ""),
                "timestamp": info.get("timestamp", ""),
                "zone_json": info.get("zone_json", ""),
            })
        with st.expander(f"Corrected videos ({n_corrected})", expanded=False):
            st.dataframe(progress_rows, width="stretch", hide_index=True)
    else:
        st.info("No videos corrected yet.")

    # ------------------------------------------------------------------
    # Section 6: Export for retraining
    # ------------------------------------------------------------------
    st.subheader("6. Export for retraining")

    if n_corrected == 0:
        st.info("Correct at least one video before exporting.")
        return

    export_csv_path = run_dir / "border_qc_training_export.csv"
    if st.button("Export training CSV", key="ezm_bqc_export"):
        rows_out: List[Dict[str, str]] = []
        for stem, info in sorted(corrected.items()):
            zj = str(info.get("zone_json", ""))
            # Look up video_path from the manifest
            matching = [r for r in manifest if str(r.get("video_stem", "")) == stem]
            vp = str(matching[0].get("video_path", "")) if matching else ""
            # Get frame_idx from the zone JSON if available
            fi = 0
            try:
                zp = json.loads(Path(zj).read_text())
                fi = int(zp.get("annotations", {}).get("frame_idx", 0))
            except Exception:
                pass
            rows_out.append({
                "video_path": vp,
                "zone_json": zj,
                "frame_idx": str(fi),
                "label_source": "ezm_border_qc",
            })

        export_csv_path.parent.mkdir(parents=True, exist_ok=True)
        with export_csv_path.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["video_path", "zone_json", "frame_idx", "label_source"])
            w.writeheader()
            for r in rows_out:
                w.writerow(r)

        st.success(f"Wrote training CSV: `{export_csv_path}` ({len(rows_out)} rows)")

    if export_csv_path.exists():
        st.caption(f"Training CSV: `{export_csv_path}`")
        with st.expander("Preview training CSV", expanded=False):
            export_rows = read_csv_rows(export_csv_path, limit=200)
            st.dataframe(export_rows, width="stretch", hide_index=True)

    # Submit retrain SLURM job
    st.markdown("#### Submit retrain")
    repo_root = Path(__file__).resolve().parents[4]
    slurm_script = (
        repo_root / "workspace" / "dlc_ezm_open_closed" / "torch_ml"
        / "run_train_unet_open_closed_from_zones_augfix_sched_and_qc.slurm"
    )

    if not slurm_script.exists():
        st.caption(f"Slurm script not found: `{slurm_script}`")
        st.caption("Cannot submit retrain from the UI without the training script.")
        return

    st.caption(f"Training script: `{slurm_script}`")

    check = st.button("Check for idle nodes", key="ezm_bqc_check_idle")
    idle_ok = False
    if check:
        try:
            r = subprocess.run(
                ["sinfo", "-h", "-t", "idle,mix", "-o", "%P %D %N"],
                check=False, capture_output=True, text=True,
            )
            out = (r.stdout or "").strip()
            err = (r.stderr or "").strip()
            if err:
                st.caption(err)
            st.code(out or "(no output)")
            idle_ok = bool(out)
        except Exception as e:
            st.error(f"sinfo failed: {e}")

    submit = st.button("Submit retrain job", key="ezm_bqc_submit", disabled=not check)
    if submit:
        if not idle_ok:
            st.error("No idle/mix nodes detected. Not submitting.")
            st.stop()
        if not export_csv_path.exists():
            st.error("Export the training CSV first.")
            st.stop()

        ws_root = Path(str(workspace_root)).expanduser().resolve() if workspace_root else project_path
        export_vars = ",".join([
            "ALL",
            f"MUS1_TRAINING_CSV={str(export_csv_path)}",
            f"MOSEQ2_WORKSPACE_ROOT={str(ws_root)}",
        ])
        try:
            r = subprocess.run(
                ["sbatch", "--export", export_vars, str(slurm_script)],
                check=False, capture_output=True, text=True,
            )
            if r.returncode != 0:
                st.error(r.stderr or r.stdout or "sbatch failed.")
            else:
                msg = (r.stdout or "").strip()
                st.success(msg or "Submitted.")
                jobid = msg.split()[-1] if msg else ""
                if jobid.isdigit():
                    st.code(
                        "\n".join([
                            f"squeue -j {jobid}",
                            f"sacct -j {jobid} --format=JobID,JobName%25,State,Elapsed,MaxRSS,AllocCPUS,NodeList%25",
                        ])
                    )
        except Exception as e:
            st.error(f"sbatch failed: {e}")
