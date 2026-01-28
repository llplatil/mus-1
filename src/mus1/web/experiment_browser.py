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


def main() -> None:
    st.set_page_config(page_title="MUS1 Experiment Browser", layout="wide")
    st.title("MUS1 Experiment Browser")

    st.sidebar.header("Database")
    args = _parse_args()
    default_project = args.project_path or str(Path.cwd())
    project_path_str = st.sidebar.text_input("Project path (contains mus1.db)", value=str(default_project))
    project_path = Path(project_path_str).expanduser()
    db_path = project_path / "mus1.db"

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
            # Show a small, readable table view.
            rows = []
            for r in ann_qc[:300]:
                try:
                    details = json.loads(r["details_json"] or "{}")
                except Exception:
                    details = {"_raw": r["details_json"]}
                rows.append(
                    {
                        "id": r["id"],
                        "code": r["code"],
                        "created_at": r["created_at"],
                        "zone_json": details.get("zone_json") or details.get("path"),
                        "video_path": details.get("video_path"),
                        "kind": details.get("kind"),
                        "error": details.get("error"),
                    }
                )
            st.dataframe(rows, use_container_width=True, hide_index=True)

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
        use_container_width=True,
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

