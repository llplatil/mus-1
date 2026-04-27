from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
import streamlit as st

from ..db import fetchall


TASK_ORDER = ["OF", "EZM", "NOR", "NOF", "RR"]

TRACKING_ARTIFACT_KINDS = {
    "dlc_csv_path",
    "dlc_tracking_csv",
    "moseq2_results_h5_path",
    "kpms_syllable_stats_path",
}


from mus1.web.discovery import CACHE_TTL_SECONDS  # noqa: E402


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def _load_experiment_data_index(
    experiment_data_root: str,
) -> Dict[str, Dict[str, Any]]:
    """Scan experiment JSONs across every configured data root into a dict.

    *experiment_data_root* is retained as a project-path anchor; its parent
    is the project_path used for multi-root discovery.
    """
    from mus1.web.discovery import iter_experiment_dirs, find_experiment_json

    index: Dict[str, Dict[str, Any]] = {}
    project_path = Path(experiment_data_root).parent
    found_any = False
    for _, _, exp_dir in iter_experiment_dirs(project_path):
        found_any = True
        jp = find_experiment_json(exp_dir)
        if jp is None:
            continue
        try:
            data = json.loads(jp.read_text())
            eid = data.get("experiment_id", exp_dir.name)
            index[eid] = data
        except Exception:
            continue
    if found_any:
        return index
    # Fallback: legacy single-root scan
    root = Path(experiment_data_root)
    if not root.is_dir():
        return index
    for task_dir in root.iterdir():
        if not task_dir.is_dir():
            continue
        for exp_dir in task_dir.iterdir():
            if not exp_dir.is_dir():
                continue
            jsons = list(exp_dir.glob("*.json"))
            if not jsons:
                continue
            try:
                data = json.loads(jsons[0].read_text())
                eid = data.get("experiment_id", exp_dir.name)
                index[eid] = data
            except Exception:
                continue
    return index


def _subject_summary_from_db(con: sqlite3.Connection) -> pd.DataFrame:
    """Build per-subject summary with experiment type counts + rotarod from assay_sessions."""
    exp_sql = """
    SELECT
      s.id                    AS subject_id,
      s.sex                   AS sex,
      s.individual_genotype   AS genotype,
      s.individual_treatment  AS treatment,
      s.birth_date            AS birth_date,
      e.experiment_type       AS experiment_type,
      COUNT(*)                AS n
    FROM subjects s
    LEFT JOIN experiments e ON e.subject_id = s.id
    GROUP BY s.id, e.experiment_type
    """
    rows = fetchall(con, exp_sql)
    if not rows:
        return pd.DataFrame()

    subjects: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        sid = str(r["subject_id"])
        if sid not in subjects:
            subjects[sid] = {
                "Subject": sid,
                "Sex": str(r["sex"] or ""),
                "Genotype": str(r["genotype"] or ""),
                "Treatment": str(r["treatment"] or ""),
                "Birth date": str(r["birth_date"] or "")[:10],
            }
            for t in TASK_ORDER:
                subjects[sid][t] = 0
            subjects[sid]["Total"] = 0
        etype = str(r["experiment_type"] or "")
        n = int(r["n"])
        col = etype if etype in TASK_ORDER else None
        if col:
            subjects[sid][col] = n
            subjects[sid]["Total"] += n

    rr_sql = """
    SELECT subject_id,
           COUNT(DISTINCT CASE WHEN occurred_at IS NOT NULL THEN DATE(occurred_at) END)
           + CASE WHEN SUM(CASE WHEN occurred_at IS NULL THEN 1 ELSE 0 END) > 0 THEN 1 ELSE 0 END
           AS n
    FROM assay_sessions
    WHERE assay_type = 'rotarod'
    GROUP BY subject_id
    """
    for r in fetchall(con, rr_sql):
        sid = str(r["subject_id"])
        if sid in subjects:
            old_rr = subjects[sid]["RR"]
            subjects[sid]["RR"] = int(r["n"])
            subjects[sid]["Total"] += int(r["n"]) - old_rr

    df = pd.DataFrame(list(subjects.values()))
    col_order = ["Subject", "Sex", "Genotype", "Treatment", "Birth date"] + TASK_ORDER + ["Total"]
    df = df[[c for c in col_order if c in df.columns]]
    df = df.sort_values("Subject").reset_index(drop=True)
    return df


