"""
MUS1 experiment browser (Streamlit).

Intent:
- DB-first, provenance-first browsing for MoSeq2 workspace imports.
- Show experiments, linked artifacts (including arena annotation JSONs), and QC events.

This app deliberately queries SQLite directly (no GUI/Qt dependencies).
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import streamlit as st


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("--project-path", default=None)
    p.add_argument("--workspace-root", default=None)
    # Streamlit adds its own flags; ignore unknown.
    args, _ = p.parse_known_args()
    return args


@dataclass(frozen=True)
class ExperimentRow:
    experiment_id: str
    experiment_type: str
    date_recorded: str
    processing_stage: str
    subject_id: str
    sex: str
    genotype: Optional[str]
    treatment: Optional[str]
    artifacts_count: int
    qc_count: int
    has_ezm_zone: bool
    has_nor_nof_roi: bool


def _connect(db_path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    return con


def _ensure_ml_tables(con: sqlite3.Connection) -> None:
    """
    Lightweight DB-first tables used by the Streamlit app.

    We keep these in SQLite directly (no ORM) so the web UI can evolve quickly
    without entangling core MUS1 schema/migrations.
    """
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS ml_frame_reviews (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          kind TEXT NOT NULL,
          run_path TEXT NOT NULL,
          video_path TEXT NOT NULL,
          frame_idx INTEGER,
          overlay_path TEXT,
          zone_json TEXT,
          metric REAL,
          label TEXT,
          notes TEXT,
          created_at TEXT NOT NULL DEFAULT (datetime('now')),
          updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    con.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_ml_frame_reviews_unique
        ON ml_frame_reviews(kind, run_path, video_path, frame_idx, overlay_path)
        """
    )
    con.commit()


def _one_col(con: sqlite3.Connection, sql: str, params: Tuple[Any, ...] = ()) -> List[str]:
    cur = con.execute(sql, params)
    return [str(r[0]) for r in cur.fetchall()]


def _fetchall(con: sqlite3.Connection, sql: str, params: Tuple[Any, ...] = ()) -> List[sqlite3.Row]:
    cur = con.execute(sql, params)
    return list(cur.fetchall())


def _parse_meta(meta_json: Optional[str]) -> Dict[str, Any]:
    if not meta_json:
        return {}
    try:
        return json.loads(meta_json)
    except Exception:
        return {"_raw": meta_json}


def _list_experiments(
    con: sqlite3.Connection,
    *,
    experiment_types: Optional[List[str]] = None,
    only_with_ezm_zone: bool = False,
    only_with_nor_nof_roi: bool = False,
) -> List[ExperimentRow]:
    where = []
    params: List[Any] = []

    if experiment_types:
        where.append(f"e.experiment_type IN ({','.join(['?'] * len(experiment_types))})")
        params.extend(experiment_types)

    # We'll compute zone presence via aggregations; filtering happens in HAVING.
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    sql = f"""
    SELECT
      e.id AS experiment_id,
      e.experiment_type AS experiment_type,
      e.date_recorded AS date_recorded,
      e.processing_stage AS processing_stage,
      s.id AS subject_id,
      s.sex AS sex,
      s.individual_genotype AS genotype,
      s.individual_treatment AS treatment,
      COALESCE(a.artifacts_count, 0) AS artifacts_count,
      COALESCE(q.qc_count, 0) AS qc_count,
      COALESCE(z.has_ezm_zone, 0) AS has_ezm_zone,
      COALESCE(z.has_nor_nof_roi, 0) AS has_nor_nof_roi
    FROM experiments e
    JOIN subjects s ON s.id = e.subject_id
    LEFT JOIN (
      SELECT experiment_id, COUNT(*) AS artifacts_count
      FROM external_artifacts
      GROUP BY experiment_id
    ) a ON a.experiment_id = e.id
    LEFT JOIN (
      SELECT experiment_id, COUNT(*) AS qc_count
      FROM qc_events
      GROUP BY experiment_id
    ) q ON q.experiment_id = e.id
    LEFT JOIN (
      SELECT
        experiment_id,
        MAX(CASE WHEN kind = 'ezm_zone_json_v2' THEN 1 ELSE 0 END) AS has_ezm_zone,
        MAX(CASE WHEN kind = 'nor_nof_objects_json_v1' THEN 1 ELSE 0 END) AS has_nor_nof_roi
      FROM external_artifacts
      GROUP BY experiment_id
    ) z ON z.experiment_id = e.id
    {where_sql}
    ORDER BY e.date_recorded DESC
    """

    rows = _fetchall(con, sql, tuple(params))
    out: List[ExperimentRow] = []
    for r in rows:
        row = ExperimentRow(
            experiment_id=str(r["experiment_id"]),
            experiment_type=str(r["experiment_type"]),
            date_recorded=str(r["date_recorded"]),
            processing_stage=str(r["processing_stage"]),
            subject_id=str(r["subject_id"]),
            sex=str(r["sex"]),
            genotype=(str(r["genotype"]) if r["genotype"] is not None else None),
            treatment=(str(r["treatment"]) if r["treatment"] is not None else None),
            artifacts_count=int(r["artifacts_count"]),
            qc_count=int(r["qc_count"]),
            has_ezm_zone=bool(int(r["has_ezm_zone"])),
            has_nor_nof_roi=bool(int(r["has_nor_nof_roi"])),
        )
        if only_with_ezm_zone and not row.has_ezm_zone:
            continue
        if only_with_nor_nof_roi and not row.has_nor_nof_roi:
            continue
        out.append(row)
    return out


