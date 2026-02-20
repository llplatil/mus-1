from __future__ import annotations

import json
import math
import os
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import streamlit as st

from ..db import fetchall
from ..io import parse_meta, read_csv_rows
from ..ezm_masks import blend_mask_overlay, make_ezm_open_closed_mask
from ..ml_tables import ensure_ml_tables


@st.cache_data(show_spinner=False)
def list_ezm_unet_runs_from_db(db_path: str) -> List[Dict[str, Any]]:
    """
    List indexed EZM U-Net training runs from the MUS1 DB.

    Runs are stored as external_artifacts with kind='ezm_unet_run_dir' by the CLI importer:
      mus1 import ezm-unet-runs --project-path ... --workspace-root ...
    """
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
        out.append(
            {
                "run_path": str(p),
                "name": p.name,
                "created_at": str(r["created_at"]),
                "indexed_meta": meta,
            }
        )
    return out


def render_ezm_ml(con: sqlite3.Connection, *, workspace_root: Optional[str], db_path: Path) -> None:
    st.header("EZM → open/closed U-Net (active review)")
    if not workspace_root:
        st.error("This view requires `--workspace-root` so we can find training runs.")
        st.stop()

    ensure_ml_tables(con)

    ws_root = Path(str(workspace_root)).expanduser().resolve()
    repo_root = Path(__file__).resolve().parents[4]
    project_path = Path(db_path).parent

    def _utc_now_iso() -> str:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    def _upsert_run_status(run_dir: Path, patch: Dict[str, Any]) -> None:
        status_path = run_dir / "run_status.json"
        cur: Dict[str, Any] = {}
        try:
            cur_obj = json.loads(status_path.read_text())
            if isinstance(cur_obj, dict):
                cur = cur_obj
        except Exception:
            cur = {}
        cur.update(patch)
        status_path.write_text(json.dumps(cur, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def _create_project_run(kind: str, name: str) -> Optional[Dict[str, Any]]:
        env = dict(os.environ)
        src_path = str((repo_root / "src").resolve())
        py_path = str(env.get("PYTHONPATH") or "").strip()
        env["PYTHONPATH"] = src_path if not py_path else f"{src_path}:{py_path}"
        cmd = [
            sys.executable,
            "-m",
            "mus1.core.simple_cli",
            "runs",
            "new",
            kind,
            "--project-path",
            str(project_path),
            "--name",
            name,
            "--json",
        ]
        r = subprocess.run(cmd, check=False, capture_output=True, text=True, env=env)
        if r.returncode != 0:
            st.error("Could not create MUS1 run record for retrain submission.")
            st.code((r.stderr or r.stdout or "").strip() or "(no output)", language=None)
            return None
        try:
            payload = json.loads((r.stdout or "").strip())
        except Exception:
            st.error("Run creation output was not valid JSON.")
            st.code((r.stdout or "").strip() or "(no output)", language=None)
            return None
        if not isinstance(payload, dict):
            st.error("Run creation output had unexpected shape.")
            return None
        if not payload.get("run_dir") or not payload.get("run_id"):
            st.error("Run creation output missing run_dir/run_id.")
            st.code(json.dumps(payload, indent=2), language=None)
            return None
        return payload

    def _resolve_video_path(vp: str) -> Path:
        p = Path(str(vp).strip())
        if p.is_absolute():
            return p
        # training_index_from_zones.csv commonly uses workspace-relative video paths like "data/..."
        return (ws_root / p).resolve()

    def _resolve_zone_json_path(zp: str) -> Path:
        p = Path(str(zp).strip())
        if p.is_absolute():
            return p
        # If someone wrote "workspace/arena_zones/..." into a CSV, anchor it at repo root.
        if str(p).startswith("workspace/"):
            return (repo_root / p).resolve()
        return (ws_root / p).resolve()

    st.subheader("Training run")
    runs_db = list_ezm_unet_runs_from_db(str(db_path))
    if runs_db:
        st.caption("Using DB-indexed runs (recommended; avoids manual path pasting).")
        run_labels = [f"{r['name']}  (DB)  {r['run_path']}" for r in runs_db]
        run_choice = st.selectbox("Select run", options=run_labels, index=0)
        run = next(r for r in runs_db if f"{r['name']}  (DB)  {r['run_path']}" == run_choice)
        run_dir = Path(str(run["run_path"]))
    else:
        # Option A: DB is authoritative; no fallback scanning.
        expected = project_path / "runs" / "ezm_unet"
        st.info("No EZM U-Net runs indexed in this project DB yet.")
        st.code(
            "\n".join(
                [
                    "# Index project-scoped runs into the DB",
                    f"mus1 import ezm-unet-runs --project-path \"{project_path}\" --workspace-root \"{workspace_root}\"",
                    "",
                    "# Expected runs root:",
                    str(expected),
                ]
            ),
            language=None,
        )
        st.stop()

    st.caption(f"Run dir: `{run_dir}`")

    # Labeled dataset == zone-derived training index for now.
    st.subheader("Labeled dataset")
    labeled_index = run_dir / "training_index_from_zones.csv"
    if labeled_index.exists():
        st.caption(f"Index: `{labeled_index}`")
        with st.expander("Preview labeled index (first 20 rows)", expanded=False):
            rows = read_csv_rows(labeled_index, limit=20)
            st.dataframe(rows, width="stretch", hide_index=True)

        with st.expander("Dataset inspector (pre-train)", expanded=False):
            # Read more rows for summary (still lightweight).
            all_rows = read_csv_rows(labeled_index, limit=5000)
            if not all_rows:
                st.info("Index is empty.")
            else:
                # Heuristic column detection.
                cols = set().union(*(set(r.keys()) for r in all_rows))
                video_col = "video_path" if "video_path" in cols else ("video" if "video" in cols else "")
                frame_col = "frame_idx" if "frame_idx" in cols else ("frame" if "frame" in cols else "")
                zone_col = "zone_json" if "zone_json" in cols else ("zone_path" if "zone_path" in cols else "")

                st.caption(f"Columns: {', '.join(sorted(list(cols))[:60])}{' …' if len(cols) > 60 else ''}")
                if not video_col:
                    st.warning("Could not find a video path column (expected `video_path`). Showing raw table only.")
                    st.dataframe(all_rows[:200], width="stretch", hide_index=True)
                else:
                    # Build per-video counts and missingness.
                    by_video: Dict[str, List[Dict[str, Any]]] = {}
                    missing_videos = 0
                    missing_zones = 0
                    for r in all_rows:
                        vp = str(r.get(video_col) or "").strip()
                        if not vp:
                            continue
                        by_video.setdefault(vp, []).append(r)
                    for vp, rs in by_video.items():
                        if not _resolve_video_path(vp).exists():
                            missing_videos += 1
                        if zone_col:
                            z = str(rs[0].get(zone_col) or "").strip()
                            if z and not _resolve_zone_json_path(z).exists():
                                missing_zones += 1

                    st.write(
                        {
                            "rows_loaded": len(all_rows),
                            "unique_videos": len(by_video),
                            "videos_missing_on_disk": int(missing_videos),
                            "zone_json_missing_on_disk": int(missing_zones),
                        }
                    )

                    preview_rows = []
                    for vp, rs in list(by_video.items())[:300]:
                        z0 = (str(rs[0].get(zone_col) or "") if zone_col else "")
                        vp_abs = _resolve_video_path(vp)
                        z_abs = _resolve_zone_json_path(z0) if z0 else None
                        preview_rows.append(
                            {
                                "video_path": vp,
                                "n_frames_listed": len(rs),
                                "video_exists": vp_abs.exists(),
                                "video_abs": str(vp_abs),
                                "zone_json": z0,
                                "zone_exists": (z_abs.exists() if z_abs else None),
                                "zone_abs": (str(z_abs) if z_abs else ""),
                            }
                        )
                    st.dataframe(preview_rows, width="stretch", hide_index=True)

                    st.markdown("#### Quick preview (frame + zone overlay when available)")
                    vp_list = list(by_video.keys())
                    chosen_vp = st.selectbox("Video", options=vp_list, index=0)
                    rows_for_vp = by_video.get(str(chosen_vp), [])

                    # Pick a few candidate frames.
                    frame_opts: List[int] = []
                    if frame_col:
                        for rr in rows_for_vp[:2000]:
                            try:
                                frame_opts.append(int(float(rr.get(frame_col) or 0)))
                            except Exception:
                                continue
                    frame_opts = sorted(set(frame_opts)) or [0]
                    chosen_frame = st.selectbox("Frame idx", options=frame_opts[:500], index=0)

                    zone_path = str(rows_for_vp[0].get(zone_col) or "").strip() if zone_col and rows_for_vp else ""
                    vp_abs = _resolve_video_path(str(chosen_vp))
                    zone_abs = _resolve_zone_json_path(zone_path) if zone_path else None

                    label_source = st.selectbox(
                        "Mask fit / label source",
                        options=["auto", "derived", "annotations"],
                        index=0,
                        help=(
                            "Controls how GT masks are rasterized from the zone JSON. "
                            "`derived` uses stored outer_ellipse + r_inner + open_angle_ranges. "
                            "`annotations` fits outer/inner ellipses and border rays from saved clicks/lines (requires zone JSON to include them). "
                            "`auto` uses annotations when present, else derived."
                        ),
                        key="mus1_ezm_mask_label_source",
                    )

                    try:
                        import cv2  # type: ignore
                        import numpy as np  # type: ignore
                    except Exception:
                        st.warning("opencv/numpy missing in env; cannot preview frames.")
                        st.stop()

                    cap = cv2.VideoCapture(str(vp_abs))
                    if not cap.isOpened():
                        st.error(f"Could not open video: {vp_abs}")
                        st.stop()
                    cap.set(cv2.CAP_PROP_POS_FRAMES, int(chosen_frame))
                    ok, frame_bgr = cap.read()
                    cap.release()
                    if not ok:
                        st.error(f"Could not read frame {chosen_frame}")
                        st.stop()
                    frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)

                    # If zone json exists, draw minimal overlay: outer ellipse + inner ellipse + 4 boundary rays.
                    if zone_abs is not None and zone_abs.exists():
                        try:
                            payload = json.loads(Path(zone_abs).read_text())
                        except Exception:
                            payload = {}
                        try:
                            outer = payload.get("outer_ellipse") or {}
                            (cx, cy) = outer.get("center") or [None, None]
                            (ax, by) = outer.get("axes") or [None, None]
                            ang = outer.get("angle_deg")
                            r_inner = float(payload.get("r_inner") or 0.0)
                            b_angles = payload.get("boundary_angles") or []
                            if cx is not None and cy is not None and ax is not None and by is not None and ang is not None:
                                cv2.ellipse(
                                    frame_rgb,
                                    (int(round(cx)), int(round(cy))),
                                    (int(round(float(ax) / 2.0)), int(round(float(by) / 2.0))),
                                    float(ang),
                                    0.0,
                                    360.0,
                                    (0, 255, 255),
                                    2,
                                )
                                if r_inner and r_inner > 0:
                                    cv2.ellipse(
                                        frame_rgb,
                                        (int(round(cx)), int(round(cy))),
                                        (int(round((float(ax) / 2.0) * r_inner)), int(round((float(by) / 2.0) * r_inner))),
                                        float(ang),
                                        0.0,
                                        360.0,
                                        (255, 0, 255),
                                        2,
                                    )
                                if isinstance(b_angles, list) and len(b_angles) == 4:
                                    theta = np.array([float(t) for t in b_angles], dtype=float)
                                    ca = math.radians(float(ang))
                                    c = float(math.cos(ca))
                                    s = float(math.sin(ca))
                                    R = np.array([[c, -s], [s, c]], dtype=float)
                                    pts = np.stack([np.cos(theta) * (float(ax) / 2.0), np.sin(theta) * (float(by) / 2.0)], axis=0)
                                    rot = R @ pts
                                    for i in range(rot.shape[1]):
                                        x = float(rot[0, i] + float(cx))
                                        y = float(rot[1, i] + float(cy))
                                        cv2.line(
                                            frame_rgb,
                                            (int(round(cx)), int(round(cy))),
                                            (int(round(x)), int(round(y))),
                                            (255, 255, 255),
                                            2,
                                        )
                        except Exception:
                            pass

                    if zone_abs is not None and zone_abs.exists():
                        st.markdown("#### Rasterized GT mask preview")
                        try:
                            mask = make_ezm_open_closed_mask(
                                Path(zone_abs),
                                out_hw=(int(frame_rgb.shape[0]), int(frame_rgb.shape[1])),
                                label_source=str(label_source),  # type: ignore[arg-type]
                            )
                            overlay = blend_mask_overlay(frame_rgb, mask)
                            cols2 = st.columns(2)
                            with cols2[0]:
                                st.image(frame_rgb, caption=f"frame: {vp_abs.name}  idx={chosen_frame}", width="stretch")
                            with cols2[1]:
                                st.image(overlay, caption=f"GT mask overlay (source={label_source})", width="stretch")
                            st.caption(
                                f"mask pixels: open={(mask == 1).sum()}  closed={(mask == 2).sum()}  bg={(mask == 0).sum()}"
                            )
                        except Exception as e:
                            st.error(f"Could not rasterize GT mask from zone JSON ({label_source}): {e}")
                            st.image(frame_rgb, caption=f"{vp_abs.name} frame={chosen_frame}", width="stretch")
                    else:
                        if zone_path.strip():
                            st.warning(f"Zone JSON not found at: {zone_abs}")
                        st.image(frame_rgb, caption=f"{vp_abs.name} frame={chosen_frame}", width="stretch")
    else:
        st.warning("Missing `training_index_from_zones.csv` in this run dir.")

    st.subheader("Review worst frames")
    n = int(st.number_input("N worst frames", min_value=1, max_value=100, value=5, step=1))

    worst_csv = run_dir / "labeled_eval" / "worst_frames.csv"
    if not worst_csv.exists():
        st.warning(
            "Missing `labeled_eval/worst_frames.csv` for this run. "
            "Run inference to generate it (outside the app) or rerun the inference step for this run."
        )
        st.stop()

    worst_rows = read_csv_rows(worst_csv, limit=max(200, n))

    def _as_float(v: Any) -> float:
        try:
            return float(v)
        except Exception:
            return float("nan")

    worst_rows.sort(key=lambda r: _as_float(r.get("miou_open_closed")), reverse=False)
    worst_rows = worst_rows[:n]

    st.dataframe(worst_rows, width="stretch", hide_index=True)

    if not worst_rows:
        st.stop()

    # Reset navigation index when the selected run or N changes.
    nav_sig = (str(run_dir), int(n))
    if st.session_state.get("ezm_ml_nav_sig") != nav_sig:
        st.session_state["ezm_ml_nav_sig"] = nav_sig
        st.session_state["ezm_ml_idx"] = 0
    if "ezm_ml_idx" not in st.session_state:
        st.session_state["ezm_ml_idx"] = 0
    try:
        cur_idx = int(st.session_state["ezm_ml_idx"])
    except Exception:
        cur_idx = 0
    st.session_state["ezm_ml_idx"] = int(max(0, min(cur_idx, max(0, len(worst_rows) - 1))))

    nav1, nav2, nav3 = st.columns([1, 1, 3])
    with nav1:
        if st.button("Prev", disabled=int(st.session_state["ezm_ml_idx"]) <= 0):
            st.session_state["ezm_ml_idx"] = int(st.session_state["ezm_ml_idx"]) - 1
    with nav2:
        if st.button("Next", disabled=int(st.session_state["ezm_ml_idx"]) >= len(worst_rows) - 1):
            st.session_state["ezm_ml_idx"] = int(st.session_state["ezm_ml_idx"]) + 1
    with nav3:
        st.write(f"Item {int(st.session_state['ezm_ml_idx']) + 1} / {len(worst_rows)}")

    st.session_state["ezm_ml_idx"] = int(max(0, min(int(st.session_state["ezm_ml_idx"]), max(0, len(worst_rows) - 1))))
    row = worst_rows[int(st.session_state["ezm_ml_idx"])]

    overlay_path = Path(str(row.get("overlay_path") or "")).expanduser()
    if not overlay_path.is_absolute():
        overlay_path = (Path(workspace_root) / overlay_path).resolve()

    st.markdown("#### Overlay (GT vs pred)")
    st.caption(f"video: `{row.get('video_path')}`  frame_idx: `{row.get('frame_idx')}`")
    if row.get("zone_json"):
        st.caption(f"zone_json: `{row.get('zone_json')}`")
    st.caption(f"miou_open_closed: `{row.get('miou_open_closed')}`")

    if overlay_path.exists():
        st.image(str(overlay_path), width="stretch")
    else:
        st.error(f"Overlay image not found: {overlay_path}")

    st.markdown("#### Label arena markings (recommended workflow)")
    st.caption(
        "Export a QC CSV list and open the embedded annotator in MUS1 (Mode → Annotator). "
        "This path will be fully wired once the annotator embed module is ported into MUS1."
    )

    # Export a QC CSV list the annotator can consume.
    qc_outdir = Path(db_path).parent / "ml_review" / "ezm_unet_open_closed" / str(run_dir.name)
    qc_outdir.mkdir(parents=True, exist_ok=True)
    qc_csv_path = qc_outdir / f"worst_{n}_frames_for_labeling.csv"

    if st.button("Export QC CSV list for arena annotator", key="ezm_ml_export_qc_csv"):
        import csv

        rows_out = []
        for r in worst_rows:
            vp_rel = str(r.get("video_path") or "")
            fi = int(float(r.get("frame_idx") or 0))
            op = str(r.get("overlay_path") or "")

            vp_abs = Path(vp_rel)
            if not vp_abs.is_absolute():
                vp_abs = (Path(workspace_root) / vp_rel).resolve()

            op_abs = Path(op)
            if op_abs and not op_abs.is_absolute():
                op_abs = (Path(workspace_root) / op).resolve()

            rows_out.append(
                {
                    "video_path": str(vp_abs),
                    "frame_idx": fi,
                    "overlay_path": str(op_abs) if op_abs else "",
                    "zone_json": str(r.get("zone_json") or ""),
                    "miou_open_closed": str(r.get("miou_open_closed") or ""),
                }
            )

        with qc_csv_path.open("w", newline="") as f:
            w = csv.DictWriter(
                f,
                fieldnames=["video_path", "frame_idx", "overlay_path", "zone_json", "miou_open_closed"],
            )
            w.writeheader()
            for rr in rows_out:
                w.writerow(rr)

        st.success(f"Wrote: {qc_csv_path}")

    st.code(str(qc_csv_path), language=None)

    st.markdown("#### Add this frame to the next training run")
    st.caption("This adds the frame index to the next training run’s `--frames` list (it does not mean “label 1200 frames”).")

    if st.button("Queue this frame for retraining", key="ezm_ml_queue"):
        con.execute("BEGIN")
        con.execute(
            """
            INSERT INTO ml_training_frame_queue (kind, run_path, video_path, frame_idx, overlay_path, zone_json, score, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'queued')
            ON CONFLICT(kind, run_path, video_path, frame_idx) DO UPDATE SET
              overlay_path=excluded.overlay_path,
              zone_json=excluded.zone_json,
              score=excluded.score,
              status='queued'
            """,
            (
                "ezm_unet_open_closed",
                str(run_dir),
                str(row.get("video_path") or ""),
                int(float(row.get("frame_idx") or 0)),
                str(overlay_path),
                str(row.get("zone_json") or ""),
                _as_float(row.get("miou_open_closed")),
            ),
        )
        con.commit()
        st.success("Queued.")

    queued = fetchall(
        con,
        """
        SELECT video_path, frame_idx, score, zone_json, created_at
        FROM ml_training_frame_queue
        WHERE kind = ? AND run_path = ? AND status = 'queued'
        ORDER BY score ASC, created_at DESC
        LIMIT 200
        """,
        ("ezm_unet_open_closed", str(run_dir)),
    )
    with st.expander(f"Queued frames for this run ({len(queued)})", expanded=False):
        st.dataframe([dict(r) for r in queued], width="stretch", hide_index=True)

    st.subheader("Retrain (Slurm)")
    repo_root = Path(__file__).resolve().parents[4]
    slurm_script = repo_root / "workspace" / "dlc_ezm_open_closed" / "torch_ml" / "run_train_unet_open_closed_from_zones_augfix_sched_and_qc.slurm"
    st.caption(f"Training script: `{slurm_script}`")
    if not slurm_script.exists():
        st.warning("Slurm script not found; cannot submit retrain from the UI.")
        st.stop()

    part = ""
    try:
        for line in slurm_script.read_text().splitlines():
            if line.startswith("#SBATCH --partition="):
                part = line.split("=", 1)[1].strip()
                break
    except Exception:
        part = ""
    if part:
        st.caption(f"Detected partition: `{part}`")

    # Build a frames list for training: default base frames + any queued frames.
    base_frames = []
    try:
        cfg = json.loads((run_dir / "train_config.json").read_text())
        if isinstance(cfg, dict) and isinstance(cfg.get("frames"), list):
            base_frames = [int(x) for x in cfg["frames"]]
    except Exception:
        base_frames = []
    queued_frames = sorted({int(r["frame_idx"]) for r in queued}) if queued else []
    frames_union = sorted(set(base_frames).union(set(queued_frames)))
    frames_str = ",".join(str(x) for x in frames_union) if frames_union else "0,1200,2400"
    st.caption(f"Training frames to use: `{frames_str}`")

    check = st.button("Check for idle nodes", key="ezm_ml_check_idle")
    idle_ok = False
    if check:
        try:
            cmd = ["sinfo", "-h", "-t", "idle,mix", "-o", "%P %D %N"]
            r = subprocess.run(cmd, check=False, capture_output=True, text=True)
            out = (r.stdout or "").strip()
            err = (r.stderr or "").strip()
            if err:
                st.caption(err)
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
            st.error(f"No idle/mix nodes detected for partition `{part}`. Not submitting.")
            st.stop()
        run_payload = _create_project_run("ezm_unet", "retrain_from_ezm_ml")
        if run_payload is None:
            st.stop()
        submit_run_dir = Path(str(run_payload.get("run_dir")))
        submit_run_id = str(run_payload.get("run_id"))
        st.caption(f"MUS1 run: `{submit_run_id}`")
        st.caption(f"MUS1 run dir: `{submit_run_dir}`")
        _upsert_run_status(
            submit_run_dir,
            {
                "state": "submitting",
                "submitted_at": _utc_now_iso(),
                "slurm_script": str(slurm_script),
                "workspace_root": str(ws_root),
                "frames": [int(x) for x in frames_str.split(",") if str(x).strip()],
            },
        )
        try:
            export_vars = ",".join(
                [
                    "ALL",
                    f"EZM_UNET_TRAIN_FRAMES={frames_str}",
                    f"MUS1_RUN_DIR={str(submit_run_dir)}",
                    f"MUS1_RUN_ID={submit_run_id}",
                    f"MOSEQ2_WORKSPACE_ROOT={str(ws_root)}",
                ]
            )
            r = subprocess.run(
                ["sbatch", "--export", export_vars, str(slurm_script)],
                check=False,
                capture_output=True,
                text=True,
            )
            if r.returncode != 0:
                _upsert_run_status(
                    submit_run_dir,
                    {
                        "state": "submit_failed",
                        "submit_failed_at": _utc_now_iso(),
                        "submit_error": (r.stderr or r.stdout or "sbatch failed.").strip(),
                    },
                )
                st.error(r.stderr or r.stdout or "sbatch failed.")
            else:
                msg = (r.stdout or "").strip()
                st.success(msg or "Submitted.")
                jobid = msg.split()[-1] if msg else ""
                if jobid.isdigit():
                    _upsert_run_status(
                        submit_run_dir,
                        {
                            "state": "submitted",
                            "job_id": jobid,
                            "submitted_at": _utc_now_iso(),
                            "submit_stdout": msg,
                        },
                    )
                    st.code(
                        "\n".join(
                            [
                                f"squeue -j {jobid}",
                                f"sacct -j {jobid} --format=JobID,JobName%25,State,Elapsed,MaxRSS,AllocCPUS,NodeList%25",
                            ]
                        )
                    )
                else:
                    _upsert_run_status(
                        submit_run_dir,
                        {
                            "state": "submitted",
                            "submitted_at": _utc_now_iso(),
                            "submit_stdout": msg,
                        },
                    )
        except Exception as e:
            _upsert_run_status(
                submit_run_dir,
                {
                    "state": "submit_failed",
                    "submit_failed_at": _utc_now_iso(),
                    "submit_error": str(e),
                },
            )
            st.error(f"sbatch failed: {e}")

