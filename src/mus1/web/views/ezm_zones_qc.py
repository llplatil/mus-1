from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import streamlit as st

from ..ezm_masks import blend_mask_overlay, blend_safe_bg_overlay, make_ezm_open_closed_mask, make_ezm_safe_bg_mask
from ..io import parse_meta


@st.cache_data(show_spinner=False)
def list_ezm_zone_jsons_from_db(db_path: str) -> List[Dict[str, Any]]:
    """
    Return per-video EZM zone JSONs indexed into MUS1 DB.

    Requires: `mus1 import arena-zones ...` to have been run.
    """
    try:
        import sqlite3

        con = sqlite3.connect(str(db_path))
        con.row_factory = sqlite3.Row
        rows = con.execute(
            """
            SELECT path, meta_json, created_at
            FROM external_artifacts
            WHERE kind = 'ezm_zone_json_v2'
            ORDER BY created_at DESC
            LIMIT 5000
            """,
            (),
        ).fetchall()
    except Exception:
        return []
    finally:
        try:
            con.close()
        except Exception:
            pass

    out: List[Dict[str, Any]] = []
    # De-dupe by exact path (re-importing can create duplicate artifacts).
    seen: set[str] = set()
    for r in rows:
        p = str(Path(str(r["path"])))
        if p in seen:
            continue
        seen.add(p)
        out.append({"zone_json": p, "meta": parse_meta(r["meta_json"]), "created_at": str(r["created_at"])})
    return out


def _resolve_video_from_zone_payload(payload: dict, *, workspace_root: Path) -> Tuple[Optional[Path], int]:
    ann = (payload or {}).get("annotations") or {}
    # Prefer MUS1 annotator fields
    vp = str(ann.get("video_path") or "").strip()
    fi = ann.get("frame_idx")
    if vp:
        p = Path(vp)
        if not p.is_absolute():
            p = (workspace_root / p).resolve()
        return p, int(fi) if str(fi).strip() else 0
    # Legacy schema
    calib = ann.get("calibration") or {}
    vp = str(calib.get("video_path") or "").strip()
    fi = calib.get("frame_idx")
    if vp:
        p = Path(vp)
        if not p.is_absolute():
            p = (workspace_root / p).resolve()
        return p, int(fi) if str(fi).strip() else 0
    return None, 0


def _workspace_relative(p: Path, workspace_root: Path) -> str:
    try:
        return str(p.resolve().relative_to(workspace_root.resolve()))
    except Exception:
        return str(p)

def _resolve_zone_json_alias(z: Path, *, repo_root: Path, workspace_root: Path) -> Path:
    """
    Resolve stale zone-json paths that used to live under the MoSeq2 workspace.

    Historically:
      <workspace_root>/resources/arena_zones/...
    Now canonical:
      <repo_root>/workspace/arena_zones/...
    """
    z = Path(z)
    if z.exists():
        return z
    # Common stale prefix
    stale_prefix = (workspace_root / "resources" / "arena_zones").resolve()
    try:
        rel = z.resolve().relative_to(stale_prefix)
    except Exception:
        rel = None
    if rel is not None:
        cand = (repo_root / "workspace" / "arena_zones" / rel).resolve()
        if cand.exists():
            return cand
    # Fallback by basename within canonical EZM folder
    cand2 = (repo_root / "workspace" / "arena_zones" / "ezm_per_video_v2" / z.name).resolve()
    if cand2.exists():
        return cand2
    return z


def _resolve_video_abs(video_path_str: str, *, workspace_root: Path) -> Path:
    p = Path(str(video_path_str).strip())
    if p.is_absolute():
        return p
    return (workspace_root / p).resolve()


@st.cache_data(show_spinner=False, ttl=60)
def _load_frame_rgb(video_abs: str, frame_idx: int) -> Optional[Any]:
    try:
        import cv2  # type: ignore
        import numpy as np  # type: ignore
    except Exception:
        return None

    cap = cv2.VideoCapture(str(video_abs))
    if not cap.isOpened():
        return None
    cap.set(cv2.CAP_PROP_POS_FRAMES, int(frame_idx))
    ok, frame_bgr = cap.read()
    cap.release()
    if not ok or frame_bgr is None:
        return None
    frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
    return frame_rgb.astype(np.uint8, copy=False)