def _get_experiment_artifacts(con: sqlite3.Connection, experiment_id: str) -> List[sqlite3.Row]:
    sql = """
    SELECT id, kind, path, meta_json, created_at
    FROM external_artifacts
    WHERE experiment_id = ?
    ORDER BY kind ASC, created_at DESC
    """
    return _fetchall(con, sql, (experiment_id,))


def _get_experiment_qc(con: sqlite3.Connection, experiment_id: str) -> List[sqlite3.Row]:
    sql = """
    SELECT id, scope, code, details_json, created_at
    FROM qc_events
    WHERE experiment_id = ?
    ORDER BY created_at DESC
    """
    return _fetchall(con, sql, (experiment_id,))


def _get_annotation_qc(con: sqlite3.Connection) -> List[sqlite3.Row]:
    """
    Return QC events emitted by arena zone indexing that are not tied to an experiment.
    """
    sql = """
    SELECT id, scope, code, details_json, created_at
    FROM qc_events
    WHERE scope = 'annotation'
    ORDER BY created_at DESC
    """
    return _fetchall(con, sql, ())


def _update_external_artifact_linkage(
    con: sqlite3.Connection,
    *,
    kind: str,
    path: str,
    experiment_id: str,
    subject_id: Optional[str],
    meta_patch: Dict[str, Any],
) -> bool:
    """
    Update linkage for an existing external_artifacts row identified by (kind, path).
    Returns True if an artifact row was found and updated.
    """
    row = con.execute(
        "SELECT id, meta_json FROM external_artifacts WHERE kind = ? AND path = ? ORDER BY id DESC LIMIT 1",
        (kind, path),
    ).fetchone()
    if not row:
        return False

    try:
        current_meta = json.loads(row["meta_json"] or "{}")
        if not isinstance(current_meta, dict):
            current_meta = {}
    except Exception:
        current_meta = {}

    merged_meta = {**current_meta, **(meta_patch or {})}
    con.execute(
        "UPDATE external_artifacts SET experiment_id = ?, subject_id = ?, meta_json = ? WHERE id = ?",
        (experiment_id, subject_id, json.dumps(merged_meta), int(row["id"])),
    )
    return True


def _delete_qc_event(con: sqlite3.Connection, qc_id: int) -> None:
    con.execute("DELETE FROM qc_events WHERE id = ?", (qc_id,))


