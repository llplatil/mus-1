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
import sqlite3
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

