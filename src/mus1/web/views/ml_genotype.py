"""ML Genotype Prediction — dataset building, training, monitoring & QC."""
from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import streamlit as st

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ml_dir(workspace_root: str) -> Path:
    return Path(workspace_root) / "ml_workspace" / "ml_tracking_metadata_model"

def _read_json(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}

@st.cache_data(ttl=60)
def _load_cohort_summary(workspace_root: str, cohort_name: str) -> Optional[Dict]:
    path = Path(workspace_root) / "data" / "cohorts" / f"{cohort_name}.json"
    if not path.exists():
        return None
    return _read_json(path).get("summary")

def _list_dirs(parent: Path) -> List[str]:
    """Directory names under *parent*, newest-first by mtime."""
    if not parent.is_dir():
        return []
    dirs = sorted(
        [d for d in parent.iterdir() if d.is_dir()],
        key=lambda d: d.stat().st_mtime, reverse=True,
    )
    return [d.name for d in dirs]

def _list_yaml_configs(ml_root: Path) -> List[str]:
    cfg_dir = ml_root / "configs"
    if not cfg_dir.is_dir():
        return []
    return sorted(f.name for f in cfg_dir.iterdir() if f.suffix in (".yaml", ".yml"))

@st.cache_data(ttl=30)
def _squeue_ml_jobs() -> str:
    try:
        result = subprocess.run(
            ["squeue", "-u", os.environ.get("USER", ""),
             "--name=ml_train,ml_train_gpu,ml_build_ds",
             "-o", "%i %j %T %M %l %P"],
            capture_output=True, text=True, timeout=10,
        )
        return result.stdout.strip() if result.returncode == 0 else result.stderr.strip()
    except Exception as exc:
        return f"squeue error: {exc}"

def _tail_file(path: Path, n: int = 50) -> str:
    try:
        return "\n".join(path.read_text().splitlines()[-n:])
    except Exception:
        return ""

# Cohort definitions: (display_label, cohort_json_stem, task_type_filter)
_COHORT_DEFS = [
    ("EZM", "ezm_publication", None),
    ("NOR", "nor_nof_publication", "NOR"),
    ("NOF", "nor_nof_publication", "NOF"),
    ("OF",  "of_publication", None),
    ("RR",  "rr_publication", None),
]

def _cohort_experiment_count(summary: Optional[Dict], task_filter: Optional[str]) -> int:
    if summary is None:
        return 0
    if task_filter:
        return summary.get("task_type_counts", {}).get(task_filter, 0)
    return summary.get("n_experiments", 0)

# ---------------------------------------------------------------------------
# Tab 1: Dataset Build
# ---------------------------------------------------------------------------