@st.cache_data(show_spinner=False)
def _load_session_index(workspace_root: str) -> Optional[Dict[Tuple[str, str], Dict[str, Any]]]:
    """
    Load session_index_filtered.csv and build (task, basename) -> row mapping.
    """
    if not workspace_root:
        return None
    try:
        import pandas as pd
    except Exception:
        return None

    ws = Path(workspace_root)
    csv_path = ws / "ml_tracking_metadata_model" / "index" / "session_index_filtered.csv"
    if not csv_path.exists():
        return None
    df = pd.read_csv(csv_path)
    if "video_path" not in df.columns or "task" not in df.columns:
        return None
    vps = df["video_path"].fillna("").astype(str).str.strip()
    df = df.loc[vps.ne("")].copy()
    df["basename"] = df["video_path"].astype(str).apply(lambda s: Path(s).name)
    grouped = df.groupby(["task", "basename"]).size()
    unique_keys = set(k for k, n in grouped.items() if int(n) == 1)
    out: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for _, r in df.iterrows():
        task = str(r.get("task", "")).strip()
        bn = str(r.get("basename", "")).strip()
        key = (task, bn)
        if key not in unique_keys:
            continue
        out[key] = {k: (None if pd.isna(v) else v) for k, v in r.to_dict().items()}
    return out


def _normalize_basename(basename: Optional[str]) -> Optional[str]:
    if not basename:
        return None
    b = str(basename)
    if "DLC_" in b:
        b = b.split("DLC_")[0]
        if not b.endswith(".mp4"):
            b = b + ".mp4"
    return b


@st.cache_data(show_spinner=False)
def _list_ezm_unet_runs(workspace_root: str) -> List[Dict[str, Any]]:
    """
    Discover EZM open/closed U-Net training run directories under the workspace.

    Returns newest-first list with:
      - run_path (absolute)
      - name
      - mtime
      - has_labeled_eval
    """
    if not workspace_root:
        return []
    ws = Path(workspace_root)
    base = ws / "statistics_summaries" / "dlc_ezm_open_closed_ml_unet"
    if not base.exists():
        return []

    runs = []
    for p in base.iterdir():
        if not p.is_dir():
            continue
        if not p.name.startswith("train_"):
            continue
        try:
            st_mtime = p.stat().st_mtime
        except Exception:
            st_mtime = 0.0
        labeled_eval = p / "labeled_eval"
        runs.append(
            {
                "run_path": str(p.resolve()),
                "name": p.name,
                "mtime": float(st_mtime),
                "has_labeled_eval": labeled_eval.exists(),
            }
        )

    runs.sort(key=lambda r: float(r.get("mtime", 0.0)), reverse=True)
    return runs


def _read_csv_rows(path: Path, *, limit: int = 500) -> List[Dict[str, Any]]:
    """
    Small CSV reader for UI tables (keeps deps minimal).
    """
    import csv

    out: List[Dict[str, Any]] = []
    with path.open() as f:
        r = csv.DictReader(f)
        for i, row in enumerate(r):
            if i >= int(limit):
                break
            out.append({k: row.get(k) for k in (row.keys() or [])})
    return out


