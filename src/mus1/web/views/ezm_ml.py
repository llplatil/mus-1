from __future__ import annotations

import json
import math
import os
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import streamlit as st

from ..db import fetchall
from ..io import parse_meta, read_csv_rows
from ..ezm_masks import blend_mask_overlay
from ..ml_tables import ensure_ml_tables

# ---------------------------------------------------------------------------
# Lazy import: experiment_dataset_builder lives in the workspace torch_ml dir.
# ---------------------------------------------------------------------------
_TORCH_ML_DIR = None


def _get_torch_ml_dir() -> Path:
    global _TORCH_ML_DIR
    if _TORCH_ML_DIR is None:
        _TORCH_ML_DIR = Path(__file__).resolve().parents[4] / "workspace" / "dlc_ezm_open_closed" / "torch_ml"
    return _TORCH_ML_DIR


def _ensure_builder_importable():
    d = str(_get_torch_ml_dir())
    if d not in sys.path:
        sys.path.insert(0, d)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@st.cache_data(show_spinner=False)
def list_ezm_unet_runs_from_db(db_path: str) -> List[Dict[str, Any]]:
    try:
        con = sqlite3.connect(str(db_path))
        con.row_factory = sqlite3.Row
        rows = con.execute(
            """
            SELECT path, meta_json, created_at
            FROM external_artifacts
            WHERE kind = 'ezm_unet_run_dir'
            ORDER BY created_at DESC
            LIMIT 200
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
    for r in rows:
        p = Path(str(r["path"]))
        meta = parse_meta(r["meta_json"])
        out.append({"run_path": str(p), "name": p.name, "created_at": str(r["created_at"]), "indexed_meta": meta})
    return out


@st.cache_data(show_spinner="Loading EZM training sources...", ttl=120)
def _load_train_val_split(cohort_name: str) -> Dict[str, Any]:
    """Load train/val split from experiment_data (cached)."""
    _ensure_builder_importable()
    from experiment_dataset_builder import build_training_sources
    split = build_training_sources(cohort_name=cohort_name)
    # Convert to serializable dicts for Streamlit caching.
    def _src_to_dict(s):
        return {
            "experiment_id": s.experiment_id,
            "video_path": str(s.video_path),
            "zone_payload": s.zone_payload,
            "frame_shape": s.frame_shape,
        }
    return {
        "train": [_src_to_dict(s) for s in split.train],
        "val": [_src_to_dict(s) for s in split.val],
        "skipped": split.skipped,
        "cohort_name": split.cohort_name,
    }


def _load_frame_rgb(video_path: str, frame_idx: int):
    import cv2
    import numpy as np
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return None
    cap.set(cv2.CAP_PROP_POS_FRAMES, int(frame_idx))
    ok, frame_bgr = cap.read()
    cap.release()
    if not ok or frame_bgr is None:
        return None
    return cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB).astype(np.uint8, copy=False)


def _make_mask_from_payload(payload: Dict[str, Any], out_hw: Tuple[int, int]):
    """Render zone mask from a payload dict (no file IO)."""
    _ensure_builder_importable()
    sys.path.insert(0, str(_get_torch_ml_dir().parent))
    from ezm_open_closed_zones import EllipseParams, ZoneDefinition, compute_r_theta, angle_in_any_open_range
    import numpy as np

    outer = payload["outer_ellipse"]
    z = ZoneDefinition(
        outer_ellipse=EllipseParams(
            center_xy=(float(outer["center"][0]), float(outer["center"][1])),
            axes_xy=(float(outer["axes"][0]), float(outer["axes"][1])),
            angle_deg=float(outer.get("angle_deg", 0.0)),
        ),
        r_inner=float(payload["r_inner"]),
        open_angle_ranges=(
            (float(payload["open_angle_ranges"][0][0]), float(payload["open_angle_ranges"][0][1])),
            (float(payload["open_angle_ranges"][1][0]), float(payload["open_angle_ranges"][1][1])),
        ),
        version=str(payload.get("version", "ezm_open_closed_v2")),
    )
    h, w = int(out_hw[0]), int(out_hw[1])
    yy, xx = np.mgrid[0:h, 0:w]
    r, theta = compute_r_theta(xx.reshape(-1), yy.reshape(-1), z.outer_ellipse)
    r = r.reshape(h, w)
    theta = theta.reshape(h, w)
    in_track = (r >= float(z.r_inner)) & (r <= 1.0)
    is_open = in_track & angle_in_any_open_range(theta, z.open_angle_ranges)
    is_closed = in_track & (~is_open)
    mask = np.zeros((h, w), dtype=np.uint8)
    mask[is_open] = 1
    mask[is_closed] = 2
    return mask


def _safe_bg_mask_from_payload(payload: Dict[str, Any], out_hw: Tuple[int, int]):
    """Render safe_bg weak-label mask from a payload dict."""
    sys.path.insert(0, str(_get_torch_ml_dir().parent))
    from ezm_open_closed_zones import EllipseParams, ZoneDefinition, compute_r_theta
    import numpy as np

    outer = payload["outer_ellipse"]
    z = ZoneDefinition(
        outer_ellipse=EllipseParams(
            center_xy=(float(outer["center"][0]), float(outer["center"][1])),
            axes_xy=(float(outer["axes"][0]), float(outer["axes"][1])),
            angle_deg=float(outer.get("angle_deg", 0.0)),
        ),
        r_inner=float(payload["r_inner"]),
        open_angle_ranges=(
            (float(payload["open_angle_ranges"][0][0]), float(payload["open_angle_ranges"][0][1])),
            (float(payload["open_angle_ranges"][1][0]), float(payload["open_angle_ranges"][1][1])),
        ),
        version="ezm_open_closed_v2",
    )
    h, w = int(out_hw[0]), int(out_hw[1])
    yy, xx = np.mgrid[0:h, 0:w]
    r, _ = compute_r_theta(xx.reshape(-1), yy.reshape(-1), z.outer_ellipse)
    r = r.reshape(h, w).astype(np.float64, copy=False)
    IGNORE = 255
    safe_center = r <= (float(z.r_inner) * 0.85)
    safe_outside = r >= 1.12
    mask = np.full((h, w), IGNORE, dtype=np.uint8)
    mask[safe_center | safe_outside] = 0
    return mask


# ---------------------------------------------------------------------------
# In-memory inference (no disk writes)
# ---------------------------------------------------------------------------

@st.cache_resource(show_spinner="Loading model weights...")
def _load_unet_model(model_path: str):
    """Load TinyUNet weights into eval mode. Cached per model path."""
    import torch
    _ensure_builder_importable()
    sys.path.insert(0, str(_get_torch_ml_dir()))
    from train_unet_open_closed import TinyUNet
    model = TinyUNet(in_ch=1, n_classes=3, base=16)
    state = torch.load(str(model_path), map_location="cpu")
    # model_best.pt is saved as a raw state_dict(); checkpoints wrap it under "model_state"
    if isinstance(state, dict) and "model_state" in state:
        model.load_state_dict(state["model_state"])
    else:
        model.load_state_dict(state)
    model.eval()
    return model


def _run_inference(model_path, frame_rgb):
    """Run TinyUNet on a single RGB frame; return blended overlay (numpy RGB) or None."""
    try:
        import torch
        import numpy as np
        import cv2

        model = _load_unet_model(str(model_path))

        # Preprocess: match training pipeline (grayscale, resize to 256, normalize)
        gray = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2GRAY)
        orig_h, orig_w = gray.shape[:2]
        resized = cv2.resize(gray, (256, 256), interpolation=cv2.INTER_AREA)
        x = resized.astype(np.float32) / 255.0
        x = torch.from_numpy(x).unsqueeze(0).unsqueeze(0)  # (1, 1, 256, 256)

        with torch.no_grad():
            logits = model(x)  # (1, 3, 256, 256)
        pred = logits.squeeze(0).argmax(0).numpy().astype(np.uint8)  # (256, 256)

        # Resize prediction back to original frame size
        pred_full = cv2.resize(pred, (orig_w, orig_h), interpolation=cv2.INTER_NEAREST)
        return blend_mask_overlay(frame_rgb, pred_full)
    except Exception as e:
        return None


# ---------------------------------------------------------------------------
# Main render function
# ---------------------------------------------------------------------------


def render_ezm_ml(con: sqlite3.Connection, *, workspace_root: Optional[str], db_path: Path) -> None:
    st.header("EZM U-Net: Open/Closed Segmentation")
    if not workspace_root:
        st.error("This view requires `--workspace-root`.")
        st.stop()

    ensure_ml_tables(con)

    repo_root = Path(__file__).resolve().parents[4]
    project_path = Path(db_path).parent
    ws_root = Path(str(workspace_root)).expanduser().resolve()

    def _utc_now_iso() -> str:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    def _upsert_run_status(run_dir: Path, patch: Dict[str, Any]) -> None:
        status_path = run_dir / "run_status.json"
        cur: Dict[str, Any] = {}
        try:
            cur = json.loads(status_path.read_text())
        except Exception:
            cur = {}
        cur.update(patch)
        status_path.write_text(json.dumps(cur, indent=2, sort_keys=True) + "\n")

    def _create_project_run(kind: str, name: str) -> Optional[Dict[str, Any]]:
        env = dict(os.environ)
        src_path = str((repo_root / "src").resolve())
        py_path = str(env.get("PYTHONPATH") or "").strip()
        env["PYTHONPATH"] = src_path if not py_path else f"{src_path}:{py_path}"
        cmd = [sys.executable, "-m", "mus1.core.simple_cli", "runs", "new", kind, "--project-path", str(project_path), "--name", name, "--json"]
        r = subprocess.run(cmd, check=False, capture_output=True, text=True, env=env)
        if r.returncode != 0:
            st.error("Could not create MUS1 run record.")
            st.code((r.stderr or r.stdout or "").strip() or "(no output)", language=None)
            return None
        try:
            payload = json.loads((r.stdout or "").strip())
        except Exception:
            st.error("Run creation output was not valid JSON.")
            return None
        if not isinstance(payload, dict) or not payload.get("run_dir") or not payload.get("run_id"):
            st.error("Run creation output missing run_dir/run_id.")
            return None
        return payload

    # ======================================================================
    # SECTION 1: Cohort Overview
    # ======================================================================
    st.subheader("Cohort Overview")
    cohort_name = "ezm_publication"
    try:
        split = _load_train_val_split(cohort_name)
    except Exception as e:
        st.error(f"Could not load cohort: {e}")
        st.stop()

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Training", f"{len(split['train'])} experiments")
    with col2:
        st.metric("Validation", f"{len(split['val'])} experiments")
    with col3:
        st.metric("Skipped", f"{len(split['skipped'])}")

    st.caption(f"Cohort: `{cohort_name}` — Training = publication members, Validation = excluded experiments with QC-approved wedge points")

    with st.expander("Training set details", expanded=False):
        import pandas as pd
        train_df = pd.DataFrame([{"experiment_id": s["experiment_id"]} for s in split["train"]])
        st.dataframe(train_df, hide_index=True, use_container_width=True)

    with st.expander("Validation set details", expanded=False):
        val_df = pd.DataFrame([
            {"experiment_id": s["experiment_id"], "video_exists": Path(s["video_path"]).exists()}
            for s in split["val"]
        ])
        st.dataframe(val_df, hide_index=True, use_container_width=True)
        if split["skipped"]:
            st.caption("Skipped experiments:")
            st.dataframe(pd.DataFrame(split["skipped"]), hide_index=True, use_container_width=True)

    # ======================================================================
    # SECTION 2: Inference Preview on Validation Set
    # ======================================================================
    show_val_inference = st.checkbox("Validation set inference preview", value=True)
    if show_val_inference and split["val"]:
        st.subheader("Validation Inference Preview")

        val_ids = [s["experiment_id"] for s in split["val"]]
        chosen_val = st.selectbox("Validation experiment", options=val_ids, index=0, key="ezm_ml_val_exp")
        val_src = next(s for s in split["val"] if s["experiment_id"] == chosen_val)

        frame_idx = st.number_input("Frame index", min_value=0, value=1200, step=300, key="ezm_ml_val_frame")

        frame_rgb = _load_frame_rgb(val_src["video_path"], int(frame_idx))
        if frame_rgb is None:
            st.error(f"Could not read frame {frame_idx} from {val_src['video_path']}")
        else:
            gt_mask = _make_mask_from_payload(val_src["zone_payload"], out_hw=frame_rgb.shape[:2])
            gt_overlay = blend_mask_overlay(frame_rgb, gt_mask)

            # Check for active model
            active_model_path = repo_root.parents[1] / "ml_workspace" / "ezm_arena_unet" / "active_model" / "model_best.pt"
            has_model = active_model_path.exists()

            if has_model:
                st.caption("Showing GT mask (left) vs model prediction (right)")
                pred_overlay = _run_inference(active_model_path, frame_rgb)
                cols = st.columns(2)
                with cols[0]:
                    st.image(gt_overlay, caption=f"GT mask — {chosen_val} frame={frame_idx}")
                with cols[1]:
                    if pred_overlay is not None:
                        st.image(pred_overlay, caption=f"Model prediction — {chosen_val} frame={frame_idx}")
                    else:
                        st.warning("Inference failed — check that model weights are compatible.")
            else:
                st.caption("No active model found — showing GT mask only. Train a model first.")
                st.image(gt_overlay, caption=f"GT mask — {chosen_val} frame={frame_idx}")

    # ======================================================================
    # SECTION 3: Training Set Mask Preview
    # ======================================================================
    show_train_preview = st.checkbox("Training set mask preview", value=False)
    if show_train_preview and split["train"]:
        st.subheader("Training Set Mask Preview")

        train_ids = [s["experiment_id"] for s in split["train"]]
        chosen_train = st.selectbox("Training experiment", options=train_ids, index=0, key="ezm_ml_train_exp")
        train_src = next(s for s in split["train"] if s["experiment_id"] == chosen_train)

        frame_idx_train = st.number_input("Frame index", min_value=0, value=1200, step=300, key="ezm_ml_train_frame")
        mask_mode = st.selectbox("Mask mode", options=["full (derived)", "safe_bg (weak label)"], index=0, key="ezm_ml_mask_mode")

        frame_rgb = _load_frame_rgb(train_src["video_path"], int(frame_idx_train))
        if frame_rgb is None:
            st.error(f"Could not read frame from {train_src['video_path']}")
        else:
            if "safe_bg" in mask_mode:
                mask = _safe_bg_mask_from_payload(train_src["zone_payload"], out_hw=frame_rgb.shape[:2])
            else:
                mask = _make_mask_from_payload(train_src["zone_payload"], out_hw=frame_rgb.shape[:2])
            overlay = blend_mask_overlay(frame_rgb, mask)

            cols = st.columns(2)
            with cols[0]:
                st.image(frame_rgb, caption=f"Raw frame — {chosen_train} frame={frame_idx_train}")
            with cols[1]:
                st.image(overlay, caption=f"Mask overlay ({mask_mode})")

            import numpy as np
            st.caption(f"Mask pixels: open={(mask == 1).sum()}, closed={(mask == 2).sum()}, bg={(mask == 0).sum()}, ignore={(mask == 255).sum()}")

    # ======================================================================
    # SECTION 4: Retrain Submission
    # ======================================================================
    show_retrain = st.checkbox("Retrain (Slurm)", value=False)
    if show_retrain:
        st.subheader("Submit Training Job")

        slurm_script = repo_root / "workspace" / "dlc_ezm_open_closed" / "torch_ml" / "run_train_unet_from_cohort.slurm"
        st.caption(f"Script: `{slurm_script}`")
        if not slurm_script.exists():
            st.warning("Slurm script not found.")
            st.stop()

        part = ""
        try:
            for line in slurm_script.read_text().splitlines():
                if line.startswith("#SBATCH --partition="):
                    part = line.split("=", 1)[1].strip()
                    break
        except Exception:
            pass
        if part:
            st.caption(f"Partition: `{part}`")

        check = st.button("Check for idle nodes", key="ezm_ml_check_idle")
        idle_ok = False
        if check:
            try:
                r = subprocess.run(["sinfo", "-h", "-t", "idle,mix", "-o", "%P %D %N"], check=False, capture_output=True, text=True)
                out = (r.stdout or "").strip()
                st.code(out or "(no output)")
                if part:
                    idle_ok = any(line.strip().startswith(part) for line in out.splitlines())
                else:
                    idle_ok = bool(out)
            except Exception as e:
                st.error(f"sinfo failed: {e}")

        submit = st.button("Submit retrain job", key="ezm_ml_submit", disabled=not check)
        if submit:
            if part and not idle_ok:
                st.error(f"No idle/mix nodes for partition `{part}`.")
                st.stop()
            run_payload = _create_project_run("ezm_unet", "retrain_cohort")
            if run_payload is None:
                st.stop()
            submit_run_dir = Path(str(run_payload.get("run_dir")))
            submit_run_id = str(run_payload.get("run_id"))
            st.caption(f"Run: `{submit_run_id}` → `{submit_run_dir}`")
            _upsert_run_status(submit_run_dir, {
                "state": "submitting",
                "submitted_at": _utc_now_iso(),
                "cohort": cohort_name,
            })
            try:
                export_vars = ",".join([
                    "ALL",
                    f"MUS1_RUN_DIR={str(submit_run_dir)}",
                    f"EZM_UNET_COHORT={cohort_name}",
                ])
                r = subprocess.run(
                    ["sbatch", "--export", export_vars, str(slurm_script)],
                    check=False, capture_output=True, text=True,
                )
                if r.returncode != 0:
                    _upsert_run_status(submit_run_dir, {"state": "submit_failed", "submit_error": (r.stderr or r.stdout or "").strip()})
                    st.error(r.stderr or r.stdout or "sbatch failed.")
                else:
                    msg = (r.stdout or "").strip()
                    st.success(msg or "Submitted.")
                    jobid = msg.split()[-1] if msg else ""
                    _upsert_run_status(submit_run_dir, {"state": "submitted", "job_id": jobid, "submitted_at": _utc_now_iso()})
                    if jobid.isdigit():
                        st.code(f"squeue -j {jobid}\nsacct -j {jobid} --format=JobID,State,Elapsed,MaxRSS")
            except Exception as e:
                _upsert_run_status(submit_run_dir, {"state": "submit_failed", "submit_error": str(e)})
                st.error(f"sbatch failed: {e}")

    # ======================================================================
    # SECTION 5: Post-Training QC (worst frames from existing runs)
    # ======================================================================
    show_qc = st.checkbox("Post-training QC (worst frames)", value=False)
    if show_qc:
        st.subheader("Post-Training QC")

        runs_db = list_ezm_unet_runs_from_db(str(db_path))
        if not runs_db:
            st.info("No EZM U-Net runs indexed in DB.")
            st.stop()

        run_labels = [f"{r['name']}  ({r['run_path']})" for r in runs_db]
        run_choice = st.selectbox("Select run", options=run_labels, index=0, key="ezm_ml_qc_run")
        run = next(r for r in runs_db if f"{r['name']}  ({r['run_path']})" == run_choice)
        run_dir = Path(str(run["run_path"]))
        st.caption(f"Run dir: `{run_dir}`")

        # Show manifest if available
        manifest_path = run_dir / "training_manifest.json"
        if manifest_path.exists():
            with st.expander("Training manifest", expanded=False):
                manifest = json.loads(manifest_path.read_text())
                st.json(manifest)

        worst_csv = run_dir / "labeled_eval" / "worst_frames.csv"
        if not worst_csv.exists():
            st.warning("No `labeled_eval/worst_frames.csv` in this run.")
        else:
            n = int(st.number_input("N worst", min_value=1, max_value=100, value=5, step=1, key="ezm_ml_qc_n"))
            worst_rows = read_csv_rows(worst_csv, limit=max(200, n))

            def _as_float(v):
                try:
                    return float(v)
                except Exception:
                    return float("nan")

            worst_rows.sort(key=lambda r: _as_float(r.get("miou_open_closed")), reverse=False)
            worst_rows = worst_rows[:n]
            st.dataframe(worst_rows, use_container_width=True, hide_index=True)

            if worst_rows:
                nav_sig = (str(run_dir), n)
                if st.session_state.get("ezm_ml_nav_sig") != nav_sig:
                    st.session_state["ezm_ml_nav_sig"] = nav_sig
                    st.session_state["ezm_ml_idx"] = 0
                cur_idx = int(st.session_state.get("ezm_ml_idx", 0))
                cur_idx = max(0, min(cur_idx, len(worst_rows) - 1))

                c1, c2, c3 = st.columns([1, 1, 3])
                with c1:
                    if st.button("Prev", disabled=cur_idx <= 0, key="ezm_ml_prev"):
                        cur_idx -= 1
                with c2:
                    if st.button("Next", disabled=cur_idx >= len(worst_rows) - 1, key="ezm_ml_next"):
                        cur_idx += 1
                with c3:
                    st.write(f"Item {cur_idx + 1} / {len(worst_rows)}")
                st.session_state["ezm_ml_idx"] = cur_idx

                row = worst_rows[cur_idx]
                overlay_path = Path(str(row.get("overlay_path") or "")).expanduser()
                if not overlay_path.is_absolute():
                    overlay_path = (ws_root / overlay_path).resolve()

                st.caption(f"video: `{row.get('video_path')}`  frame: `{row.get('frame_idx')}`  miou: `{row.get('miou_open_closed')}`")
                if overlay_path.exists():
                    st.image(str(overlay_path), use_container_width=True)
                else:
                    st.error(f"Overlay not found: {overlay_path}")

                if st.button("Queue frame for retraining", key="ezm_ml_queue"):
                    con.execute("BEGIN")
                    con.execute(
                        """
                        INSERT INTO ml_training_frame_queue (kind, run_path, video_path, frame_idx, overlay_path, zone_json, score, status)
                        VALUES (?, ?, ?, ?, ?, ?, ?, 'queued')
                        ON CONFLICT(kind, run_path, video_path, frame_idx) DO UPDATE SET score=excluded.score, status='queued'
                        """,
                        (
                            "ezm_unet_open_closed", str(run_dir),
                            str(row.get("video_path") or ""), int(float(row.get("frame_idx") or 0)),
                            str(overlay_path), str(row.get("zone_json") or ""),
                            _as_float(row.get("miou_open_closed")),
                        ),
                    )
                    con.commit()
                    st.success("Queued.")
