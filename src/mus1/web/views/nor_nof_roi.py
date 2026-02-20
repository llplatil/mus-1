from __future__ import annotations

import csv
import json
import sqlite3
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

import streamlit as st

from ..db import fetchall
from ..paths import (
    default_nor_nof_outdir,
    find_nor_nof_roi_json,
    normalize_basename,
    path_aliases,
    resolve_dlc_config_path,
    resolve_dlc_project_config_from_id,
    safe_stem_annotator,
)
from ..session_index import read_session_index_rows


def _index_nor_nof_todo_csv(con: sqlite3.Connection, *, qc_csv_path: Path, n_rows: int) -> None:
    kind = "nor_nof_roi_todo_csv"
    path_s = str(qc_csv_path)
    meta = {"rows": int(n_rows), "source": "nor_nof_roi_view"}
    row = con.execute(
        "SELECT id, meta_json FROM external_artifacts WHERE kind = ? AND path = ? ORDER BY id DESC LIMIT 1",
        (kind, path_s),
    ).fetchone()
    if row:
        old_meta = {}
        try:
            old_meta = json.loads(str(row["meta_json"] or "{}"))
        except Exception:
            old_meta = {}
        old_meta.update(meta)
        con.execute("UPDATE external_artifacts SET meta_json = ? WHERE id = ?", (json.dumps(old_meta), int(row["id"])))
    else:
        con.execute(
            "INSERT INTO external_artifacts (kind, path, meta_json) VALUES (?, ?, ?)",
            (kind, path_s, json.dumps(meta)),
        )
    con.commit()


@st.cache_data(show_spinner=False, ttl=30)
def list_dlc_project_ids(db_path: str, workspace_root: str) -> List[str]:
    """
    Best-effort: collect DLC project ids from both the DB and from the
    workspace ``dlc_projects/`` directory on disk.
    """
    ids: set[str] = set()

    # -- source 1: DB artifact paths containing '/dlc_projects/<id>/' --------
    try:
        con = sqlite3.connect(str(db_path))
        con.row_factory = sqlite3.Row
    except Exception:
        con = None
    if con is not None:
        try:
            rows = con.execute(
                "SELECT path FROM external_artifacts WHERE path LIKE '%/dlc_projects/%' AND path IS NOT NULL"
            ).fetchall()
        except Exception:
            rows = []
        finally:
            try:
                con.close()
            except Exception:
                pass
        for r in rows:
            p = str(r["path"] or "")
            if not p:
                continue
            parts = Path(p).parts
            try:
                i = parts.index("dlc_projects")
            except ValueError:
                continue
            if i + 1 < len(parts):
                proj_id = str(parts[i + 1]).strip()
                if proj_id:
                    ids.add(proj_id)

    # -- source 2: workspace disk scan for DLC projects (Stage 2: dlc_workspace/projects first) --------
    if workspace_root:
        ws = Path(str(workspace_root)).expanduser()
        for dlc_root in (
            ws.parent / "dlc_workspace" / "projects",
            ws / "data" / "behavior_videos" / "dlc_projects",
        ):
            if dlc_root.is_dir():
                try:
                    for child in dlc_root.iterdir():
                        if child.is_dir() and (child / "config.yaml").exists():
                            ids.add(child.name)
                except Exception:
                    pass

    return sorted(ids)


