from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import streamlit as st

from ..slurm import sacct, scontrol_node, squeue, sstat
from ..utils import run_cmd, tail_text


@st.cache_data(show_spinner=False)
def list_run_dirs_from_db(db_path: str, *, kind: str, limit: int = 500) -> List[Dict[str, Any]]:
    """
    List run output dirs from the MUS1 DB.

    Runs are stored as external_artifacts with kind='<kind>_run_dir'.
    """
    try:
        import sqlite3

        con = sqlite3.connect(str(db_path))
        con.row_factory = sqlite3.Row
        rows = con.execute(
            """
            SELECT path, meta_json, created_at
            FROM external_artifacts
            WHERE kind = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (str(kind), int(limit)),
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
        try:
            meta = json.loads(r["meta_json"] or "{}")
        except Exception:
            meta = {}
        rs = p / "run_status.json"
        try:
            st_mtime = rs.stat().st_mtime if rs.exists() else p.stat().st_mtime
        except Exception:
            st_mtime = 0.0
        out.append(
            {
                "run_path": str(p),
                "name": p.name,
                "created_at": str(r["created_at"]),
                "mtime": float(st_mtime),
                "has_metrics": (p / "metrics.csv").exists(),
                "has_by_exposure": (p / "metrics_by_exposure.csv").exists(),
                "meta": meta,
            }
        )
    out.sort(key=lambda r: float(r.get("mtime", 0.0)), reverse=True)
    return out


def _infer_log_path(*, repo_root: Path, job_id: str, kind: str) -> Optional[Path]:
    jid = str(job_id or "").strip()
    if not jid.isdigit():
        return None
    if kind == "ezm_unet":
        p = repo_root / "logs" / f"ezm_unet_augfix_{jid}.out"
        return p if p.exists() else None
    if kind == "ml_tracking":
        p = repo_root / "logs" / f"train_sess_eval_long_{jid}.out"
        return p if p.exists() else None
    return None


def _log_candidates_for_job(*, repo_root: Path, job_id: str) -> List[Path]:
    """
    Return existing log file paths for a slurm job id, preferring known patterns.
    """
    jid = str(job_id or "").strip()
    if not jid.isdigit():
        return []

    logs_dir = repo_root / "logs"
    out: List[Path] = []

    for kind in ("ezm_unet", "ml_tracking"):
        p = _infer_log_path(repo_root=repo_root, job_id=jid, kind=kind)
        if p is not None and p.exists():
            out.append(p)

    # Generic fallbacks within repo_root/logs only (safe, small).
    try:
        if logs_dir.exists():
            for pat in (f"*_{jid}.out", f"*_{jid}.err"):
                for p in sorted(list(logs_dir.glob(pat))):
                    if p.exists() and p not in out:
                        out.append(p)
    except Exception:
        pass

    return out


def _read_json(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def _tail_with_mtime(path: Path, *, max_lines: int) -> Dict[str, Any]:
    try:
        st_mtime = float(path.stat().st_mtime)
        st_size = int(path.stat().st_size)
    except Exception:
        st_mtime = 0.0
        st_size = 0
    return {
        "path": str(path),
        "mtime": st_mtime,
        "size_bytes": st_size,
        "tail": tail_text(path, max_lines=max_lines) or "",
    }


def _parse_ezm_unet_epochs(log_text: str) -> List[Dict[str, float]]:
    """
    Parse EZM U-Net epoch summary lines of the form:
      epoch 017 train_loss=0.1977 val_loss=0.4492 val_acc=0.8904 miou_open_closed=0.4033
    """
    rows: List[Dict[str, float]] = []
    rx = re.compile(
        r"^epoch\s+(?P<epoch>\d+)\s+train_loss=(?P<train_loss>[-+0-9.eE]+)\s+val_loss=(?P<val_loss>[-+0-9.eE]+)\s+val_acc=(?P<val_acc>[-+0-9.eE]+)\s+miou_open_closed=(?P<miou>[-+0-9.eE]+)\s*$"
    )
    for line in (log_text or "").splitlines():
        m = rx.match(line.strip())
        if not m:
            continue
        try:
            rows.append(
                {
                    "epoch": float(m.group("epoch")),
                    "train_loss": float(m.group("train_loss")),
                    "val_loss": float(m.group("val_loss")),
                    "val_acc": float(m.group("val_acc")),
                    "miou_open_closed": float(m.group("miou")),
                }
            )
        except Exception:
            continue
    return rows


def render_training_monitor(*, project_path: Path, workspace_root: Optional[str]) -> None:
    st.header("Training Monitor")
    st.caption("Read-only monitoring of Slurm jobs and training run outputs (EZM U-Net + ML tracking).")
    project_path = Path(project_path)
    repo_root = Path(__file__).resolve().parents[4]

    try:
        import pandas as pd  # type: ignore
    except Exception:
        st.error("This view requires `pandas` (missing in the current environment).")
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
    jobs = squeue(user)
    st.dataframe(jobs, width="stretch", hide_index=True)

    jobids = [j["jobid"] for j in jobs if str(j.get("jobid", "")).isdigit()]
    selected_job = st.selectbox("Inspect job", options=(["(none)"] + jobids), index=0)
    if selected_job != "(none)":
        st.markdown("#### Job accounting (sacct)")
        st.code(sacct(selected_job) or "(no output)")
        st.markdown("#### Live usage (sstat)")
        st.code(sstat(selected_job) or "(no output)")
        # Extract node name if present in nodelist_reason like "n144" or "(Priority)".
        nodelist = next((j.get("nodelist_reason", "") for j in jobs if j.get("jobid") == selected_job), "")
        node = ""
        for tok in str(nodelist).replace(",", " ").split():
            if tok.startswith("n") and tok[1:].isdigit():
                node = tok
                break
        if node:
            st.markdown(f"#### Node snapshot (`{node}`)")
            st.code(scontrol_node(node) or "(no output)")

        with st.expander("Job log tail (auto)", expanded=True):
            cands = _log_candidates_for_job(repo_root=repo_root, job_id=selected_job)
            if not cands:
                st.info("No log files found under `repo_root/logs` for this job yet.")
            else:
                label_to_path = {str(p): p for p in cands}
                chosen = st.selectbox("Log file", options=list(label_to_path.keys()), index=0, key="mus1_tm_job_log_choice")
                p = label_to_path.get(chosen)
                if p is not None and p.exists():
                    payload = _tail_with_mtime(p, max_lines=260)
                    st.caption(f"log: `{payload['path']}`  size={payload['size_bytes']:,}  mtime={payload['mtime']:.0f}")
                    st.code(payload["tail"] or "(empty)")
                    # If this looks like an EZM U-Net log, parse learning signal from the tail.
                    rows = _parse_ezm_unet_epochs(payload["tail"])
                    if rows:
                        import pandas as pd  # type: ignore

                        df = pd.DataFrame(rows).sort_values("epoch", kind="mergesort")
                        st.markdown("#### EZM U-Net learning signal (from log tail)")
                        cols = st.columns(2)
                        with cols[0]:
                            st.line_chart(df.set_index("epoch")[["val_acc", "miou_open_closed"]], height=180)
                        with cols[1]:
                            st.line_chart(df.set_index("epoch")[["train_loss", "val_loss"]], height=180)
                        last = df.tail(1).to_dict(orient="records")[0]
                        st.caption(
                            f"latest: epoch={int(last.get('epoch', 0))}  "
                            f"val_acc={last.get('val_acc', float('nan')):.4f}  "
                            f"miou_open_closed={last.get('miou_open_closed', float('nan')):.4f}"
                        )

    db_path = project_path / "mus1.db"
    if not db_path.exists():
        st.error(f"mus1.db not found at: {db_path}")
        st.stop()

    st.subheader("EZM arena detection runs (U-Net)")
    ezm_runs_root = project_path / "runs" / "ezm_unet"
    ezm_runs = list_run_dirs_from_db(str(db_path), kind="ezm_unet_run_dir", limit=500)

    with st.expander("Index / re-index EZM U-Net runs into the DB", expanded=(not bool(ezm_runs))):
        st.caption("This is safe to run repeatedly; it will skip runs already present in the DB.")
        st.caption("Expected runs root:")
        st.code(str(ezm_runs_root), language=None)
        if not workspace_root:
            st.code(f"mus1 import ezm-unet-runs --project-path \"{project_path}\" --workspace-root <REQUIRED>", language=None)
            st.warning("Provide `--workspace-root` when launching the web app to enable run indexing from the UI.")
        else:
            only_latest = st.checkbox("Only index latest EZM U-Net run", value=False, key="mus1_index_ezm_only_latest")
            if st.button("Index EZM U-Net runs into DB now", type="primary", key="mus1_index_ezm_btn"):
                cmd = [
                    "mus1",
                    "import",
                    "ezm-unet-runs",
                    "--project-path",
                    str(project_path),
                    "--workspace-root",
                    str(workspace_root),
                ]
                if bool(only_latest):
                    cmd.append("--only-latest")
                with st.spinner("Indexing EZM U-Net runs…"):
                    rc, out, err = run_cmd(cmd)
                st.code(" ".join(cmd), language=None)
                st.code(out or "(no stdout)", language=None)
                if err:
                    st.code(err, language=None)
                if rc == 0:
                    st.success("Indexed. Refreshing.")
                    st.cache_data.clear()
                    st.rerun()
                else:
                    st.error(f"Indexing failed (exit={rc}).")

    # Refresh after possible indexing rerun.
    ezm_runs = list_run_dirs_from_db(str(db_path), kind="ezm_unet_run_dir", limit=500)
    if not ezm_runs:
        st.info("No EZM U-Net runs indexed in this project DB yet.")
        st.stop()

    ezm_labels = [f"{r['name']}  {r['run_path']}" for r in ezm_runs[:200]]
    ezm_choice = st.selectbox("Select EZM U-Net run", options=ezm_labels, index=0, key="mus1_tm_ezm_choice")
    ezm_run = next(r for r in ezm_runs if f"{r['name']}  {r['run_path']}" == ezm_choice)
    ezm_dir = Path(str(ezm_run["run_path"]))
    st.caption(f"Run dir: `{ezm_dir}`")
    ezm_status = _read_json(ezm_dir / "run_status.json") if (ezm_dir / "run_status.json").exists() else {}
    with st.expander("run_status.json", expanded=False):
        st.json(ezm_status, expanded=False)
    ezm_slurm: Dict[str, Any] = {}
    if (ezm_dir / "slurm.json").exists():
        ezm_slurm = _read_json(ezm_dir / "slurm.json")
        with st.expander("slurm.json", expanded=False):
            st.json(ezm_slurm, expanded=False)

    # Auto log tail from job_id (so you don't have to hunt logs/*.out)
    ezm_job_id = str(ezm_status.get("job_id") or ezm_slurm.get("job_id") or "")
    ezm_log = _infer_log_path(repo_root=repo_root, job_id=ezm_job_id, kind="ezm_unet")
    if str(ezm_job_id).strip().isdigit():
        with st.expander("Slurm job (from run_status/slurm.json)", expanded=False):
            st.caption(f"job_id: `{ezm_job_id}`")
            st.code(sacct(ezm_job_id) or "(no output)")
            st.code(sstat(ezm_job_id) or "(no output)")
    with st.expander("Training log tail (auto)", expanded=True):
        cands = _log_candidates_for_job(repo_root=repo_root, job_id=ezm_job_id) if str(ezm_job_id).strip().isdigit() else []
        if cands:
            # Prefer the known ezm-unet pattern if present.
            preferred = str(ezm_log) if (ezm_log and ezm_log.exists()) else str(cands[0])
            label_to_path = {str(p): p for p in cands}
            if preferred not in label_to_path:
                preferred = str(cands[0])
            chosen = st.selectbox(
                "Log file",
                options=list(label_to_path.keys()),
                index=list(label_to_path.keys()).index(preferred),
                key="mus1_tm_ezm_log_choice",
            )
            p = label_to_path.get(chosen)
        else:
            p = ezm_log if (ezm_log and ezm_log.exists()) else None

        if p is not None and p.exists():
            payload = _tail_with_mtime(p, max_lines=260)
            st.caption(f"log: `{payload['path']}`  size={payload['size_bytes']:,}")
            st.code(payload["tail"] or "(empty)")
            # Parse learning signal from the tail (fast, avoids full-file reads).
            rows = _parse_ezm_unet_epochs(payload["tail"] or "")
            if rows:
                import pandas as pd  # type: ignore

                df = pd.DataFrame(rows).sort_values("epoch", kind="mergesort")
                st.markdown("#### Learning signal (from log tail)")
                cols = st.columns(2)
                with cols[0]:
                    st.line_chart(df.set_index("epoch")[["val_acc", "miou_open_closed"]], height=180)
                with cols[1]:
                    st.line_chart(df.set_index("epoch")[["train_loss", "val_loss"]], height=180)
        else:
            st.info("Could not infer log path yet (run_status.json missing job_id, or log not written yet).")

    qc_dir = ezm_dir / "qc_overlays"
    if qc_dir.exists():
        pngs = sorted(list(qc_dir.glob("*.png")))
        st.caption(f"QC overlays: `{qc_dir}`  (pngs={len(pngs)})")
        if pngs:
            with st.expander("QC overlay quick peek (first 6)", expanded=False):
                st.image([str(p) for p in pngs[:6]], width="stretch")

    st.divider()
    st.subheader("ML tracking runs (what it learned)")
    ml_runs_root = project_path / "runs" / "ml_tracking"
    ml_runs = list_run_dirs_from_db(str(db_path), kind="ml_tracking_run_dir", limit=500)
    with st.expander("Index / re-index ML tracking runs into the DB", expanded=(not bool(ml_runs))):
        st.caption("This is safe to run repeatedly; it will skip runs already present in the DB.")
        st.caption("Expected runs root:")
        st.code(str(ml_runs_root), language=None)
        only_latest = st.checkbox("Only index latest ML tracking run", value=False, key="mus1_index_ml_only_latest")
        if st.button("Index ML tracking runs into DB now", type="primary", key="mus1_index_ml_btn"):
            cmd = ["mus1", "import", "ml-tracking-runs", "--project-path", str(project_path)]
            if bool(only_latest):
                cmd.append("--only-latest")
            with st.spinner("Indexing ML tracking runs…"):
                rc, out, err = run_cmd(cmd)
            st.code(" ".join(cmd), language=None)
            st.code(out or "(no stdout)", language=None)
            if err:
                st.code(err, language=None)
            if rc == 0:
                st.success("Indexed. Refreshing.")
                st.cache_data.clear()
                st.rerun()
            else:
                st.error(f"Indexing failed (exit={rc}).")

    # Refresh after possible indexing rerun.
    ml_runs = list_run_dirs_from_db(str(db_path), kind="ml_tracking_run_dir", limit=500)
    if not ml_runs:
        st.info("No ML tracking runs indexed in this project DB yet.")
        st.stop()

    run_labels = [f"{r['name']}  ({'metrics' if r['has_metrics'] else 'no-metrics'})  {r['run_path']}" for r in ml_runs[:200]]
    choice = st.selectbox("Select run output dir", options=run_labels, index=0)
    run = next(r for r in ml_runs if f"{r['name']}  ({'metrics' if r['has_metrics'] else 'no-metrics'})  {r['run_path']}" == choice)
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
            cols = st.columns(2)
            for i, tgt in enumerate(["sex", "genotype"]):
                sub = mdf[mdf["target"].astype(str) == tgt].sort_values("repeat", kind="mergesort")
                with cols[i]:
                    st.caption(f"target: `{tgt}`")
                    if sub.empty:
                        st.info("No rows yet.")
                    else:
                        st.line_chart(sub.set_index("repeat")["value"], height=160)
        with st.expander("metrics.csv (tail)", expanded=False):
            st.code(tail_text(metrics_path, max_lines=120) or "(empty)")
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
            st.code(tail_text(byexp_path, max_lines=120) or "(empty)")

    st.subheader("Log tail")
    job_id = str(status.get("job_id") or "")
    logp = _infer_log_path(repo_root=repo_root, job_id=job_id, kind="ml_tracking")
    if str(job_id).strip().isdigit():
        with st.expander("Slurm job (from run_status.json)", expanded=False):
            st.caption(f"job_id: `{job_id}`")
            st.code(sacct(job_id) or "(no output)")
            st.code(sstat(job_id) or "(no output)")

    cands = _log_candidates_for_job(repo_root=repo_root, job_id=job_id) if str(job_id).strip().isdigit() else []
    if cands:
        preferred = str(logp) if (logp and logp.exists()) else str(cands[0])
        label_to_path = {str(p): p for p in cands}
        if preferred not in label_to_path:
            preferred = str(cands[0])
        chosen = st.selectbox(
            "Log file",
            options=list(label_to_path.keys()),
            index=list(label_to_path.keys()).index(preferred),
            key="mus1_tm_ml_log_choice",
        )
        p = label_to_path.get(chosen)
    else:
        p = logp if (logp and logp.exists()) else None

    if p is not None and p.exists():
        st.caption(f"log: `{p}`")
        st.code(tail_text(p, max_lines=220) or "(empty)")
    else:
        st.info("Could not infer log path yet (run_status.json missing job_id, or log not written yet).")

    with st.expander("Custom log tail (optional)", expanded=False):
        default_log = str((repo_root / "logs").resolve())
        log_path_str = st.text_input(
            "Path to a log file to tail (absolute path recommended)",
            value="",
            help=f"Example: `{default_log}/train_sess_eval_long_<jobid>.out`",
        )
        if log_path_str.strip():
            p = Path(log_path_str.strip()).expanduser()
            # Safety: ensure within project or repo root
            try:
                pr = Path(project_path).resolve()
                rr = Path(repo_root).resolve()
                if (pr not in p.parents and p != pr) and (rr not in p.parents and p != rr):
                    st.error("Refusing to read a path outside the project/repo root.")
                elif p.exists():
                    st.code(tail_text(p, max_lines=200) or "(empty)")
                else:
                    st.warning(f"Not found: {p}")
            except Exception as e:
                st.error(f"Path error: {e}")