def _subject_experiments(
    con: sqlite3.Connection,
    subject_id: str,
) -> pd.DataFrame:
    sql = """
    SELECT
      e.id                  AS experiment_id,
      e.experiment_type     AS experiment_type,
      e.date_recorded       AS date_recorded,
      e.processing_stage    AS processing_stage
    FROM experiments e
    WHERE e.subject_id = ?
    ORDER BY e.experiment_type, e.date_recorded
    """
    rows = fetchall(con, sql, (subject_id,))
    if not rows:
        return pd.DataFrame()
    records = []
    for r in rows:
        records.append({
            "Experiment": str(r["experiment_id"]),
            "Type": str(r["experiment_type"]),
            "Date": str(r["date_recorded"] or "")[:10],
            "Stage": str(r["processing_stage"]),
        })
    return pd.DataFrame(records)


def _experiment_artifacts(
    con: sqlite3.Connection,
    experiment_id: str,
) -> List[Dict[str, str]]:
    sql = """
    SELECT kind, path FROM external_artifacts
    WHERE experiment_id = ?
    ORDER BY kind
    """
    rows = fetchall(con, sql, (experiment_id,))
    seen: set[str] = set()
    out: List[Dict[str, str]] = []
    for r in rows:
        key = f"{r['kind']}|{r['path']}"
        if key in seen:
            continue
        seen.add(key)
        out.append({"Kind": str(r["kind"]), "Path": str(r["path"])})
    return out


def _experiment_assay_measurements(
    con: sqlite3.Connection,
    experiment_id: str,
) -> pd.DataFrame:
    sql = """
    SELECT
      a_s.assay_type  AS assay_type,
      a_s.occurred_at AS occurred_at,
      a_m.metric      AS metric,
      a_m.value       AS value,
      a_m.units       AS units
    FROM assay_sessions a_s
    JOIN assay_measurements a_m ON a_m.assay_session_id = a_s.id
    WHERE a_s.experiment_id = ?
    ORDER BY a_m.metric
    """
    rows = fetchall(con, sql, (experiment_id,))
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame([dict(r) for r in rows])


def _subject_rotarod_sessions(
    con: sqlite3.Connection,
    subject_id: str,
    ed_index: Dict[str, Dict[str, Any]],
) -> pd.DataFrame:
    """Build rotarod session table from assay_sessions + assay_measurements.

    Deduplicates by (experiment_id) to handle duplicate assay_session rows
    that may exist from repeated sync runs.
    """
    sql = """
    SELECT
      a_s.id            AS session_id,
      a_s.experiment_id AS experiment_id,
      a_s.occurred_at   AS date,
      a_m.metric        AS metric,
      a_m.value         AS value
    FROM assay_sessions a_s
    JOIN assay_measurements a_m ON a_m.assay_session_id = a_s.id
    WHERE a_s.subject_id = ? AND a_s.assay_type = 'rotarod'
    ORDER BY a_s.occurred_at, a_m.metric
    """
    rows = fetchall(con, sql, (subject_id,))
    if not rows:
        return pd.DataFrame()

    # Keep only the first session_id per experiment_id to deduplicate
    first_session_for_exp: Dict[str, int] = {}
    for r in rows:
        eid = str(r["experiment_id"] or r["session_id"])
        sid = int(r["session_id"])
        if eid not in first_session_for_exp:
            first_session_for_exp[eid] = sid

    valid_session_ids = set(first_session_for_exp.values())

    sessions: Dict[int, Dict[str, Any]] = {}
    for r in rows:
        sid = int(r["session_id"])
        if sid not in valid_session_ids:
            continue
        if sid not in sessions:
            sessions[sid] = {"Date": str(r["date"] or "")[:10]}
        sessions[sid][str(r["metric"])] = r["value"]

    df = pd.DataFrame(list(sessions.values()))

    # Try to add timepoint from experiment_data RR JSONs
    rr_by_date: Dict[str, Dict[str, Any]] = {}
    for eid, ed in ed_index.items():
        if ed.get("experiment_type") == "RR":
            md = ed.get("metadata", {})
            d = md.get("date_recorded", "")
            sid = md.get("subject_id", "")
            if sid == subject_id and d:
                rr_by_date[d] = ed

    if rr_by_date:
        tp_col = []
        for _, row in df.iterrows():
            ed = rr_by_date.get(row["Date"])
            if ed:
                tp = ed.get("metadata", {}).get("experiment_level", {}).get("timepoint", "")
                tp_col.append(str(tp) if tp != "" else "")
            else:
                tp_col.append("")
        df.insert(1, "Timepoint", tp_col)

    return df


