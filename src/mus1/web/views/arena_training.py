"""Arena Training — profile-parameterized training lifecycle pane.

T11 (ROADMAP Iteration 6 follow-on). Gives operators a single pane to:

  1. **See the training-set state** for any arena profile: how many
     experiments have manual arena markings ready to feed into a U-Net
     training run; how many have predictions already; how many are still
     unmarked.

  2. **Browse training-run history** indexed in the DB (artifact kind
     ``ezm_unet_run_dir`` today; ``arena_unet_run_dir`` going forward).

  3. **Activate** a run — i.e. point the active-model registry
     (``data/arena_models.yaml``) at a specific checkpoint. Equivalent
     to ``mus1 arena-models activate`` but in-pane.

  4. **Inspect the currently active model** for each profile, with a
     deactivate shortcut.

The pane intentionally does NOT submit SLURM jobs directly — the
existing EZM ML pane already owns that flow for EZM, and the rest of
the workflow is profile-by-profile bring-up. T11 surfaces the
**right command to run** for each profile so the operator stays in
control of cluster submission.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st

from ..discovery import (
    CACHE_TTL_SECONDS,
    find_experiment_json,
    iter_experiment_dirs,
)
from ..filters import invalidate_after_write, pkey, render_scope_banner

PANE = "arena_training"


# ---------------------------------------------------------------------------
# Registries (cached per-render)
# ---------------------------------------------------------------------------

@st.cache_resource(show_spinner=False)
def _profiles(project_path_str: str):
    from mus1.arena_profiles.registry import ArenaProfileRegistry
    return ArenaProfileRegistry.from_config(Path(project_path_str))


@st.cache_resource(show_spinner=False)
def _models(project_path_str: str):
    from mus1.compute.arena_models import ArenaModelRegistry
    return ArenaModelRegistry.load(Path(project_path_str))


# ---------------------------------------------------------------------------
# Training-set discovery — per profile
# ---------------------------------------------------------------------------

# Which manual-marking key each profile reads from. Adding a profile that
# needs a new GT key means extending this map.
_MARKING_KEY_BY_PROFILE_GEOMETRY = {
    "annular": ("ezm_wedge_points", "ezm_wedge_points"),
    # Future: ("arena_boundary", "circular_arena_boundary") for buckets
}


def _gt_marking_key(profile) -> Optional[str]:
    """Return the arena_markings sub-key that holds GT data for *profile*."""
    if profile is None:
        return None
    shape = profile.geometry.shape
    if shape == "annular":
        return "ezm_wedge_points"
    if shape == "circular":
        return "arena_boundary"  # not yet trained; reserved
    return None


@st.cache_data(show_spinner=False, ttl=CACHE_TTL_SECONDS)
def _training_set_summary(
    project_path_str: str, profile_id: str, gt_key: str, pred_key: str,
) -> Dict[str, int]:
    """Return ``{n_total, n_with_gt, n_with_pred, n_promotable}``.

    *n_promotable* = predictions that have been QC-reviewed and either
    accepted (``keep``) or actively promoted; serves as a quick "how
    much extra training data could be picked up from this round."
    """
    n_total = 0
    n_gt = 0
    n_pred = 0
    n_promotable = 0
    project_path = Path(project_path_str)
    for root, task, exp_dir in iter_experiment_dirs(project_path):
        jp = find_experiment_json(exp_dir)
        if jp is None:
            continue
        try:
            data = json.loads(jp.read_text())
        except Exception:
            continue
        am = data.get("arena_markings") or {}
        ap = am.get("arena_profile") or {}
        if ap.get("profile_id") != profile_id:
            continue
        n_total += 1
        gt = am.get(gt_key) or {}
        if gt.get("points") or gt.get("ellipse"):
            n_gt += 1
        pred = (am.get("predicted") or {}).get(pred_key) or {}
        if pred:
            n_pred += 1
            qc = pred.get("qc") or {}
            if qc.get("status") in ("keep", "promote_to_manual"):
                n_promotable += 1
    return {
        "n_total": n_total,
        "n_with_gt": n_gt,
        "n_with_pred": n_pred,
        "n_promotable": n_promotable,
    }


# ---------------------------------------------------------------------------
# Run history (DB)
# ---------------------------------------------------------------------------

def _list_runs_from_db(
    db_path: Path, *, kinds: Tuple[str, ...] = ("ezm_unet_run_dir", "arena_unet_run_dir"),
    limit: int = 200,
) -> List[Dict[str, Any]]:
    if not Path(db_path).is_file():
        return []
    try:
        con = sqlite3.connect(str(db_path))
        con.row_factory = sqlite3.Row
        placeholders = ",".join(["?"] * len(kinds))
        rows = con.execute(
            f"SELECT kind, path, meta_json, created_at FROM external_artifacts "
            f"WHERE kind IN ({placeholders}) ORDER BY created_at DESC LIMIT ?",
            (*kinds, int(limit)),
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
        try:
            meta = json.loads(r["meta_json"]) if r["meta_json"] else {}
        except Exception:
            meta = {}
        p = Path(str(r["path"]))
        # Best-effort: pull profile_id from meta or infer EZM from kind
        profile_id = str(meta.get("profile_id") or "")
        if not profile_id and r["kind"] == "ezm_unet_run_dir":
            profile_id = "ezm_460mm"
        # Best-effort: read run_status.json for test metrics
        rs_path = p / "run_status.json"
        rs: Dict[str, Any] = {}
        if rs_path.is_file():
            try:
                rs = json.loads(rs_path.read_text())
            except Exception:
                rs = {}
        # Find a model checkpoint inside the run dir
        ckpt = p / "model_best.pt"
        if not ckpt.is_file():
            ckpt = p / "model.pt"
        out.append({
            "kind": r["kind"],
            "run_path": str(p),
            "run_name": p.name,
            "profile_id": profile_id,
            "created_at": str(r["created_at"])[:19],
            "checkpoint": str(ckpt) if ckpt.is_file() else "",
            "checkpoint_exists": ckpt.is_file(),
            "status": rs.get("status", ""),
            "best_iou": rs.get("best_iou") or rs.get("test_iou") or "",
            "n_train": rs.get("n_train_sources") or rs.get("n_train") or "",
        })
    return out


# ---------------------------------------------------------------------------
# Main render
# ---------------------------------------------------------------------------

def render_arena_training(
    *, workspace_root: Optional[str], project_path: Path, db_path: Path,
) -> None:
    st.header("Arena Training")
    st.caption(
        "Per-profile view of training-set readiness, run history, and "
        "active-model status. Submit SLURM training from a terminal; "
        "use this pane to track progress and activate trained models."
    )
    render_scope_banner()

    if st.button("Refresh (clear cache)", key=pkey(PANE, "refresh")):
        invalidate_after_write()
        st.cache_data.clear()
        st.cache_resource.clear()
        st.rerun()

    profiles = _profiles(str(project_path))
    models = _models(str(project_path))
    profile_ids = profiles.list_ids()
    if not profile_ids:
        st.warning("No arena profiles registered.")
        st.stop()

    # ── Profile selector ─────────────────────────────────────────────
    active_ids = set(models.list_profiles())
    profile_id = st.selectbox(
        "Arena profile",
        options=profile_ids,
        format_func=lambda pid: (
            f"{pid}  •  {'✓ model active' if pid in active_ids else 'no active model'}"
        ),
        key=pkey(PANE, "profile"),
    )
    profile = profiles.get(profile_id)

    # ── Section 1: Training-set state ────────────────────────────────
    st.markdown("---")
    st.subheader("1. Training-set state")
    gt_key = _gt_marking_key(profile) or ""
    # Default prediction key falls back to the active model's mask_to_marking
    # if set, else mirror the GT key naming for circular geometries.
    active_entry = models.get(profile_id)
    pred_key = (active_entry.mask_to_marking if active_entry and active_entry.mask_to_marking
                else gt_key)
    if not gt_key:
        st.info(
            f"No GT marking key wired for `{profile_id}` "
            f"(geometry: `{profile.geometry.shape}`). Add an entry in "
            "`_gt_marking_key()` once a corresponding marker pane exists."
        )
    else:
        summary = _training_set_summary(
            str(project_path), profile_id, gt_key, pred_key or gt_key,
        )
        cols = st.columns(4)
        cols[0].metric("Experiments (profile-assigned)", summary["n_total"])
        cols[1].metric(f"With GT (`{gt_key}`)", summary["n_with_gt"])
        cols[2].metric(
            f"With predictions (`{pred_key or '—'}`)",
            summary["n_with_pred"] if pred_key else 0,
        )
        cols[3].metric(
            "Predictions accepted/promoted (extra training data)",
            summary["n_promotable"],
        )
        if summary["n_with_gt"] == 0:
            st.warning(
                f"No experiments have `arena_markings.{gt_key}` yet. "
                f"Mark some via the **{ 'EZM Wedge Marking' if gt_key == 'ezm_wedge_points' else 'NOR/NOF Object Marking' }** pane first."
            )

    # ── Section 2: Submit training (manual command) ─────────────────
    st.markdown("---")
    st.subheader("2. Submit training")
    if profile_id == "ezm_460mm":
        st.code(
            "# From the project root, submit a SLURM training job:\n"
            "sbatch ml_workspace/ezm_arena_unet/training/train.sbatch \\\n"
            "  --cohort ezm_publication \\\n"
            "  --base-ch 16 --img-size 256 --epochs 200",
            language="bash",
        )
        st.caption(
            "Adjust `--cohort` to whichever cohort whose GT you want to train on. "
            "When the job lands, the run dir auto-registers in the DB; refresh "
            "this pane to see it under Section 3 below."
        )
    else:
        st.info(
            f"No training submission template for `{profile_id}` yet. "
            "Wire one in `ml_workspace/<profile>/training/train.sbatch` "
            "and surface it here once it exists."
        )

    # ── Section 3: Run history ───────────────────────────────────────
    st.markdown("---")
    st.subheader("3. Run history")
    all_runs = _list_runs_from_db(db_path)
    profile_runs = [
        r for r in all_runs if (not r["profile_id"] or r["profile_id"] == profile_id)
    ]
    if not profile_runs:
        st.info(
            f"No runs indexed for `{profile_id}`. Run "
            "`mus1 import ezm-unet-runs` (or the profile-aware equivalent) "
            "after a training job completes."
        )
    else:
        df = pd.DataFrame(profile_runs)
        # Show the columns operators actually scan
        show_cols = [
            "run_name", "created_at", "status", "best_iou",
            "n_train", "checkpoint_exists", "run_path",
        ]
        show_cols = [c for c in show_cols if c in df.columns]
        st.dataframe(df[show_cols], hide_index=True, use_container_width=True)

        # Activation form (uses run_id from the table)
        st.markdown("**Activate a run**")
        run_choices = [r["run_name"] for r in profile_runs if r["checkpoint_exists"]]
        if not run_choices:
            st.caption(
                "No runs with an on-disk checkpoint available to activate."
            )
        else:
            sel_run = st.selectbox(
                "Run to activate",
                options=run_choices,
                key=pkey(PANE, f"activate_run__{profile_id}"),
            )
            sel_meta = next((r for r in profile_runs if r["run_name"] == sel_run), None)
            default_post = (
                "ezm_wedge_points" if profile_id == "ezm_460mm"
                else "circular_arena_boundary"
            )
            mask_to_marking = st.text_input(
                "Post-processor key",
                value=default_post,
                key=pkey(PANE, f"activate_mask__{profile_id}"),
                help="Maps the U-Net mask to a marking shape. See "
                     "`mus1.compute.arena_post_processors`.",
            )
            notes = st.text_input(
                "Notes",
                value="",
                placeholder="optional — e.g., 'best so far on val cohort'",
                key=pkey(PANE, f"activate_notes__{profile_id}"),
            )
            if st.button(
                f"Activate {sel_run}",
                key=pkey(PANE, f"activate_btn__{profile_id}"),
                type="primary",
                disabled=sel_meta is None or not sel_meta.get("checkpoint_exists"),
            ):
                from mus1.compute.arena_models import ArenaModelRegistry
                try:
                    yaml_path = ArenaModelRegistry.write_active(
                        project_path,
                        profile_id=profile_id,
                        run_id=sel_meta["run_name"],
                        checkpoint=Path(sel_meta["checkpoint"]),
                        mask_to_marking=mask_to_marking,
                        notes=notes,
                    )
                    invalidate_after_write()
                    st.cache_resource.clear()
                    st.success(f"Activated. Wrote {yaml_path}.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Activation failed: {e}")

    # ── Section 4: Active model status ───────────────────────────────
    st.markdown("---")
    st.subheader("4. Active model status")
    entry = models.get(profile_id)
    if entry is None:
        st.info(f"No active model for `{profile_id}`.")
    else:
        col_info, col_actions = st.columns([3, 1])
        with col_info:
            st.markdown(
                f"**Run:** `{entry.run_id}`  \n"
                f"**Checkpoint:** `{entry.checkpoint}` "
                f"{'✓' if entry.checkpoint.is_file() else '✗ missing on disk'}  \n"
                f"**Post-processor:** `{entry.mask_to_marking or '—'}`  \n"
                f"**Activated:** `{entry.activated_at or '?'}`"
            )
            if entry.notes:
                st.caption(f"Notes: {entry.notes}")
        with col_actions:
            if st.button(
                "Deactivate", key=pkey(PANE, f"deactivate__{profile_id}"),
            ):
                from mus1.compute.arena_models import ArenaModelRegistry
                ArenaModelRegistry.clear_active(project_path, profile_id=profile_id)
                invalidate_after_write()
                st.cache_resource.clear()
                st.toast(f"Deactivated {profile_id}.")
                st.rerun()
            st.caption(
                "Inference QC pane will continue to display historical reviews "
                "pinned to their original `model_run_id`."
            )