def _render_ezm_ml(con: sqlite3.Connection, *, workspace_root: Optional[str]) -> None:
    st.header("EZM → open/closed U-Net (active review)")
    if not workspace_root:
        st.error("This view requires `--workspace-root` so we can find training runs.")
        st.stop()

    _ensure_ml_tables(con)

    runs = _list_ezm_unet_runs(str(workspace_root))
    if not runs:
        st.info("No EZM U-Net runs found under `statistics_summaries/dlc_ezm_open_closed_ml_unet/`.")
        st.stop()

    run_labels = [f"{r['name']}" for r in runs]
    default_idx = 0
    run_choice = st.selectbox("Select run", options=run_labels, index=default_idx)
    run = next(r for r in runs if r["name"] == run_choice)
    run_dir = Path(str(run["run_path"]))

    st.caption(f"Run dir: `{run_dir}`")

    # Labeled dataset == zone-derived training index for now.
    st.subheader("Labeled dataset")
    labeled_index = run_dir / "training_index_from_zones.csv"
    if labeled_index.exists():
        st.caption(f"Index: `{labeled_index}`")
        with st.expander("Preview labeled index (first 20 rows)", expanded=False):
            rows = _read_csv_rows(labeled_index, limit=20)
            st.dataframe(rows, width="stretch", hide_index=True)
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

    worst_rows = _read_csv_rows(worst_csv, limit=max(200, n))
    # Sort by miou_open_closed when present (as string)
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

    if "ezm_ml_idx" not in st.session_state:
        st.session_state.ezm_ml_idx = 0
    st.session_state.ezm_ml_idx = int(
        max(0, min(int(st.session_state.ezm_ml_idx), len(worst_rows) - 1))
    )

    nav1, nav2, nav3 = st.columns([1, 1, 3])
    with nav1:
        if st.button("Prev", disabled=st.session_state.ezm_ml_idx <= 0):
            st.session_state.ezm_ml_idx -= 1
    with nav2:
        if st.button("Next", disabled=st.session_state.ezm_ml_idx >= len(worst_rows) - 1):
            st.session_state.ezm_ml_idx += 1
    with nav3:
        st.write(f"Item {st.session_state.ezm_ml_idx + 1} / {len(worst_rows)}")

    row = worst_rows[int(st.session_state.ezm_ml_idx)]
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

    st.markdown("#### Label this frame")
    label = st.radio(
        "Label",
        options=["unreviewed", "gt_issue", "model_issue", "ambiguous"],
        horizontal=True,
        index=0,
        key="ezm_ml_label",
    )
    notes = st.text_area("Notes", value="", key="ezm_ml_notes")

    if st.button("Save label to DB", key="ezm_ml_save"):
        con.execute("BEGIN")
        con.execute(
            """
            INSERT INTO ml_frame_reviews (kind, run_path, video_path, frame_idx, overlay_path, zone_json, metric, label, notes, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(kind, run_path, video_path, frame_idx, overlay_path) DO UPDATE SET
              zone_json=excluded.zone_json,
              metric=excluded.metric,
              label=excluded.label,
              notes=excluded.notes,
              updated_at=datetime('now')
            """,
            (
                "ezm_unet_open_closed",
                str(run_dir),
                str(row.get("video_path") or ""),
                int(float(row.get("frame_idx") or 0)),
                str(overlay_path),
                str(row.get("zone_json") or ""),
                _as_float(row.get("miou_open_closed")),
                str(label),
                str(notes),
            ),
        )
        con.commit()
        st.success("Saved.")

    with st.expander("Recent saved labels (this run)", expanded=False):
        saved = _fetchall(
            con,
            """
            SELECT video_path, frame_idx, metric, label, notes, updated_at
            FROM ml_frame_reviews
            WHERE kind = ? AND run_path = ?
            ORDER BY updated_at DESC
            LIMIT 50
            """,
            ("ezm_unet_open_closed", str(run_dir)),
        )
        st.dataframe([dict(r) for r in saved], width="stretch", hide_index=True)

    st.subheader("Retrain (Slurm)")
    # We do a "free node" check before offering submit.
    slurm_script = Path(workspace_root) / "scripts" / "statistics_organized" / "dlc_ezm_open_closed" / "torch_ml" / "run_train_unet_open_closed_from_zones_augfix_sched_and_qc.slurm"
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

    check = st.button("Check for idle nodes", key="ezm_ml_check_idle")
    idle_ok = False
    if check:
        try:
            # Cluster rule: look for a free node before starting jobs.
            cmd = ["sinfo", "-h", "-t", "idle,mix", "-o", "%P %D %N"]
            r = subprocess.run(cmd, check=False, capture_output=True, text=True)
            out = (r.stdout or "").strip()
            err = (r.stderr or "").strip()
            if err:
                st.caption(err)
            st.code(out or "(no output)")
            if part:
                # Best-effort: require at least one line mentioning the partition.
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
        try:
            r = subprocess.run(["sbatch", str(slurm_script)], check=False, capture_output=True, text=True)
            if r.returncode != 0:
                st.error(r.stderr or r.stdout or "sbatch failed.")
            else:
                msg = (r.stdout or "").strip()
                st.success(msg or "Submitted.")
                # Print monitoring commands
                jobid = msg.split()[-1] if msg else ""
                if jobid.isdigit():
                    st.code(
                        "\n".join(
                            [
                                f"squeue -j {jobid}",
                                f"sacct -j {jobid} --format=JobID,JobName%25,State,Elapsed,MaxRSS,AllocCPUS,NodeList%25",
                            ]
                        )
                    )
        except Exception as e:
            st.error(f"sbatch failed: {e}")