def _enrich_with_experiment_data(
    exp_df: pd.DataFrame,
    ed_index: Dict[str, Dict[str, Any]],
) -> pd.DataFrame:
    """Add columns from experiment_data JSONs to the experiments dataframe."""
    has_video = []
    has_tracking = []
    tracking_source = []
    timepoint = []

    for _, row in exp_df.iterrows():
        eid = row["Experiment"]
        ed = ed_index.get(eid)
        if ed is None:
            has_video.append("")
            has_tracking.append("")
            tracking_source.append("")
            timepoint.append("")
            continue

        vid = ed.get("video")
        if vid and vid.get("path"):
            has_video.append("yes")
        elif row.get("Type") == "RR" or row.get("Type") == "ROTAROD":
            has_video.append("n/a")
        else:
            has_video.append("no")

        ext = ed.get("extraction", {})
        tp_raw = ext.get("tracking_file_path") or ""
        h5_paths = [
            r.get("kpms_stats_path", "")
            for r in ext.get("analysis_runs", [])
        ]
        moseq_h5 = ext.get("moseq2_h5_path") or ""

        if tp_raw:
            has_tracking.append("yes")
            model = ext.get("dlc_model_path", "")
            tracking_source.append(model.split("_shuffle")[0] if model else "DLC")
        elif moseq_h5 or any(h5_paths):
            has_tracking.append("yes")
            tracking_source.append("moseq2/kpms")
        elif row.get("Type") == "RR" or row.get("Type") == "ROTAROD":
            has_tracking.append("n/a")
            tracking_source.append("")
        else:
            has_tracking.append("no")
            tracking_source.append("")

        md = ed.get("metadata", {})
        exp_level = md.get("experiment_level", {})
        tp = exp_level.get("timepoint", "")
        timepoint.append(str(tp) if tp != "" else "")

    exp_df = exp_df.copy()
    exp_df.insert(2, "Timepoint", timepoint)
    exp_df["Video"] = has_video
    exp_df["Tracking"] = has_tracking
    exp_df["Tracking source"] = tracking_source
    return exp_df


