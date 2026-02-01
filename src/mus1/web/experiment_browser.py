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
import math
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

    con.execute(
        """
        CREATE TABLE IF NOT EXISTS ml_training_frame_queue (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          kind TEXT NOT NULL,
          run_path TEXT NOT NULL,
          video_path TEXT NOT NULL,
          frame_idx INTEGER NOT NULL,
          overlay_path TEXT,
          zone_json TEXT,
          score REAL,
          status TEXT NOT NULL DEFAULT 'queued',
          created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    con.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_ml_training_frame_queue_unique
        ON ml_training_frame_queue(kind, run_path, video_path, frame_idx)
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


def _tail_text(path: Path, *, max_lines: int = 200) -> str:
    """
    Efficient-ish tail for log files (best effort).
    """
    try:
        if max_lines <= 0:
            return ""
        # Read from the end in chunks until we have enough newlines.
        with path.open("rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            block = 8192
            data = b""
            pos = size
            while pos > 0 and data.count(b"\n") <= max_lines:
                step = block if pos >= block else pos
                pos -= step
                f.seek(pos, os.SEEK_SET)
                data = f.read(step) + data
            txt = data.decode(errors="replace")
            lines = txt.splitlines()[-max_lines:]
            return "\n".join(lines)
    except Exception:
        return ""


def _run_cmd(cmd: List[str]) -> Tuple[int, str, str]:
    try:
        r = subprocess.run(cmd, check=False, capture_output=True, text=True)
        return int(r.returncode), (r.stdout or "").strip(), (r.stderr or "").strip()
    except Exception as e:
        return 1, "", str(e)


@st.cache_data(show_spinner=False, ttl=20)
def _slurm_squeue(user: str) -> List[Dict[str, str]]:
    """
    Return a table of active jobs for the given user.
    """
    # Use a parsable format to avoid brittle whitespace parsing.
    fmt = "%i|%P|%j|%u|%T|%M|%D|%R"
    code, out, err = _run_cmd(["squeue", "-u", str(user), "-h", "-o", fmt])
    if code != 0:
        return [{"jobid": "", "partition": "", "name": "", "user": str(user), "state": "ERROR", "time": "", "nodes": "", "reason": err or out}]
    rows = []
    for line in (out.splitlines() if out else []):
        parts = line.split("|")
        if len(parts) != 8:
            continue
        rows.append(
            {
                "jobid": parts[0],
                "partition": parts[1],
                "name": parts[2],
                "user": parts[3],
                "state": parts[4],
                "time": parts[5],
                "nodes": parts[6],
                "nodelist_reason": parts[7],
            }
        )
    return rows


@st.cache_data(show_spinner=False, ttl=60)
def _slurm_sacct(jobid: str) -> str:
    code, out, err = _run_cmd(
        [
            "sacct",
            "-j",
            str(jobid),
            "--format=JobID,JobName%25,Partition,State,Elapsed,Timelimit,AllocCPUS,NodeList%25,ExitCode,MaxRSS",
            "-n",
        ]
    )
    if code != 0:
        return err or out
    return out


@st.cache_data(show_spinner=False, ttl=20)
def _slurm_sstat(jobid: str) -> str:
    # Often only meaningful while running.
    code, out, err = _run_cmd(
        [
            "sstat",
            "-j",
            f"{jobid}.batch",
            "--format=JobID,AveCPU,MaxRSS,AveRSS,MaxVMSize",
            "-n",
        ]
    )
    if code != 0:
        return err or out
    return out


@st.cache_data(show_spinner=False, ttl=60)
def _slurm_scontrol_node(node: str) -> str:
    code, out, err = _run_cmd(["scontrol", "show", "node", "-o", str(node)])
    if code != 0:
        return err or out
    return out


@st.cache_data(show_spinner=False, ttl=30)
def _discover_ml_tracking_runs(workspace_root: str) -> List[Dict[str, Any]]:
    """
    Discover ML tracking run outputs that contain run_status.json (and optionally metrics.csv).
    """
    if not workspace_root:
        return []
    ws = Path(workspace_root)
    base = ws / "ml_tracking_metadata_model" / "runs"
    if not base.exists():
        return []

    runs: List[Dict[str, Any]] = []
    # Common patterns used by this workspace.
    patterns = [
        "*/train_session_long_*",
        "*/train_session_test_*",
        "*/train_session",
        "*/train",  # legacy baseline trainer output
        "**/train_session_long_*",
        "**/train_session_test_*",
    ]
    seen: set[str] = set()
    for pat in patterns:
        for p in base.glob(pat):
            if not p.is_dir():
                continue
            rs = p / "run_status.json"
            if not rs.exists():
                continue
            key = str(p.resolve())
            if key in seen:
                continue
            seen.add(key)
            try:
                st_mtime = rs.stat().st_mtime
            except Exception:
                st_mtime = 0.0
            runs.append(
                {
                    "run_path": key,
                    "name": p.name,
                    "mtime": float(st_mtime),
                    "has_metrics": (p / "metrics.csv").exists(),
                    "has_by_exposure": (p / "metrics_by_exposure.csv").exists(),
                }
            )
    runs.sort(key=lambda r: float(r.get("mtime", 0.0)), reverse=True)
    return runs


def _render_training_monitor(*, workspace_root: Optional[str]) -> None:
    st.header("Training Monitor")
    st.caption("Read-only monitoring of Slurm jobs and ML run outputs (metrics + logs).")
    if not workspace_root:
        st.error("This view requires `--workspace-root` so we can find run outputs.")
        st.stop()

    user = os.environ.get("USER", "").strip() or "unknown"

    col_a, col_b = st.columns([1, 1])
    with col_a:
        if st.button("Refresh now"):
            st.cache_data.clear()
            st.rerun()
    with col_b:
        st.caption("Auto-refresh by reloading the page; cached queries update every ~20–60s.")

    st.subheader("What to watch (best practice)")
    st.markdown(
        "\n".join(
            [
                "- **Job health**: job state (RUNNING/PENDING), time remaining, and whether the job is writing outputs regularly.",
                "- **Resource usage**: MaxRSS / AveRSS, and CPU utilization (low CPU can indicate a stall or oversubscription).",
                "- **Learning signal**: session-level balanced accuracy trends by repeat; don’t interpret single repeats.",
                "- **Timepoint trend**: performance by `exposure_num` with consistent subject-grouped splits (session-level aggregation).",
                "- **Failure modes**: max-iter convergence warnings, missing classes in test fold, and timeouts.",
            ]
        )
    )

    st.subheader("Active Slurm jobs")
    jobs = _slurm_squeue(user)
    st.dataframe(jobs, width="stretch", hide_index=True)

    jobids = [j["jobid"] for j in jobs if str(j.get("jobid", "")).isdigit()]
    selected_job = st.selectbox("Inspect job", options=(["(none)"] + jobids), index=0)
    if selected_job != "(none)":
        st.markdown("#### Job accounting (sacct)")
        st.code(_slurm_sacct(selected_job) or "(no output)")
        st.markdown("#### Live usage (sstat)")
        st.code(_slurm_sstat(selected_job) or "(no output)")
        # Extract node name if present in nodelist_reason like "n144" or "(Priority)".
        nodelist = next((j.get("nodelist_reason", "") for j in jobs if j.get("jobid") == selected_job), "")
        node = ""
        for tok in str(nodelist).replace(",", " ").split():
            if tok.startswith("n") and tok[1:].isdigit():
                node = tok
                break
        if node:
            st.markdown(f"#### Node snapshot (`{node}`)")
            st.code(_slurm_scontrol_node(node) or "(no output)")

    st.subheader("ML tracking runs (what it learned)")
    runs = _discover_ml_tracking_runs(str(workspace_root))
    if not runs:
        st.info("No ML tracking runs found under `ml_tracking_metadata_model/runs/**/train*`.")
        st.stop()

    run_labels = [f"{r['name']}  ({'metrics' if r['has_metrics'] else 'no-metrics'})  {r['run_path']}" for r in runs[:200]]
    choice = st.selectbox("Select run output dir", options=run_labels, index=0)
    run = next(r for r in runs if f"{r['name']}  ({'metrics' if r['has_metrics'] else 'no-metrics'})  {r['run_path']}" == choice)
    run_dir = Path(str(run["run_path"]))

    st.caption(f"Run dir: `{run_dir}`")
    # Status
    try:
        status = json.loads((run_dir / "run_status.json").read_text())
    except Exception:
        status = {}
    with st.expander("run_status.json", expanded=False):
        st.json(status, expanded=False)

    # Metrics
    metrics_path = run_dir / "metrics.csv"
    if metrics_path.exists():
        try:
            mdf = pd.read_csv(metrics_path)
        except Exception:
            mdf = pd.DataFrame()
        if not mdf.empty and "repeat" in mdf.columns and "value" in mdf.columns:
            mdf["repeat"] = pd.to_numeric(mdf["repeat"], errors="coerce")
            mdf["value"] = pd.to_numeric(mdf["value"], errors="coerce")
            if "score_level" in mdf.columns:
                mdf = mdf[mdf["score_level"].astype(str) == "session"].copy()
            st.markdown("#### Session-level accuracy trend (by repeat)")
            for tgt in ["sex", "genotype"]:
                sub = mdf[mdf["target"].astype(str) == tgt].sort_values("repeat", kind="mergesort")
                if sub.empty:
                    continue
                st.line_chart(sub.set_index("repeat")["value"], height=160)
        with st.expander("metrics.csv (tail)", expanded=False):
            st.code(_tail_text(metrics_path, max_lines=120) or "(empty)")
    else:
        st.warning("metrics.csv not found yet (run may still be in progress).")

    byexp_path = run_dir / "metrics_by_exposure.csv"
    if byexp_path.exists():
        try:
            bdf = pd.read_csv(byexp_path)
        except Exception:
            bdf = pd.DataFrame()
        if not bdf.empty and "exposure_num" in bdf.columns and "value" in bdf.columns:
            bdf["exposure_num"] = pd.to_numeric(bdf["exposure_num"], errors="coerce")
            bdf["value"] = pd.to_numeric(bdf["value"], errors="coerce")
            st.markdown("#### Accuracy by exposure_num (mean over repeats so far)")
            piv = (
                bdf.groupby(["target", "exposure_num"], dropna=False)["value"]
                .mean()
                .reset_index()
                .pivot(index="exposure_num", columns="target", values="value")
                .sort_index()
            )
            st.line_chart(piv, height=200)
        with st.expander("metrics_by_exposure.csv (tail)", expanded=False):
            st.code(_tail_text(byexp_path, max_lines=120) or "(empty)")

    # Logs: user-provided path (we can't reliably infer jobid -> log file)
    st.subheader("Log tail (optional)")
    default_log = str((Path(workspace_root) / "logs").resolve())
    log_path_str = st.text_input(
        "Path to a log file to tail (absolute or relative to workspace root)",
        value="",
        help=f"Example: `{default_log}/train_sess_eval_long_<jobid>.out`",
    )
    if log_path_str.strip():
        p = Path(log_path_str.strip()).expanduser()
        if not p.is_absolute():
            p = (Path(workspace_root) / p).resolve()
        # Safety: ensure within workspace root
        try:
            ws = Path(workspace_root).resolve()
            if ws not in p.parents and p != ws:
                st.error("Refusing to read a path outside the workspace root.")
            elif p.exists():
                st.code(_tail_text(p, max_lines=200) or "(empty)")
            else:
                st.warning(f"Not found: {p}")
        except Exception as e:
            st.error(f"Path error: {e}")


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

    st.markdown("#### Label arena markings on this frame")
    st.caption(
        "Use this editor to label the EZM arena (outer/inner boundaries + 4 borders + open sectors) on this exact frame. "
        "Saving updates the referenced zone JSON. Then you can add this frame to the training frame set."
    )

    # --- Minimal EZM annotator (ported from scripts/arena_annotation/app.py) ---
    try:
        import numpy as np  # type: ignore
        import cv2  # type: ignore
        from PIL import Image  # type: ignore
        from streamlit_drawable_canvas import st_canvas  # type: ignore
    except Exception as e:
        st.error(
            "EZM frame labeling requires extra deps. Reinstall with:\n"
            "  pip install -e \".[web]\"\n"
            f"Import error: {e}"
        )
        st.stop()

    TAU = 2.0 * math.pi

    @dataclass(frozen=True)
    class _EllipseParams:
        center_xy: Tuple[float, float]
        axes_xy: Tuple[float, float]  # diameters
        angle_deg: float

        @property
        def a(self) -> float:
            return float(self.axes_xy[0]) / 2.0

        @property
        def b(self) -> float:
            return float(self.axes_xy[1]) / 2.0

        @property
        def angle_rad(self) -> float:
            return math.radians(float(self.angle_deg))

    def _wrap_angle(theta: np.ndarray) -> np.ndarray:
        return np.mod(theta, TAU)

    def _rotation_matrix(angle_rad: float) -> np.ndarray:
        c = math.cos(angle_rad)
        s = math.sin(angle_rad)
        return np.array([[c, -s], [s, c]], dtype=float)

    def _compute_r_theta(x: np.ndarray, y: np.ndarray, outer: _EllipseParams) -> Tuple[np.ndarray, np.ndarray]:
        x = np.asarray(x, dtype=float)
        y = np.asarray(y, dtype=float)
        cx, cy = outer.center_xy
        pts = np.stack([x - cx, y - cy], axis=0)
        R = _rotation_matrix(-outer.angle_rad)
        rot = R @ pts
        a = outer.a if outer.a > 0 else np.nan
        b = outer.b if outer.b > 0 else np.nan
        xn = rot[0, :] / a
        yn = rot[1, :] / b
        r = np.sqrt(xn * xn + yn * yn)
        theta = _wrap_angle(np.arctan2(yn, xn))
        return r, theta

    def _circular_mean(angles: List[float]) -> float:
        ang = np.asarray(list(angles), dtype=float)
        s = float(np.nanmean(np.sin(ang)))
        c = float(np.nanmean(np.cos(ang)))
        return float((math.atan2(s, c)) % TAU)

    def _open_ranges_from_boundary_angles(boundary_angles_sorted: Tuple[float, float, float, float], open_sectors: List[int]) -> Tuple[Tuple[float, float], Tuple[float, float]]:
        angles = [float(a) % TAU for a in boundary_angles_sorted]
        if len(angles) != 4:
            raise ValueError("Expected 4 boundary angles")
        if len(open_sectors) != 2:
            raise ValueError("Expected exactly 2 open sectors")
        ranges = []
        for sidx in open_sectors:
            start = angles[int(sidx)]
            end = angles[(int(sidx) + 1) % 4]
            ranges.append((start, end))
        return (ranges[0], ranges[1])

    def _ensure_dict(x: Any) -> Dict[str, Any]:
        return x if isinstance(x, dict) else {}

    def _extract_points_from_canvas(canvas_json: Dict[str, Any]) -> List[Tuple[float, float]]:
        pts = []
        objs = list((_ensure_dict(canvas_json).get("objects", []) or []))
        for obj in objs:
            if not isinstance(obj, dict):
                continue
            if obj.get("type") != "circle":
                continue
            # Fabric circles are stored by bounding box top/left + radius
            left = float(obj.get("left", 0.0))
            top = float(obj.get("top", 0.0))
            radius = float(obj.get("radius", 0.0))
            pts.append((left + radius, top + radius))
        return pts

    def _extract_lines_from_canvas(canvas_json: Dict[str, Any]) -> List[Tuple[Tuple[float, float], Tuple[float, float]]]:
        lines = []
        objs = list((_ensure_dict(canvas_json).get("objects", []) or []))
        for obj in objs:
            if not isinstance(obj, dict):
                continue
            if obj.get("type") != "line":
                continue
            # Fabric lines are stored with x1..y2 in object-local coords + left/top offset
            left = float(obj.get("left", 0.0))
            top = float(obj.get("top", 0.0))
            x1 = float(obj.get("x1", 0.0))
            y1 = float(obj.get("y1", 0.0))
            x2 = float(obj.get("x2", 0.0))
            y2 = float(obj.get("y2", 0.0))
            lines.append(((left + x1, top + y1), (left + x2, top + y2)))
        return lines

    def _scale_for_display(img_rgb: np.ndarray, disp_w: int) -> Tuple[Image.Image, float]:
        h, w = img_rgb.shape[:2]
        if w <= 0 or h <= 0:
            raise ValueError("Invalid image")
        scale = float(disp_w) / float(w)
        new_w = int(round(w * scale))
        new_h = int(round(h * scale))
        pil = Image.fromarray(img_rgb)
        pil = pil.resize((new_w, new_h))
        return pil, scale

    def _fit_zones_from_annotations(
        outer_pts: List[Tuple[float, float]],
        inner_pts: List[Tuple[float, float]],
        border_lines: List[Tuple[Tuple[float, float], Tuple[float, float]]],
        open_sectors: List[int],
    ) -> Tuple[_EllipseParams, float, Tuple[float, float, float, float], Tuple[Tuple[float, float], Tuple[float, float]]]:
        outer_arr = np.array(outer_pts, dtype=np.float32).reshape(-1, 1, 2)
        (cx, cy), (major, minor), angle_deg = cv2.fitEllipse(outer_arr)
        outer = _EllipseParams(center_xy=(float(cx), float(cy)), axes_xy=(float(major), float(minor)), angle_deg=float(angle_deg))

        inner_xy = np.array(inner_pts, dtype=float)
        r_inner_pts, _ = _compute_r_theta(inner_xy[:, 0], inner_xy[:, 1], outer)
        r_inner = float(np.nanmedian(r_inner_pts))

        angles = []
        for (p1, p2) in border_lines:
            _, th1 = _compute_r_theta(np.array([p1[0]]), np.array([p1[1]]), outer)
            _, th2 = _compute_r_theta(np.array([p2[0]]), np.array([p2[1]]), outer)
            angles.append(_circular_mean([float(th1[0]), float(th2[0])]))
        boundary_angles = tuple(sorted(float(a) for a in angles))  # type: ignore[assignment]
        open_ranges = _open_ranges_from_boundary_angles(boundary_angles, open_sectors)
        return outer, r_inner, boundary_angles, open_ranges

    video_rel = str(row.get("video_path") or "")
    frame_idx = int(float(row.get("frame_idx") or 0))
    # training_index uses relative paths under workspace; convert to absolute for reading
    video_abs = (Path(workspace_root) / video_rel).resolve() if not Path(video_rel).is_absolute() else Path(video_rel)

    zone_json_path = Path(str(row.get("zone_json") or "")).expanduser()
    if not zone_json_path.is_absolute():
        zone_json_path = (Path(workspace_root) / zone_json_path).resolve()

    # Load the specific frame for labeling
    if not video_abs.exists():
        st.error(f"Video not found: {video_abs}")
        st.stop()
    cap = cv2.VideoCapture(str(video_abs))
    cap.set(cv2.CAP_PROP_POS_FRAMES, int(frame_idx))
    ret, frame_bgr = cap.read()
    cap.release()
    if not ret or frame_bgr is None:
        st.error(f"Could not read frame {frame_idx} from: {video_abs}")
        st.stop()
    frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)

    disp_img, scale = _scale_for_display(frame_rgb, disp_w=900)
    inv_scale = 1.0 / float(scale)

    prefix = f"ezm_label::{video_rel}::frame{frame_idx}"
    k_outer = f"{prefix}::outer"
    k_inner = f"{prefix}::inner"
    k_borders = f"{prefix}::borders"
    k_open = f"{prefix}::open_sectors"

    if k_open not in st.session_state:
        st.session_state[k_open] = [0, 2]

    with st.expander("Arena labeling editor (save zone JSON)", expanded=False):
        if zone_json_path.exists() and st.button("Load existing zone JSON into editor", key=f"{prefix}::load"):
            try:
                data = json.loads(zone_json_path.read_text())
                ann = data.get("annotations", {}) if isinstance(data, dict) else {}
                st.session_state[k_outer] = ann.get("outer_canvas")
                st.session_state[k_inner] = ann.get("inner_canvas")
                st.session_state[k_borders] = ann.get("borders_canvas")
                # best-effort open sectors infer from stored open_angle_ranges if present
                st.success("Loaded.")
            except Exception as e:
                st.error(f"Failed to load: {e}")

        st.write("Step 1: outer points (>=10)")
        outer_canvas = st_canvas(
            fill_color="rgba(0, 255, 0, 0.3)",
            stroke_width=2,
            stroke_color="rgba(0, 255, 0, 0.8)",
            background_image=disp_img,
            update_streamlit=True,
            height=disp_img.size[1],
            width=disp_img.size[0],
            drawing_mode="circle",
            initial_drawing=st.session_state.get(k_outer),
            key=f"{prefix}::outer_canvas",
        )
        st.session_state[k_outer] = _ensure_dict(outer_canvas.json_data if outer_canvas else {})

        st.write("Step 2: inner points (>=10)")
        inner_canvas = st_canvas(
            fill_color="rgba(0, 255, 255, 0.3)",
            stroke_width=2,
            stroke_color="rgba(0, 255, 255, 0.8)",
            background_image=disp_img,
            update_streamlit=True,
            height=disp_img.size[1],
            width=disp_img.size[0],
            drawing_mode="circle",
            initial_drawing=st.session_state.get(k_inner),
            key=f"{prefix}::inner_canvas",
        )
        st.session_state[k_inner] = _ensure_dict(inner_canvas.json_data if inner_canvas else {})

        st.write("Step 3: borders (4 lines)")
        borders_canvas = st_canvas(
            fill_color="rgba(255, 0, 0, 0.2)",
            stroke_width=3,
            stroke_color="rgba(255, 0, 0, 0.9)",
            background_image=disp_img,
            update_streamlit=True,
            height=disp_img.size[1],
            width=disp_img.size[0],
            drawing_mode="line",
            initial_drawing=st.session_state.get(k_borders),
            key=f"{prefix}::borders_canvas",
        )
        st.session_state[k_borders] = _ensure_dict(borders_canvas.json_data if borders_canvas else {})

        open_sectors = st.multiselect("Open sectors (pick 2)", options=[0, 1, 2, 3], default=st.session_state.get(k_open, [0, 2]))
        st.session_state[k_open] = list(open_sectors)

        # Fit + save
        if st.button("Fit + save zone JSON for this video", key=f"{prefix}::save"):
            outer_pts = [(x * inv_scale, y * inv_scale) for (x, y) in _extract_points_from_canvas(st.session_state[k_outer])]
            inner_pts = [(x * inv_scale, y * inv_scale) for (x, y) in _extract_points_from_canvas(st.session_state[k_inner])]
            border_lines = [
                ((p1[0] * inv_scale, p1[1] * inv_scale), (p2[0] * inv_scale, p2[1] * inv_scale))
                for (p1, p2) in _extract_lines_from_canvas(st.session_state[k_borders])
            ]
            if len(outer_pts) < 10 or len(inner_pts) < 10:
                st.error("Need >=10 outer points and >=10 inner points.")
                st.stop()
            if len(border_lines) != 4:
                st.error("Need exactly 4 border lines.")
                st.stop()
            if len(open_sectors) != 2:
                st.error("Select exactly 2 open sectors.")
                st.stop()

            outer, r_inner, boundary_angles, open_ranges = _fit_zones_from_annotations(
                outer_pts=outer_pts,
                inner_pts=inner_pts,
                border_lines=border_lines,
                open_sectors=list(open_sectors),
            )

            payload = {
                "version": "ezm_open_closed_v2",
                "image": {"width": int(frame_rgb.shape[1]), "height": int(frame_rgb.shape[0])},
                "outer_ellipse": {
                    "center": [float(outer.center_xy[0]), float(outer.center_xy[1])],
                    "axes": [float(outer.axes_xy[0]), float(outer.axes_xy[1])],
                    "angle_deg": float(outer.angle_deg),
                },
                "r_inner": float(r_inner),
                "boundary_angles": [float(a) for a in boundary_angles],
                "open_angle_ranges": [[float(open_ranges[0][0]), float(open_ranges[0][1])], [float(open_ranges[1][0]), float(open_ranges[1][1])]],
                "annotations": {
                    "outer_canvas": st.session_state.get(k_outer),
                    "inner_canvas": st.session_state.get(k_inner),
                    "borders_canvas": st.session_state.get(k_borders),
                    "calibration": {
                        "video_path": str(video_abs),
                        "frame_idx": int(frame_idx),
                        "video_source": "MUS1 web (EZM ML)",
                    },
                },
                "notes": f"labeled_from_run={run_dir.name} frame_idx={frame_idx}",
            }
            zone_json_path.parent.mkdir(parents=True, exist_ok=True)
            zone_json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
            st.success(f"Saved: {zone_json_path}")

    st.markdown("#### Add this labeled frame to the next training run")
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

    queued = _fetchall(
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
            r = subprocess.run(
                ["sbatch", "--export", f"ALL,EZM_UNET_TRAIN_FRAMES={frames_str}", str(slurm_script)],
                check=False,
                capture_output=True,
                text=True,
            )
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
    view = st.sidebar.radio("Mode", options=["Experiments", "EZM ML", "Training Monitor"], index=0)

    if view == "EZM ML":
        _render_ezm_ml(con, workspace_root=workspace_root)
        st.stop()
    if view == "Training Monitor":
        _render_training_monitor(workspace_root=workspace_root)
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