def _render_dataset_build(workspace_root: str, ml_root: Path):
    st.subheader("Dataset Configuration")

    # Cohort checkboxes with experiment counts
    st.markdown("**Cohorts**")
    selected_tasks: List[str] = []
    cols = st.columns(len(_COHORT_DEFS))
    for col, (label, cohort_name, task_filter) in zip(cols, _COHORT_DEFS):
        summary = _load_cohort_summary(workspace_root, cohort_name)
        n = _cohort_experiment_count(summary, task_filter)
        with col:
            if st.checkbox(f"{label} ({n})", value=(label != "RR"), key=f"cohort_{label}"):
                selected_tasks.append(label)

    # Feature tier checkboxes
    st.markdown("**Feature tiers**")
    fc1, fc2, fc3, fc4 = st.columns(4)
    with fc1:
        use_kin = st.checkbox("Kinematics (DLC/MoSeq2)", value=True)
    with fc2:
        use_meta = st.checkbox("Metadata (age, sex, tp, task)")
    with fc3:
        use_rr = st.checkbox("RR data")
    with fc4:
        use_syl = st.checkbox("Syllable temporal sequences")

    # Syllable config (conditional)
    syl_ezm_kpms = syl_of_moseq2 = False
    syl_encoder_type = "lstm"
    if use_syl:
        st.markdown("**Syllable configuration**")
        sc1, sc2, sc3 = st.columns(3)
        with sc1:
            syl_ezm_kpms = st.checkbox("EZM KPMS", value=True)
        with sc2:
            syl_of_moseq2 = st.checkbox("OF MoSeq2", value=True)
        with sc3:
            syl_encoder_type = st.selectbox("Encoder type", ["lstm", "transformer"])

    # Subject exclusion
    exclude_str = st.text_input(
        "Exclude subjects (comma-separated IDs)", value="444,445",
        help="Subjects to exclude from the dataset.",
    )
    exclude_ids = [s.strip() for s in exclude_str.split(",") if s.strip()]

    # Preview
    if st.button("Preview"):
        total = 0
        geno_totals: Dict[str, int] = {}
        for label, cohort_name, task_filter in _COHORT_DEFS:
            if label not in selected_tasks:
                continue
            summary = _load_cohort_summary(workspace_root, cohort_name)
            n = _cohort_experiment_count(summary, task_filter)
            st.write(f"- **{label}**: {n} experiments")
            total += n
            if summary:
                for grp, cnt in summary.get("groups", {}).items():
                    geno = grp.split("_")[0]
                    geno_totals[geno] = geno_totals.get(geno, 0) + cnt
        st.write(f"**Total**: {total} experiments")
        if geno_totals:
            st.write("**Genotype distribution**: " +
                     ", ".join(f"{g}: {c}" for g, c in sorted(geno_totals.items())))

    # Build Dataset
    st.divider()
    run_name = st.text_input("Run name prefix", value="custom_build")
    if st.button("Build Dataset", type="primary"):
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        cfg_name = f"{run_name}_{ts}.yaml"
        cfg = _generate_config(
            run_name=run_name, selected_tasks=selected_tasks,
            use_kin=use_kin, use_meta=use_meta, use_rr=use_rr,
            use_syl=use_syl, syl_ezm_kpms=syl_ezm_kpms,
            syl_of_moseq2=syl_of_moseq2, syl_encoder_type=syl_encoder_type,
            exclude_ids=exclude_ids,
        )
        try:
            import yaml
            (ml_root / "configs" / cfg_name).write_text(
                yaml.dump(cfg, default_flow_style=False, sort_keys=False))
        except Exception as exc:
            st.error(f"Failed to write config: {exc}")
            return
        result = subprocess.run(
            ["sbatch", "slurm/build_dataset.sbatch", f"configs/{cfg_name}"],
            capture_output=True, text=True, cwd=str(ml_root),
        )
        if result.returncode == 0:
            st.success(f"Config written: `configs/{cfg_name}`")
            st.info(result.stdout.strip())
        else:
            st.error(f"sbatch failed: {result.stderr.strip()}")

    # Existing Datasets browser
    st.divider()
    st.subheader("Existing Datasets")
    ds_names = _list_dirs(ml_root / "datasets")
    if not ds_names:
        st.info("No datasets built yet.")
    else:
        chosen_ds = st.selectbox("Dataset", ds_names, key="ds_browse")
        if chosen_ds:
            manifest = _read_json(ml_root / "datasets" / chosen_ds / "manifest.json")
            if manifest:
                st.json(manifest)
            else:
                st.warning("No manifest.json found.")


def _generate_config(
    *, run_name, selected_tasks, use_kin, use_meta, use_rr,
    use_syl, syl_ezm_kpms, syl_of_moseq2, syl_encoder_type, exclude_ids,
) -> Dict[str, Any]:
    """Build a YAML-serialisable config dict from UI selections."""
    task_map = {
        "EZM": {"cohort": "ezm_publication", "tracking_source": "dlc"},
        "NOR": {"cohort": "nor_nof_publication", "task_filter": "NOR", "tracking_source": "dlc"},
        "NOF": {"cohort": "nor_nof_publication", "task_filter": "NOF", "tracking_source": "dlc"},
        "OF":  {"cohort": "of_publication", "tracking_source": "moseq2"},
        "RR":  {"cohort": "rr_publication", "tracking_source": "rr"},
    }
    meta_features = ["age_in_days", "sex", "timepoint", "task_type"] if use_meta else []
    return {
        "run_name": run_name,
        "seed": 42,
        "val_frac": 0.20,
        "n_repeats": 1,
        "dataset": {
            "metadata_features": meta_features,
            "exclude_subjects": exclude_ids,
            "tasks": {t: task_map[t] for t in selected_tasks if t in task_map},
        },
        "model": {
            "n_classes": 3,
            "kin_encoder": {"enabled": use_kin},
            "pose_encoder": {"enabled": use_kin},
            "syl_encoder": {
                "enabled": use_syl, "encoder_type": syl_encoder_type,
                "ezm_kpms": syl_ezm_kpms, "of_moseq2": syl_of_moseq2,
            },
            "meta_encoder": {"enabled": use_meta},
            "rr_encoder": {"enabled": use_rr},
        },
        "training": {
            "epochs": 100, "batch_size": 32, "lr": 3.0e-4,
            "weight_decay": 1.0e-3, "patience": 15, "device": "cpu",
        },
    }