def render_subject_explorer(
    con: sqlite3.Connection,
    *,
    db_path: Path,
    workspace_root: Optional[str] = None,
    project_path: Optional[Path] = None,
) -> None:
    st.header("Subject Explorer")

    wdmoseq2_root: Optional[Path] = None
    if workspace_root:
        wdmoseq2_root = Path(workspace_root).parent
    if project_path:
        ed_root = project_path / "experiment_data"
        if not ed_root.is_dir() and wdmoseq2_root:
            ed_root = wdmoseq2_root / "data" / "experiment_data"
    elif wdmoseq2_root:
        ed_root = wdmoseq2_root / "data" / "experiment_data"
    else:
        ed_root = Path(".")

    summary_df = _subject_summary_from_db(con)
    if summary_df.empty:
        st.warning("No subjects found in the database. Run `mus1 import workspace-db-sync` first.")
        return

    # --- Sidebar: data refresh and sync note ---
    st.sidebar.caption("Counts come from mus1.db. After adding/moving experiment data, run: mus1 import workspace-db-sync")
    if st.sidebar.button("Refresh experiment data index", help="Clear 5-min cache of experiment_data JSON scan; next load rescans disk. Does not re-run DB sync."):
        _load_experiment_data_index.clear()
        st.rerun()

    # --- Sidebar filters ---
    st.sidebar.header("Filters")
    sex_opts = sorted(summary_df["Sex"].unique().tolist())
    sel_sex = st.sidebar.multiselect("Sex", sex_opts, default=sex_opts)
    geno_opts = sorted(summary_df["Genotype"].unique().tolist())
    sel_geno = st.sidebar.multiselect("Genotype", geno_opts, default=geno_opts)

    filtered = summary_df[
        summary_df["Sex"].isin(sel_sex) & summary_df["Genotype"].isin(sel_geno)
    ]

    # --- Overview table ---
    st.subheader(f"Subjects ({len(filtered)})")
    st.caption("Experiment counts per task type. Click a row to drill in.")

    def _color_cell(val: Any) -> str:
        if isinstance(val, (int, float)):
            if val == 0:
                return "color: #cc3333; font-weight: bold"
            if val >= 4:
                return "color: #228833"
        return ""

    count_cols = [c for c in TASK_ORDER + ["Total"] if c in filtered.columns]
    styler = filtered.style
    map_fn = getattr(styler, "map", None) or styler.applymap
    styled = map_fn(_color_cell, subset=count_cols)
    st.dataframe(styled, width="stretch", height=min(35 * len(filtered) + 40, 800))

    # --- Totals row ---
    totals = {t: int(filtered[t].sum()) for t in TASK_ORDER if t in filtered.columns}
    totals["Total"] = int(filtered["Total"].sum())
    cols = st.columns(len(TASK_ORDER) + 1)
    for i, t in enumerate(TASK_ORDER):
        cols[i].metric(t, totals.get(t, 0))
    cols[-1].metric("Total", totals["Total"])

    st.divider()

    # --- Subject detail ---
    subject_list = filtered["Subject"].tolist()
    if not subject_list:
        return
    selected = st.selectbox(
        "Select subject for detail view",
        subject_list,
        index=0,
    )
    if not selected:
        return

    subj_row = filtered[filtered["Subject"] == selected].iloc[0]
    c1, c2, c3, c4 = st.columns(4)
    c1.markdown(f"**Subject** {selected}")
    c2.markdown(f"**Sex** {subj_row['Sex']}")
    c3.markdown(f"**Genotype** {subj_row['Genotype']}")
    c4.markdown(f"**Birth date** {subj_row['Birth date']}")

    exp_df = _subject_experiments(con, selected)

    # Try loading experiment_data JSONs for enrichment
    ed_index: Dict[str, Dict[str, Any]] = {}
    if ed_root.is_dir():
        with st.spinner("Loading experiment data JSONs..."):
            ed_index = _load_experiment_data_index(str(ed_root))

    if not exp_df.empty and ed_index:
        exp_df = _enrich_with_experiment_data(exp_df, ed_index)

    # Group by experiment type (OF, EZM, NOR, NOF)
    for task in TASK_ORDER:
        if task == "RR":
            continue
        task_df = exp_df[exp_df["Type"] == task] if not exp_df.empty else pd.DataFrame()
        if task_df.empty:
            continue

        st.subheader(f"{task} ({len(task_df)} sessions)")
        display_cols = [c for c in task_df.columns if c != "Type"]
        st.dataframe(task_df[display_cols].reset_index(drop=True), width="stretch")

    # Rotarod from assay_sessions
    rr_df = _subject_rotarod_sessions(con, selected, ed_index)
    if not rr_df.empty:
        st.subheader(f"Rotarod ({len(rr_df)} sessions)")
        st.dataframe(rr_df.reset_index(drop=True), width="stretch")

    if exp_df.empty and rr_df.empty:
        st.info("No experiments found for this subject.")
        return

    st.divider()

    # --- Per-experiment artifact + assay detail ---
    exp_ids = exp_df["Experiment"].tolist() if not exp_df.empty else []
    if exp_ids:
        sel_exp = st.selectbox("Inspect experiment artifacts", exp_ids)
        if sel_exp:
            artifacts = _experiment_artifacts(con, sel_exp)
            if artifacts:
                st.markdown(f"**Artifacts for {sel_exp}** ({len(artifacts)} unique)")
                st.dataframe(pd.DataFrame(artifacts), width="stretch")
            else:
                st.caption("No artifacts in DB for this experiment.")

            assay_df = _experiment_assay_measurements(con, sel_exp)
            if not assay_df.empty:
                st.markdown(f"**Assay measurements for {sel_exp}**")
                st.dataframe(assay_df, width="stretch")