def main() -> None:
    st.set_page_config(page_title="MUS1 Experiment Browser", layout="wide")
    st.title("MUS1 Experiment Browser")

    st.sidebar.header("Database")
    args = _parse_args()
    default_project = args.project_path or str(Path.cwd())
    project_path_str = st.sidebar.text_input("Project path (contains mus1.db)", value=str(default_project))
    project_path = Path(project_path_str).expanduser()
    db_path = project_path / "mus1.db"
    workspace_root = args.workspace_root

    if not db_path.exists():
        st.sidebar.error(f"mus1.db not found at: {db_path}")
        st.stop()

    con = _connect(db_path)

    st.sidebar.header("View")
    view = st.sidebar.radio("Mode", options=["Experiments", "EZM ML"], index=0)

    if view == "EZM ML":
        _render_ezm_ml(con, workspace_root=workspace_root)
        st.stop()

    st.sidebar.header("Filters")
    exp_types = _one_col(con, "SELECT DISTINCT experiment_type FROM experiments ORDER BY experiment_type ASC")
    selected_types = st.sidebar.multiselect("Experiment type", options=exp_types, default=exp_types)
    only_ezm = st.sidebar.checkbox("Only with EZM zone JSON", value=False)
    only_nor_nof = st.sidebar.checkbox("Only with NOR/NOF ROI JSON", value=False)

    exps = _list_experiments(
        con,
        experiment_types=selected_types,
        only_with_ezm_zone=only_ezm,
        only_with_nor_nof_roi=only_nor_nof,
    )

    st.caption(f"DB: `{db_path}`")
    st.caption(f"Experiments: {len(exps)}")

    # High-signal QC: show unlinked annotation JSONs so users can fix mappings.
    with st.expander("Annotation QC (unlinked / errors)", expanded=False):
        ann_qc = _get_annotation_qc(con)
        if not ann_qc:
            st.caption("No annotation QC events found.")
        else:
            index_map = _load_session_index(workspace_root) if workspace_root else None
            # Show a small, readable table view.
            rows = []
            for r in ann_qc[:300]:
                try:
                    details = json.loads(r["details_json"] or "{}")
                except Exception:
                    details = {"_raw": r["details_json"]}

                inferred_task = details.get("inferred_task")
                bn = _normalize_basename(details.get("video_basename") or (Path(details["video_path"]).name if details.get("video_path") else None))
                suggested_session_id = None
                suggested_video_path = None
                if index_map and inferred_task and bn:
                    hit = index_map.get((str(inferred_task), str(bn)))
                    if hit:
                        suggested_session_id = hit.get("session_id")
                        suggested_video_path = hit.get("video_path")

                # Simple reason classification (kept lightweight)
                reason = "not_in_session_index"
                vp = details.get("video_path") or ""
                if "unknown" in vp:
                    reason = "video_path_in_unknown_folder"

                rows.append(
                    {
                        "id": r["id"],
                        "code": r["code"],
                        "created_at": r["created_at"],
                        "zone_json": details.get("zone_json") or details.get("path"),
                        "video_path": details.get("video_path"),
                        "kind": details.get("kind"),
                        "inferred_task": inferred_task,
                        "video_basename": bn,
                        "reason": reason,
                        "suggested_session_id": suggested_session_id,
                        "suggested_video_path": suggested_video_path,
                        "error": details.get("error"),
                    }
                )
            st.dataframe(rows, width="stretch", hide_index=True)

            relink_candidates = [
                r
                for r in rows
                if r.get("suggested_session_id") and r.get("zone_json") and r.get("kind")
            ]
            if relink_candidates:
                st.markdown("**Relink an annotation (apply suggested match)**")
                options = [str(r["id"]) for r in relink_candidates]
                qc_choice = st.selectbox("QC event id", options=options, key="relink_qc_id")
                selected = next(r for r in relink_candidates if str(r["id"]) == str(qc_choice))

                st.caption(f"Zone JSON: `{selected.get('zone_json')}`")
                st.caption(f"Suggested experiment_id: `{selected.get('suggested_session_id')}`")
                if selected.get("suggested_video_path"):
                    st.caption(f"Suggested video_path: `{selected.get('suggested_video_path')}`")

                if st.button("Apply relink + clear QC event", key=f"relink_apply_{selected['id']}"):
                    try:
                        con.execute("BEGIN")
                        ok = _update_external_artifact_linkage(
                            con,
                            kind=str(selected["kind"]),
                            path=str(selected["zone_json"]),
                            experiment_id=str(selected["suggested_session_id"]),
                            subject_id=None,
                            meta_patch={
                                "link_method": "manual_suggested",
                                "suggested_session_id": str(selected["suggested_session_id"]),
                                "suggested_video_path": selected.get("suggested_video_path"),
                            },
                        )
                        if not ok:
                            con.rollback()
                            st.error("No external_artifacts row found for this kind+path.")
                        else:
                            _delete_qc_event(con, int(selected["id"]))
                            con.commit()
                            st.success("Relink applied and QC event cleared. Refreshing…")
                            st.rerun()
                    except Exception as e:
                        try:
                            con.rollback()
                        except Exception:
                            pass
                        st.error(f"Relink failed: {e}")
            else:
                st.caption("No relink suggestions available for the remaining rows.")

    # Selection
    exp_ids = [e.experiment_id for e in exps]
    selected_exp = st.selectbox("Select experiment", options=exp_ids) if exp_ids else None

    # Table view
    st.subheader("Experiments")
    st.dataframe(
        [
            {
                "experiment_id": e.experiment_id,
                "task": e.experiment_type,
                "date_recorded": e.date_recorded,
                "stage": e.processing_stage,
                "subject_id": e.subject_id,
                "sex": e.sex,
                "genotype": e.genotype,
                "treatment": e.treatment,
                "artifacts": e.artifacts_count,
                "qc": e.qc_count,
                "ezm_zone": e.has_ezm_zone,
                "nor_nof_roi": e.has_nor_nof_roi,
            }
            for e in exps
        ],
        width="stretch",
        hide_index=True,
    )

    if not selected_exp:
        st.stop()

    st.subheader(f"Experiment detail: {selected_exp}")
    artifacts = _get_experiment_artifacts(con, selected_exp)
    qc = _get_experiment_qc(con, selected_exp)

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("#### External artifacts")
        if not artifacts:
            st.info("No external artifacts linked to this experiment.")
        else:
            # Group by kind
            by_kind: Dict[str, List[sqlite3.Row]] = {}
            for r in artifacts:
                by_kind.setdefault(str(r["kind"]), []).append(r)

            for kind, items in by_kind.items():
                with st.expander(f"{kind} ({len(items)})", expanded=(kind in {"ezm_zone_json_v2", "nor_nof_objects_json_v1"})):
                    for it in items[:200]:
                        st.code(str(it["path"]), language=None)
                        meta = _parse_meta(it["meta_json"])
                        if meta:
                            st.json(meta, expanded=False)

    with col2:
        st.markdown("#### QC events")
        if not qc:
            st.info("No QC events linked to this experiment.")
        else:
            for r in qc[:200]:
                title = f"{r['scope']}::{r['code']} (id={r['id']})"
                with st.expander(title, expanded=False):
                    st.code(str(r["created_at"]), language=None)
                    try:
                        st.json(json.loads(r["details_json"] or "{}"), expanded=False)
                    except Exception:
                        st.code(str(r["details_json"]), language=None)


if __name__ == "__main__":
    main()