# ---------------------------------------------------------------------------
# Tab 2: Training
# ---------------------------------------------------------------------------

def _render_training(ml_root: Path):
    st.subheader("Submit Training Run")

    ds_names = _list_dirs(ml_root / "datasets")
    if not ds_names:
        st.warning("No datasets available. Build one in the Dataset tab first.")
        return

    dataset_choice = st.selectbox("Dataset", ds_names, key="train_ds")
    config_files = _list_yaml_configs(ml_root)
    config_choice = st.selectbox("Config preset", config_files, key="train_cfg")

    st.markdown("**Hyperparameter overrides** (leave at 0 to use config defaults)")
    hc1, hc2, hc3 = st.columns(3)
    with hc1:
        lr_override = st.number_input("Learning rate", value=0.0, format="%.1e",
                                      help="0 = use config default")
        epochs_override = st.number_input("Epochs", value=0, min_value=0, step=10,
                                          help="0 = use config default")
    with hc2:
        bs_override = st.number_input("Batch size", value=0, min_value=0, step=8,
                                      help="0 = use config default")
        val_frac_override = st.number_input("Val fraction", value=0.0, min_value=0.0,
                                            max_value=0.5, step=0.05,
                                            help="0 = use config default")
    with hc3:
        patience_override = st.number_input("Patience", value=0, min_value=0, step=5,
                                            help="0 = use config default")

    partition = st.selectbox("Compute partition", ["bio", "t1small", "l40s", "h100"],
                             key="train_partition")

    if st.button("Submit Training", type="primary"):
        config_arg = f"configs/{config_choice}"
        overrides = {}
        if lr_override > 0:
            overrides["lr"] = lr_override
        if epochs_override > 0:
            overrides["epochs"] = epochs_override
        if bs_override > 0:
            overrides["batch_size"] = bs_override
        if val_frac_override > 0:
            overrides["val_frac"] = val_frac_override
        if patience_override > 0:
            overrides["patience"] = patience_override

        if overrides:
            try:
                import yaml
                cfg = yaml.safe_load((ml_root / "configs" / config_choice).read_text())
                tb = cfg.setdefault("training", {})
                for k, v in overrides.items():
                    (cfg if k == "val_frac" else tb)[k] = v
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                mod_name = f"_modified_{ts}.yaml"
                (ml_root / "configs" / mod_name).write_text(
                    yaml.dump(cfg, default_flow_style=False, sort_keys=False))
                config_arg = f"configs/{mod_name}"
                st.info(f"Wrote modified config: `{config_arg}`")
            except Exception as exc:
                st.error(f"Failed to write modified config: {exc}")
                return

        is_gpu = partition in ("l40s", "h100")
        sbatch_script = "slurm/train_gpu.sbatch" if is_gpu else "slurm/train_cpu.sbatch"
        cmd = ["sbatch", f"--partition={partition}", sbatch_script,
               config_arg, f"datasets/{dataset_choice}"]
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ml_root))
        if result.returncode == 0:
            st.success(result.stdout.strip())
        else:
            st.error(f"sbatch failed: {result.stderr.strip()}")

    # Active SLURM jobs
    st.divider()
    st.subheader("Active SLURM Jobs")
    if st.button("Refresh", key="refresh_squeue"):
        st.cache_data.clear()
    jobs_text = _squeue_ml_jobs()
    if jobs_text:
        st.code(jobs_text, language="text")
    else:
        st.info("No active ML jobs.")

# ---------------------------------------------------------------------------
# Tab 3: Monitor & QC
# ---------------------------------------------------------------------------

