from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

import streamlit as st

from ..db import fetchall, one_col
from ..io import parse_meta
from ..models import ExperimentRow
from ..paths import normalize_basename
from ..session_index import load_session_index_map


def list_experiments(
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
        MAX(CASE WHEN kind = 'nor_nof_objects_json_v2' THEN 1 ELSE 0 END) AS has_nor_nof_roi
      FROM external_artifacts
      GROUP BY experiment_id
    ) z ON z.experiment_id = e.id
    {where_sql}
    ORDER BY e.date_recorded DESC
    """

    rows = fetchall(con, sql, tuple(params))
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


def get_experiment_artifacts(con: sqlite3.Connection, experiment_id: str) -> List[sqlite3.Row]:
    sql = """
    SELECT id, kind, path, meta_json, created_at
    FROM external_artifacts
    WHERE experiment_id = ?
    ORDER BY kind ASC, created_at DESC
    """
    return fetchall(con, sql, (experiment_id,))


def get_experiment_qc(con: sqlite3.Connection, experiment_id: str) -> List[sqlite3.Row]:
    sql = """
    SELECT id, scope, code, details_json, created_at
    FROM qc_events
    WHERE experiment_id = ?
    ORDER BY created_at DESC
    """
    return fetchall(con, sql, (experiment_id,))


def get_annotation_qc(con: sqlite3.Connection) -> List[sqlite3.Row]:
    """
    Return QC events emitted by arena zone indexing that are not tied to an experiment.
    """
    sql = """
    SELECT id, scope, code, details_json, created_at
    FROM qc_events
    WHERE scope = 'annotation'
    ORDER BY created_at DESC
    """
    return fetchall(con, sql, ())


def update_external_artifact_linkage(
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


def delete_qc_event(con: sqlite3.Connection, qc_id: int) -> None:
    con.execute("DELETE FROM qc_events WHERE id = ?", (qc_id,))


def render_experiments(
    con: sqlite3.Connection,
    *,
    db_path: Path,
    workspace_root: Optional[str],
) -> None:
    st.sidebar.header("Filters")
    exp_types = one_col(con, "SELECT DISTINCT experiment_type FROM experiments ORDER BY experiment_type ASC")
    selected_types = st.sidebar.multiselect("Experiment type", options=exp_types, default=exp_types)
    only_ezm = st.sidebar.checkbox("Only with EZM zone JSON", value=False)
    only_nor_nof = st.sidebar.checkbox("Only with NOR/NOF ROI JSON", value=False)

    exps = list_experiments(
        con,
        experiment_types=selected_types,
        only_with_ezm_zone=only_ezm,
        only_with_nor_nof_roi=only_nor_nof,
    )

    st.caption(f"DB: `{db_path}`")
    st.caption(f"Experiments: {len(exps)}")

    with st.expander("Annotation QC (unlinked / errors)", expanded=False):
        ann_qc = get_annotation_qc(con)
        if not ann_qc:
            st.caption("No annotation QC events found.")
        else:
            index_map = load_session_index_map(workspace_root) if workspace_root else None
            rows = []
            for r in ann_qc[:300]:
                try:
                    details = json.loads(r["details_json"] or "{}")
                except Exception:
                    details = {"_raw": r["details_json"]}

                inferred_task = details.get("inferred_task")
                bn = normalize_basename(
                    details.get("video_basename")
                    or (Path(details["video_path"]).name if details.get("video_path") else None)
                )
                suggested_session_id = None
                suggested_video_path = None
                if index_map and inferred_task and bn:
                    hit = index_map.get((str(inferred_task), str(bn)))
                    if hit:
                        suggested_session_id = hit.get("session_id")
                        suggested_video_path = hit.get("video_path")

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

            relink_candidates = [r for r in rows if r.get("suggested_session_id") and r.get("zone_json") and r.get("kind")]
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
                        ok = update_external_artifact_linkage(
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
                            delete_qc_event(con, int(selected["id"]))
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

    exp_ids = [e.experiment_id for e in exps]
    selected_exp = st.selectbox("Select experiment", options=exp_ids) if exp_ids else None

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
    artifacts = get_experiment_artifacts(con, selected_exp)
    qc = get_experiment_qc(con, selected_exp)

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("#### External artifacts")
        if not artifacts:
            st.info("No external artifacts linked to this experiment.")
        else:
            by_kind: Dict[str, List[sqlite3.Row]] = {}
            for r in artifacts:
                by_kind.setdefault(str(r["kind"]), []).append(r)

            for kind, items in by_kind.items():
                with st.expander(
                    f"{kind} ({len(items)})",
                    expanded=(kind in {"ezm_zone_json_v2", "nor_nof_objects_json_v2"}),
                ):
                    for it in items[:200]:
                        st.code(str(it["path"]), language=None)
                        meta = parse_meta(it["meta_json"])
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