def _load_draft_csv(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    try:
        with path.open("r", encoding="utf-8", newline="") as f:
            r = csv.DictReader(f)
            rows = []
            has_label_mode = "label_mode" in (r.fieldnames or [])
            for row in r:
                if not isinstance(row, dict):
                    continue
                vp = str(row.get("video_path") or "").strip()
                zj = str(row.get("zone_json") or "").strip()
                ls = str(row.get("label_source") or "").strip().lower()
                fi = str(row.get("frame_idx") or "").strip()
                lm = str(row.get("label_mode") or "").strip().lower() if has_label_mode else ""
                if not vp or not zj:
                    continue
                rr = {"video_path": vp, "zone_json": zj, "label_source": ls, "frame_idx": fi}
                if has_label_mode:
                    rr["label_mode"] = lm
                rows.append(rr)
            return rows
    except Exception:
        return []


def _write_draft_csv(path: Path, rows: List[Dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # de-dupe by (zone_json, frame_idx) so users can add multiple anchors per video.
    seen: set[tuple[str, str]] = set()
    out: List[Dict[str, str]] = []
    for r in rows:
        zj = str(r.get("zone_json") or "").strip()
        vp = str(r.get("video_path") or "").strip()
        ls = str(r.get("label_source") or "").strip().lower()
        fi = str(r.get("frame_idx") or "").strip()
        if not zj or not vp:
            continue
        key = (zj, fi)
        if key in seen:
            continue
        seen.add(key)
        out.append({"video_path": vp, "zone_json": zj, "label_source": ls, "frame_idx": fi})
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["video_path", "zone_json", "label_source", "frame_idx"])
        w.writeheader()
        for r in out:
            w.writerow(
                {
                    "video_path": r["video_path"],
                    "zone_json": r["zone_json"],
                    "label_source": r.get("label_source", ""),
                    "frame_idx": r.get("frame_idx", ""),
                }
            )


@st.cache_data(show_spinner=False, ttl=120)
def _video_fps_and_nframes(video_abs: str) -> Tuple[float, int]:
    try:
        import cv2  # type: ignore
    except Exception:
        return 0.0, 0
    cap = cv2.VideoCapture(str(video_abs))
    if not cap.isOpened():
        return 0.0, 0
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    cap.release()
    return fps, n


def _default_frame_idx_from_zone_json(zone_json: Path) -> int:
    try:
        payload = json.loads(Path(zone_json).read_text())
    except Exception:
        return 0
    ann = (payload or {}).get("annotations") or {}
    fi = ann.get("frame_idx")
    try:
        return int(float(fi))
    except Exception:
        return 0


def _write_rows_csv(path: Path, rows: List[Dict[str, str]], *, include_label_mode: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["video_path", "zone_json", "label_source", "frame_idx"]
    if include_label_mode:
        fieldnames.append("label_mode")
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            out = {k: str(r.get(k, "") or "") for k in fieldnames}
            w.writerow(out)

def render_ezm_zones_qc(*, db_path: Path, workspace_root: Optional[str], project_path: Path) -> None:
    st.header("EZM zones QC (pre-run)")
    st.caption("Preview all labeled videos + masks, choose mask fit mode, and export a curated training CSV.")
    if st.button("Refresh (clear cache)"):
        st.cache_data.clear()
        st.rerun()

    if not workspace_root:
        st.error("This view requires `--workspace-root` so we can resolve relative video paths.")
        st.stop()
    ws_root = Path(str(workspace_root)).expanduser().resolve()
    repo_root = Path(__file__).resolve().parents[4]

    zone_rows = list_ezm_zone_jsons_from_db(str(db_path))
    if not zone_rows:
        st.info("No EZM zone JSONs indexed in the DB yet.")
        st.code(
            f"mus1 import arena-zones --project-path \"{project_path}\" --workspace-root \"{ws_root}\"",
            language=None,
        )
        st.stop()

    st.subheader("Mask fit mode")
    label_source = st.selectbox(
        "Mask fit / label source",
        options=["auto", "derived", "annotations"],
        index=0,
        help=(
            "`annotations` is the strictest QC because it uses the raw clicks/lines saved in the JSON. "
            "If `annotations` looks wrong, your saved markup is wrong. "
            "`derived` checks the parametric fields (outer_ellipse/r_inner/open_angle_ranges)."
        ),
        key="mus1_ezm_zoneqc_label_source",
    )
    show_safe_bg = bool(
        st.checkbox(
            "Overlay SAFE_BG ('this is NOT open/closed') regions",
            value=False,
            help="Shows safe center ellipse + safe outside band enforced as background (red tint).",
        )
    )

    st.subheader("Pick an item to inspect")
    default_draft = project_path / "ml_review" / "ezm_unet" / "training_per_video_draft.csv"
    draft_path = Path(st.text_input("Draft CSV path", value=str(default_draft), key="mus1_ezm_zoneqc_draft_path"))
    draft_rows = _load_draft_csv(draft_path)
    in_draft_names = {Path(str(r.get("zone_json") or "")).name for r in draft_rows}
    default_out = project_path / "ml_review" / "ezm_unet" / "training_per_video_curated.csv"
    curated_rows = _load_draft_csv(default_out)
    in_curated_names = {Path(str(r.get("zone_json") or "")).name for r in curated_rows}

    col_f1, col_f2, col_f3 = st.columns([1, 1, 2])
    with col_f1:
        hide_in_draft = st.checkbox("Hide already in draft", value=True)
    with col_f2:
        hide_missing = st.checkbox("Hide missing JSON paths", value=True)
    with col_f3:
        name_filter = st.text_input("Filter (substring)", value="")
    hide_in_curated = st.checkbox("Hide already in curated CSV", value=False)

    filtered = []
    for r in zone_rows[:5000]:
        zp = Path(str(r.get("zone_json") or ""))
        nm = zp.name
        if hide_in_draft and nm in in_draft_names:
            continue
        if hide_in_curated and nm in in_curated_names:
            continue
        if name_filter.strip() and (name_filter.strip().lower() not in nm.lower()):
            continue
        zp2 = _resolve_zone_json_alias(zp, repo_root=repo_root, workspace_root=ws_root)
        if hide_missing and not Path(zp2).exists():
            continue
        rr = dict(r)
        rr["_zone_json_resolved"] = str(zp2)
        filtered.append(rr)

    if not filtered:
        st.info("No zone JSONs match current filters.")
        st.stop()

    labels = [f"{Path(r['_zone_json_resolved']).name}  {r.get('created_at','')}" for r in filtered[:3000]]
    choice = st.selectbox("Zone JSON", options=labels, index=0)
    rec = filtered[labels.index(choice)]
    zone_json = Path(str(rec["_zone_json_resolved"]))

    try:
        payload = json.loads(zone_json.read_text())
    except Exception as e:
        st.error(f"Could not read JSON: {zone_json} ({e})")
        st.stop()

    video_path, default_frame = _resolve_video_from_zone_payload(payload, workspace_root=ws_root)
    if video_path is None:
        st.error("Zone JSON does not include an embedded video_path under annotations.")
        st.json(payload.get("annotations") or {}, expanded=False)
        st.stop()

    st.write(
        {
            "zone_json": str(zone_json),
            "video_path": str(video_path),
            "video_exists": bool(video_path.exists()),
            "default_frame_idx": int(default_frame),
        }
    )
    if not video_path.exists():
        st.error("Video path does not exist on disk. Fix the zone JSON or workspace root.")
        st.stop()

    # Frame selector (default to stored frame_idx)
    frame_idx = int(st.number_input("Frame idx", min_value=0, value=int(default_frame), step=1))

    try:
        import cv2  # type: ignore
        import numpy as np  # type: ignore
    except Exception:
        st.error("opencv/numpy missing; cannot preview frames.")
        st.stop()

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        st.error(f"Could not open video: {video_path}")
        st.stop()
    cap.set(cv2.CAP_PROP_POS_FRAMES, int(frame_idx))
    ok, frame_bgr = cap.read()
    cap.release()
    if not ok or frame_bgr is None:
        st.error(f"Could not read frame {frame_idx} from: {video_path}")
        st.stop()
    frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)

    mask = None
    overlay = frame_rgb
    if bool(show_safe_bg):
        try:
            safe = make_ezm_safe_bg_mask(zone_json, out_hw=(frame_rgb.shape[0], frame_rgb.shape[1]))
            overlay = blend_safe_bg_overlay(frame_rgb, safe)
        except Exception as e:
            st.error(f"Could not make SAFE_BG overlay: {e}")
    else:
        try:
            mask = make_ezm_open_closed_mask(zone_json, out_hw=(frame_rgb.shape[0], frame_rgb.shape[1]), label_source=label_source)  # type: ignore[arg-type]
            overlay = blend_mask_overlay(frame_rgb, mask)
        except Exception as e:
            st.error(f"Could not rasterize mask ({label_source}): {e}")
            overlay = frame_rgb
            mask = None

    cols = st.columns(2)
    with cols[0]:
        st.image(frame_rgb, caption=f"{video_path.name} frame={frame_idx}", width="stretch")
    with cols[1]:
        st.image(
            overlay,
            caption=("SAFE_BG overlay" if bool(show_safe_bg) else f"mask overlay ({label_source})"),
            width="stretch",
        )
        if mask is not None:
            st.caption(f"mask pixels: open={(mask == 1).sum()} closed={(mask == 2).sum()} bg={(mask == 0).sum()}")

    st.subheader("Curate training set")
    st.caption("Build a draft set incrementally (add/remove per-video), then export the final CSV for a run.")

    draft_keys = {(str(r.get("zone_json") or "").strip(), str(r.get("frame_idx") or "").strip()) for r in draft_rows}

    # This row is what we'd add/remove.
    cur_row = {
        "video_path": _workspace_relative(video_path, ws_root),
        "zone_json": str(zone_json.resolve()),
        "label_source": str(label_source).strip().lower(),
        "frame_idx": str(int(frame_idx)),
    }
    cur_key = (str(cur_row["zone_json"]).strip(), str(cur_row["frame_idx"]).strip())
    cur_in_draft = cur_key in draft_keys

    col_a, col_b, col_c = st.columns([1, 1, 2])
    with col_a:
        if st.button("Add this video to draft", type="primary", disabled=cur_in_draft):
            new_rows = draft_rows + [cur_row]
            _write_draft_csv(draft_path, new_rows)
            st.success("Added to draft.")
            st.rerun()
    with col_b:
        if st.button("Remove this (video, frame_idx) from draft", disabled=(not cur_in_draft)):
            new_rows = [
                r
                for r in draft_rows
                if not (
                    str(r.get("zone_json", "")).strip() == str(cur_row["zone_json"]).strip()
                    and str(r.get("frame_idx", "")).strip() == str(cur_row["frame_idx"]).strip()
                )
            ]
            _write_draft_csv(draft_path, new_rows)
            st.success("Removed from draft.")
            st.rerun()
        if cur_in_draft and st.button("Update mask mode for this (video, frame_idx) in draft"):
            new_rows = []
            for r in draft_rows:
                if (
                    str(r.get("zone_json", "")).strip() == str(cur_row["zone_json"]).strip()
                    and str(r.get("frame_idx", "")).strip() == str(cur_row["frame_idx"]).strip()
                ):
                    rr = dict(r)
                    rr["label_source"] = cur_row["label_source"]
                    new_rows.append(rr)
                else:
                    new_rows.append(r)
            _write_draft_csv(draft_path, new_rows)
            st.success("Updated mask mode in draft.")
            st.rerun()
    with col_c:
        if st.button("Clear draft (delete all rows)", disabled=(len(draft_rows) == 0)):
            _write_draft_csv(draft_path, [])
            st.success("Draft cleared.")
            st.rerun()

    st.write({"draft_videos": int(len(draft_rows)), "total_indexed_zone_jsons": len(zone_rows)})

    with st.expander("Draft contents", expanded=(len(draft_rows) > 0)):
        st.dataframe(draft_rows, width="stretch", hide_index=True)

    st.subheader("Export final training CSV")
    out_path = Path(st.text_input("Final CSV path", value=str(default_out), key="mus1_ezm_zoneqc_out_path"))

    if st.button("Write curated training CSV from draft", type="primary", disabled=(len(draft_rows) == 0)):
        _write_draft_csv(out_path, draft_rows)
        st.success(f"Wrote: {out_path} ({len(draft_rows)} videos)")
        st.code(
            "\n".join(
                [
                    "# Use this CSV for training:",
                    f"#   --training-per-video-csv \"{out_path}\"",
                    "# (or export MUS1_TRAINING_CSV to the slurm script)",
                ]
            ),
            language=None,
        )

    with st.expander("Expand curated set (minute increments, no extra annotation)", expanded=False):
        st.caption(
            "Writes a NEW CSV with many `frame_idx` rows per video, using the SAME zone JSON + label_source. "
            "This increases within-video variation (animal position) without re-annotating."
        )
        stride_seconds = int(st.number_input("Stride seconds (e.g. 60 for 1 min)", min_value=1, value=60, step=1))
        n_steps = int(st.number_input("How many steps forward", min_value=1, value=6, step=1))
        include_base = bool(st.checkbox("Include the marked frame itself", value=True))
        write_safe_bg = bool(
            st.checkbox(
                "Also write SAFE_BG variant (expanded frames become weak-label background-only)",
                value=False,
            )
        )

        default_full = out_path.with_name(out_path.stem + f"_expanded_{stride_seconds}s_full.csv")
        full_path = Path(st.text_input("Expanded FULL CSV path", value=str(default_full)))
        default_safe = out_path.with_name(out_path.stem + f"_expanded_{stride_seconds}s_safe_bg.csv")
        safe_path = Path(st.text_input("Expanded SAFE_BG CSV path", value=str(default_safe)))

        if st.button("Write expanded FULL CSV", disabled=(len(draft_rows) == 0), type="primary"):
            out_rows: List[Dict[str, str]] = []
            for r in draft_rows:
                vp_rel = str(r.get("video_path") or "").strip()
                zj = str(r.get("zone_json") or "").strip()
                ls = str(r.get("label_source") or "").strip().lower() or "auto"
                if not vp_rel or not zj:
                    continue
                video_abs = _resolve_video_abs(vp_rel, workspace_root=ws_root)
                zj_abs = _resolve_zone_json_alias(Path(zj), repo_root=repo_root, workspace_root=ws_root)
                base = str(r.get("frame_idx") or "").strip()
                try:
                    base_fi = int(float(base)) if base else _default_frame_idx_from_zone_json(zj_abs)
                except Exception:
                    base_fi = _default_frame_idx_from_zone_json(zj_abs)
                fps, nfr = _video_fps_and_nframes(str(video_abs))
                if fps <= 1e-6:
                    fps = 30.0
                stride_frames = int(round(float(stride_seconds) * float(fps)))
                fis: List[int] = []
                if include_base:
                    fis.append(int(base_fi))
                for k in range(1, int(n_steps) + 1):
                    fis.append(int(base_fi) + int(k) * int(stride_frames))
                if nfr > 0:
                    fis = [int(x) for x in fis if 0 <= int(x) <= int(nfr - 1)]
                fis = sorted(set(fis))
                for fi in fis:
                    out_rows.append(
                        {
                            "video_path": vp_rel,
                            "zone_json": str(zj_abs),
                            "label_source": ls,
                            "frame_idx": str(int(fi)),
                            "label_mode": "full",
                        }
                    )
            _write_rows_csv(full_path, out_rows, include_label_mode=True)
            st.success(f"Wrote: {full_path} (rows={len(out_rows)})")

        if write_safe_bg and st.button("Write expanded SAFE_BG CSV", disabled=(len(draft_rows) == 0)):
            out_rows2: List[Dict[str, str]] = []
            for r in draft_rows:
                vp_rel = str(r.get("video_path") or "").strip()
                zj = str(r.get("zone_json") or "").strip()
                ls = str(r.get("label_source") or "").strip().lower() or "auto"
                if not vp_rel or not zj:
                    continue
                video_abs = _resolve_video_abs(vp_rel, workspace_root=ws_root)
                zj_abs = _resolve_zone_json_alias(Path(zj), repo_root=repo_root, workspace_root=ws_root)
                base = str(r.get("frame_idx") or "").strip()
                try:
                    base_fi = int(float(base)) if base else _default_frame_idx_from_zone_json(zj_abs)
                except Exception:
                    base_fi = _default_frame_idx_from_zone_json(zj_abs)
                fps, nfr = _video_fps_and_nframes(str(video_abs))
                if fps <= 1e-6:
                    fps = 30.0
                stride_frames = int(round(float(stride_seconds) * float(fps)))
                fis: List[int] = []
                if include_base:
                    fis.append(int(base_fi))
                for k in range(1, int(n_steps) + 1):
                    fis.append(int(base_fi) + int(k) * int(stride_frames))
                if nfr > 0:
                    fis = [int(x) for x in fis if 0 <= int(x) <= int(nfr - 1)]
                fis = sorted(set(fis))
                for j, fi in enumerate(fis):
                    lm = "full" if (j == 0 and include_base) else "safe_bg"
                    out_rows2.append(
                        {
                            "video_path": vp_rel,
                            "zone_json": str(zj_abs),
                            "label_source": ls,
                            "frame_idx": str(int(fi)),
                            "label_mode": lm,
                        }
                    )
            _write_rows_csv(safe_path, out_rows2, include_label_mode=True)
            st.success(f"Wrote: {safe_path} (rows={len(out_rows2)})")

    st.subheader("Preview final training set (what will go into training)")
    st.caption("This renders the exact marked frame per video (frame_idx) + mask overlay, so you can QC inputs before submitting Slurm.")
    preview_source = st.radio(
        "Preview source",
        options=["draft", "curated CSV file"],
        index=0,
        horizontal=True,
        help="Preview the draft-in-progress, or preview the last written curated CSV file.",
    )
    preview_rows = draft_rows if preview_source == "draft" else _load_draft_csv(out_path)
    if not preview_rows:
        st.info("Nothing to preview yet.")
        return

    ncols = int(st.slider("Grid columns", min_value=2, max_value=6, value=3, step=1))
    show_raw = bool(st.checkbox("Show raw frame next to overlay", value=False))
    respect_label_mode = bool(
        st.checkbox(
            "Respect `label_mode` (SAFE_BG rows show SAFE_BG overlay)",
            value=True,
            help="If a CSV row has label_mode=safe_bg, we render the red SAFE_BG overlay instead of open/closed.",
        )
    )

    errors: List[Dict[str, str]] = []
    cols = st.columns(ncols)
    for i, r in enumerate(preview_rows):
        vp_rel = str(r.get("video_path") or "").strip()
        zj = str(r.get("zone_json") or "").strip()
        ls = str(r.get("label_source") or "").strip().lower() or "auto"
        lm = str(r.get("label_mode") or "").strip().lower()
        try:
            fi = int(float(str(r.get("frame_idx") or "0").strip() or "0"))
        except Exception:
            fi = 0

        video_abs = _resolve_video_abs(vp_rel, workspace_root=ws_root)
        frame = _load_frame_rgb(str(video_abs), int(fi))
        if frame is None:
            errors.append(
                {
                    "video_path": vp_rel,
                    "zone_json": zj,
                    "label_source": ls,
                    "label_mode": lm,
                    "frame_idx": str(fi),
                    "error": "frame_read_failed",
                }
            )
            continue

        try:
            zj_abs = _resolve_zone_json_alias(Path(zj), repo_root=repo_root, workspace_root=ws_root)
            if bool(respect_label_mode) and str(lm) == "safe_bg":
                safe = make_ezm_safe_bg_mask(Path(zj_abs), out_hw=(int(frame.shape[0]), int(frame.shape[1])))
                overlay = blend_safe_bg_overlay(frame, safe)
            else:
                mask = make_ezm_open_closed_mask(
                    Path(zj_abs),
                    out_hw=(int(frame.shape[0]), int(frame.shape[1])),
                    label_source=ls,  # type: ignore[arg-type]
                )
                overlay = blend_mask_overlay(frame, mask)
        except Exception as e:
            errors.append(
                {
                    "video_path": vp_rel,
                    "zone_json": zj,
                    "label_source": ls,
                    "label_mode": lm,
                    "frame_idx": str(fi),
                    "error": f"mask_failed: {e}",
                }
            )
            overlay = frame

        with cols[i % ncols]:
            suffix = f"  lm={lm}" if lm else ""
            cap = f"{Path(vp_rel).name}  fi={fi}  ls={ls}{suffix}"
            if show_raw:
                st.image([frame, overlay], caption=[cap + " (raw)", cap + " (overlay)"], width="stretch")
            else:
                st.image(overlay, caption=cap, width="stretch")

    if errors:
        with st.expander(f"Preview errors ({len(errors)})", expanded=False):
            st.dataframe(errors, width="stretch", hide_index=True)