def _render_monitor(ml_root: Path):
    st.subheader("Run Browser")

    run_names = _list_dirs(ml_root / "runs")
    if not run_names:
        st.info("No training runs found.")
        return

    selected_run = st.selectbox("Run", run_names, key="mon_run")
    if not selected_run:
        return

    run_dir = ml_root / "runs" / selected_run
    status_data = _read_json(run_dir / "run_status.json")
    status = status_data.get("status", "UNKNOWN").upper()

    # Status badge
    badge_colour = {"RUNNING": "orange", "COMPLETE": "green", "FAILED": "red"}.get(status, "gray")
    st.markdown(f"**Status:** :{badge_colour}[{status}]")

    mc = st.columns(4)
    mc[0].metric("Best bal. acc", f"{status_data.get('best_genotype_bal_acc', 0):.3f}")
    mc[1].metric("Best epoch", status_data.get("best_epoch", "-"))
    mc[2].metric("Train subjects", status_data.get("n_train_subjects", "-"))
    mc[3].metric("Val subjects", status_data.get("n_val_subjects", "-"))

    # Config expander
    cfg_path = run_dir / "config.yaml"
    if cfg_path.exists():
        with st.expander("Config"):
            st.code(cfg_path.read_text(), language="yaml")

    # Learning curves
    metrics_path = run_dir / "metrics.csv"
    if metrics_path.exists():
        _render_learning_curves(metrics_path)
    else:
        st.info("No metrics.csv yet.")

    # Confusion matrix
    cm_path = run_dir / "eval" / "confusion_matrix.png"
    if cm_path.exists():
        st.subheader("Confusion Matrix")
        st.image(str(cm_path))

    # Per-subject accuracy
    subj_path = run_dir / "eval" / "per_subject_accuracy.csv"
    if subj_path.exists():
        import pandas as pd
        st.subheader("Per-Subject Accuracy")
        st.dataframe(pd.read_csv(subj_path), use_container_width=True)

    # Per-task accuracy
    task_path = run_dir / "eval" / "per_task_accuracy.csv"
    if task_path.exists():
        import pandas as pd
        st.subheader("Per-Task Accuracy")
        st.dataframe(pd.read_csv(task_path), use_container_width=True)

    # Log tail
    job_id = str(status_data.get("job_id", "")).strip()
    if job_id:
        for suffix in (f"train_{job_id}.log", f"train_gpu_{job_id}.log",
                       f"train_{job_id}.out", f"train_gpu_{job_id}.out"):
            lp = ml_root / "logs" / suffix
            if lp.exists():
                with st.expander(f"Log tail: {lp.name}"):
                    st.code(_tail_file(lp, 50), language="text")
                break

    # Run comparison
    st.divider()
    st.subheader("Run Comparison")
    compare_runs = st.multiselect("Select runs to compare", run_names, key="mon_compare")
    if len(compare_runs) >= 2:
        _render_comparison(ml_root, compare_runs)


def _render_learning_curves(metrics_path: Path):
    import pandas as pd
    st.subheader("Learning Curves")
    try:
        df = pd.read_csv(metrics_path)
    except Exception as exc:
        st.error(f"Failed to read metrics: {exc}")
        return
    if df.empty:
        st.info("Metrics file is empty.")
        return
    # Val balanced accuracy
    val_df = df[df["split"] == "val"]
    if not val_df.empty:
        st.markdown("**Validation balanced accuracy**")
        st.line_chart(val_df.set_index("epoch")[["genotype_bal_acc"]])
    # Loss: train and val
    st.markdown("**Loss (train & val)**")
    pivot = df.pivot_table(index="epoch", columns="split", values="loss", aggfunc="mean")
    if not pivot.empty:
        st.line_chart(pivot)


def _render_comparison(ml_root: Path, run_names: List[str]):
    import pandas as pd
    frames = []
    for name in run_names:
        mp = ml_root / "runs" / name / "metrics.csv"
        if not mp.exists():
            continue
        try:
            df = pd.read_csv(mp)
            val = df[df["split"] == "val"][["epoch", "genotype_bal_acc"]].copy()
            val = val.rename(columns={"genotype_bal_acc": name}).set_index("epoch")
            frames.append(val)
        except Exception:
            continue
    if not frames:
        st.warning("No metrics data for selected runs.")
        return
    st.markdown("**Val balanced accuracy comparison**")
    st.line_chart(pd.concat(frames, axis=1))

# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def render_ml_genotype(*, project_path=None, workspace_root=None):
    st.header("ML Genotype Prediction")
    st.caption("Build datasets, train models, and evaluate genotype classifiers.")

    if workspace_root is None:
        st.error("workspace_root is required.")
        return

    ml_root = _ml_dir(workspace_root)
    if not ml_root.is_dir():
        st.error(f"ML workspace not found: `{ml_root}`")
        return

    tab_ds, tab_train, tab_monitor = st.tabs(
        ["Dataset Build", "Training", "Monitor & QC"]
    )
    with tab_ds:
        _render_dataset_build(workspace_root, ml_root)
    with tab_train:
        _render_training(ml_root)
    with tab_monitor:
        _render_monitor(ml_root)