def render_nor_nof_roi(
    con: sqlite3.Connection,
    *,
    project_path: Path,
    workspace_root: Optional[str],
    db_path: Path,
) -> None:
    st.header("NOR/NOF ROI annotation (object zones)")
    st.caption("DB-driven task list for ROI JSON marking and indexing.")

    if not workspace_root:
        st.error("This view requires `--workspace-root` so we can read the session index contract.")
        st.stop()

    index_rows = read_session_index_rows(str(workspace_root), tasks=["NOR", "NOF"], require_video_path=True)
    if not index_rows:
        st.warning("No NOR/NOF rows with video_path found in session_index_filtered.csv.")
        st.stop()

    # Which sessions already have ROI JSON linked in the DB?
    try:
        have = fetchall(
            con,
            """
            SELECT DISTINCT experiment_id
            FROM external_artifacts
            WHERE kind = 'nor_nof_objects_json_v2' AND experiment_id IS NOT NULL
            """,
            (),
        )
        have_ids = {str(r["experiment_id"]) for r in have if r["experiment_id"] is not None}
    except Exception:
        have_ids = set()

    repo_root = Path(__file__).resolve().parents[4]
    nor_nof_outdir = default_nor_nof_outdir(repo_root)

    out_rows: List[Dict[str, Any]] = []
    missing_video = 0
    for r in index_rows:
        session_id = str(r.get("session_id", "")).strip()
        task = str(r.get("task", "")).strip().upper()
        vp = str(r.get("video_path", "")).strip()
        exists = bool(vp and Path(vp).exists())
        if not exists:
            missing_video += 1
        roi_json_path = find_nor_nof_roi_json(nor_nof_outdir, vp, session_id) if vp else None
        roi_json_saved = roi_json_path is not None
        out_rows.append(
            {
                "session_id": session_id,
                "task": task,
                "subject_id": str(r.get("subject_id", "")).strip(),
                "recording_date": str(r.get("recording_date", "")).strip(),
                "video_path": vp,
                "video_exists": exists,
                "has_roi_json": bool(session_id and session_id in have_ids),
                "roi_json_saved": roi_json_saved,
                "roi_json_path": str(roi_json_path) if roi_json_path else "",
            }
        )

    st.subheader("Target video set")
    target = st.radio(
        "Focus",
        options=["All NOR/NOF (session index)", "DLC project training set (config.yaml)"],
        horizontal=True,
        key="nor_nof_target_set",
    )

    dlc_basenames: Optional[set[str]] = None
    dlc_crop_by_basename: Dict[str, Any] = {}
    dlc_video_paths: List[str] = []
    if target == "DLC project training set (config.yaml)":
        dlc_project_ids = list_dlc_project_ids(str(db_path), str(workspace_root or ""))
        use_custom = True
        selected_id = ""
        if dlc_project_ids:
            options = ["(custom path)"] + dlc_project_ids
            selected_id = st.selectbox(
                "DLC project (from DB + workspace disk)",
                options=options,
                index=0,
                key="nor_nof_dlc_project_id",
            )
            use_custom = selected_id == "(custom path)"

        if use_custom:
            dlc_input = Path(
                st.text_input(
                    "DLC project directory (contains config.yaml) OR direct config.yaml path",
                    value=str(st.session_state.get("nor_nof_dlc_project_dir") or ""),
                    key="nor_nof_dlc_project_dir",
                )
            ).expanduser()
        else:
            cfg_guess = resolve_dlc_project_config_from_id(workspace_root, str(selected_id))
            st.caption(f"Using DB-derived DLC project id: `{selected_id}`")
            if cfg_guess:
                st.code(str(cfg_guess), language=None)
                dlc_input = Path(str(cfg_guess)).expanduser()
            else:
                st.error(f"Could not resolve config.yaml for DLC project id: `{selected_id}`")
                st.stop()

        cfg = resolve_dlc_config_path(dlc_input)
        if not cfg:
            st.error(f"Could not find `config.yaml` at: `{dlc_input}`")
            st.stop()
        try:
            import yaml  # PyYAML

            payload = yaml.safe_load(cfg.read_text()) or {}
            video_sets = payload.get("video_sets") if isinstance(payload, dict) else None
            if not isinstance(video_sets, dict) or not video_sets:
                raise ValueError("config.yaml missing/invalid `video_sets`")
            dlc_video_paths = [str(p).strip() for p in video_sets.keys() if str(p).strip()]
            dlc_basenames = {normalize_basename(Path(str(p)).name) for p in dlc_video_paths}
            # Optional per-video crop (x1,x2,y1,y2) when present.
            for pth, meta in video_sets.items():
                bn = normalize_basename(Path(str(pth)).name)
                if not isinstance(meta, dict):
                    continue
                crop_raw = (meta.get("crop") or "").strip() if isinstance(meta.get("crop"), str) else meta.get("crop")
                if not crop_raw:
                    continue
                if isinstance(crop_raw, str):
                    parts = [x.strip() for x in crop_raw.split(",")]
                elif isinstance(crop_raw, (list, tuple)):
                    parts = [str(x).strip() for x in crop_raw]
                else:
                    parts = []
                if len(parts) == 4:
                    try:
                        x1, x2, y1, y2 = [int(float(x)) for x in parts]
                        dlc_crop_by_basename[bn] = (x1, x2, y1, y2)
                    except Exception:
                        pass
        except Exception as e:
            st.error(f"Failed to parse DLC config.yaml: {e}")
            st.stop()
        st.caption(f"DLC project id: `{cfg.parent.name}`")
        st.caption(f"DLC videos in config.yaml: {len(dlc_basenames)}")

    st.caption(f"Default NOR/NOF ROI output dir: `{nor_nof_outdir}`")
    count_saved = sum(1 for x in out_rows if x.get("roi_json_saved"))
    st.caption(f"Saved NOR/NOF ROI JSONs on disk (in that dir): {count_saved} / {len(out_rows)}")

    shown = out_rows
    if dlc_basenames is not None:
        # DLC mode: build the list directly from config.yaml so it is EXACTLY the training set.
        # Then best-effort join to session_index for session_id/subject_id/recording_date.
        def _infer_task_from_path(vp: str) -> str:
            s = str(vp).upper()
            if "/NOF/" in s or "\\NOF\\" in s:
                return "NOF"
            if "/NOR/" in s or "\\NOR\\" in s:
                return "NOR"
            name = Path(str(vp)).name.upper()
            if "FAM" in name:
                return "NOF"
            if "REC" in name or "NOV" in name:
                return "NOR"
            return ""

        by_vp: Dict[str, Dict[str, Any]] = {}
        by_key: Dict[Any, Dict[str, Any]] = {}
        for rr in out_rows:
            vp = str(rr.get("video_path") or "").strip()
            if not vp:
                continue
            for alias in path_aliases(Path(vp)):
                by_vp[alias] = rr
            task = str(rr.get("task") or "").strip().upper()
            bn = normalize_basename(Path(vp).name)
            if task and bn:
                by_key[(task, bn)] = rr

        dlc_rows: List[Dict[str, Any]] = []
        for vp in dlc_video_paths:
            hit = None
            for alias in path_aliases(Path(vp)):
                hit = by_vp.get(alias)
                if hit:
                    break
            if not hit:
                task_guess = _infer_task_from_path(vp)
                bn = normalize_basename(Path(vp).name)
                if task_guess and bn:
                    hit = by_key.get((task_guess, bn))

            session_id = str(hit.get("session_id") or "").strip() if hit else ""
            task = str(hit.get("task") or _infer_task_from_path(vp) or "").strip().upper() if hit else _infer_task_from_path(vp)
            bn = normalize_basename(Path(vp).name)
            crop = dlc_crop_by_basename.get(bn)
            roi_json_path = find_nor_nof_roi_json(nor_nof_outdir, vp, session_id)
            roi_json_saved = roi_json_path is not None

            dlc_rows.append(
                {
                    "session_id": session_id,
                    "task": str(task or ""),
                    "subject_id": str(hit.get("subject_id") or "").strip() if hit else "",
                    "recording_date": str(hit.get("recording_date") or "").strip() if hit else "",
                    "video_path": vp,
                    "video_exists": Path(vp).exists(),
                    "has_roi_json": bool(session_id and session_id in have_ids),
                    "roi_json_saved": roi_json_saved,
                    "roi_json_path": str(roi_json_path or ""),
                    "crop_xyxy": list(crop) if crop else [],
                }
            )

        st.caption(f"DLC videos in training set: {len(dlc_rows)}")
        shown = dlc_rows

        treat_saved_done = st.checkbox("Treat saved JSONs on disk as done (even if not indexed yet)", value=True)
        only_missing = st.checkbox("Only sessions missing ROI", value=True)
        show_missing_videos = st.checkbox("Show rows with missing video files", value=True)

        if only_missing:
            if treat_saved_done:
                shown = [x for x in shown if (not x["has_roi_json"]) and (not x["roi_json_saved"])]
            else:
                shown = [x for x in shown if not x["has_roi_json"]]
        if not show_missing_videos:
            shown = [x for x in shown if x["video_exists"]]
    else:
        treat_saved_done = st.checkbox("Treat saved JSONs on disk as done (even if not indexed yet)", value=True)
        only_missing = st.checkbox("Only sessions missing ROI", value=True)
        show_missing_videos = st.checkbox("Show rows with missing video files", value=False)

        if only_missing:
            if treat_saved_done:
                shown = [x for x in shown if (not x["has_roi_json"]) and (not x["roi_json_saved"])]
            else:
                shown = [x for x in shown if not x["has_roi_json"]]
        if not show_missing_videos:
            shown = [x for x in shown if x["video_exists"]]

    st.caption(f"Sessions in index (NOR/NOF): {len(out_rows)}")
    st.caption(f"Already indexed ROI JSONs in DB: {len(have_ids)}")
    if missing_video:
        st.caption(f"Missing video files on disk (by path): {missing_video}")
    st.caption(f"Shown: {len(shown)}")

    st.dataframe(shown, width="stretch", hide_index=True)

    st.subheader("Annotator handoff")
    st.caption("Export a QC CSV list that the arena annotator can iterate (Video source → QC CSV list).")

    export_n = int(st.number_input("Export first N shown sessions (0 = all)", min_value=0, max_value=5000, value=200, step=50))
    export_rows = shown[:export_n] if export_n > 0 else shown

    qc_outdir = project_path / "ml_review" / "nor_nof_roi"
    qc_outdir.mkdir(parents=True, exist_ok=True)
    qc_csv_path = qc_outdir / "nor_nof_roi_todo.csv"

    if st.button("Write QC CSV list for NOR/NOF annotator", key="nor_nof_write_qc_csv"):
        with qc_csv_path.open("w", newline="") as f:
            w = csv.DictWriter(
                f,
                fieldnames=["video_path", "frame_idx", "task", "session_id", "subject_id", "recording_date", "crop_xyxy"],
            )
            w.writeheader()
            for rr in export_rows:
                w.writerow(
                    {
                        "video_path": str(rr.get("video_path") or ""),
                        "frame_idx": 0,
                        "task": str(rr.get("task") or ""),
                        "session_id": str(rr.get("session_id") or ""),
                        "subject_id": str(rr.get("subject_id") or ""),
                        "recording_date": str(rr.get("recording_date") or ""),
                        "crop_xyxy": ",".join(str(x) for x in (rr.get("crop_xyxy") or [])),
                    }
                )
        try:
            _index_nor_nof_todo_csv(con, qc_csv_path=qc_csv_path, n_rows=len(export_rows))
        except Exception as e:
            st.warning(f"Wrote CSV but DB index update failed: {e}")
        st.success(f"Wrote: {qc_csv_path}")

    st.code(str(qc_csv_path), language=None)
    st.markdown("In the annotator: **Mode → `NOR/NOF: annotate arena + objects`** and **Video source → `QC CSV list`**.")

    open_in_app = st.button("Open annotator (NOR/NOF) in this app", key="nor_nof_open_annotator_in_app")
    if open_in_app:
        # Jump to the first unmarked entry based on whether JSON exists on disk.
        start_idx = 0
        for i, rr in enumerate(export_rows):
            if not rr.get("roi_json_saved"):
                start_idx = int(i)
                break
        st.session_state["mus1_nor_nof_start_idx"] = int(start_idx)
        st.session_state["mus1_nor_nof_qc_csv"] = str(qc_csv_path)
        st.session_state["mus1_nor_nof_video_source"] = "QC CSV list"
        st.session_state["mus1_annotator_mode"] = "NOR/NOF: annotate arena + objects"
        st.session_state["mus1_view_mode_next"] = "Annotator"
        st.rerun()

    st.subheader("Index saved ROI JSONs into the DB (refresh)")
    st.caption("After saving JSONs, index them into mus1.db so this view updates.")
    if st.button("Run: mus1 import arena-zones", key="nor_nof_index_arena_zones"):
        try:
            cmd = [
                "mus1",
                "import",
                "arena-zones",
                "--project-path",
                str(project_path),
                "--workspace-root",
                str(Path(str(workspace_root))),
            ]
            r = subprocess.run(cmd, check=False, capture_output=True, text=True)
            st.code((r.stdout or "").strip() or "(no stdout)", language=None)
            if r.returncode != 0:
                st.error((r.stderr or "").strip() or f"Command failed with exit code {r.returncode}")
            else:
                st.success("Index complete. Refreshing…")
                st.cache_data.clear()
                st.rerun()
        except Exception as e:
            st.error(f"Failed to run indexer: {e}")

