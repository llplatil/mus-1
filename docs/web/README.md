# MUS1 Web: operational reference

## EZM arena marking + U-Net training loop

### 1) Annotate EZM zone JSONs

- In the web app: **Mode -> Annotator**
- Provide a **QC CSV list** (e.g. `qc_to_label_*.csv`) containing at least:
  - `video_path` (absolute or workspace-relative)
  - `frame_idx`
  - optional: `overlay_path`, `crop_xyxy`

**Two annotation modes are available:**

#### EZM Wedge: refine boundaries (recommended for boundary refinement)

Annotator mode: **`EZM Wedge: refine boundaries`**

Requires an existing zone JSON for each video (outer ellipse + r_inner). Best used after initial marking or autofit.

Workflow per video:
1. Click **2 border points** on the outer track for **open wedge 1** (where open arm meets closed arm)
2. Click **2 border points** for **open wedge 2**
3. Optionally adjust the **radial center** with X/Y sliders (default = ellipse center)
4. Verify the preview overlay (green = open, blue = closed)
5. **Accept + Save + Next video** to save and advance

Controls:
- **Undo last point** and **Clear** per wedge
- **Reset center** to return sliders to ellipse center
- **Preview overlay** toggle (sidebar)

#### EZM: full zone annotation (for initial marking)

Annotator mode: **`EZM: open/closed zone annotation`**

Use this when no zone JSON exists yet (first-time marking).

Controls:
- **Undo last** and **Clear** for outer boundary points, inner boundary points, and border lines
- **Preview overlay** toggle (sidebar) to verify before saving

Saved outputs (both modes): `workspace/arena_zones/ezm_per_video_v2/*.json`

Note: Streamlit may occasionally log `MediaFileHandler: Missing file <hash>.png` during rapid reruns. This does not mean your JSONs failed to save.

### 2) Curate and QC the training set

In the web app: **Mode -> EZM Zones QC**

- **Preview final training set** renders the exact `frame_idx` and the GT mask overlay.
- Overlay colors: **Yellow = open** (class 1), **Blue = closed** (class 2)

Curated training list: `projects/<project>/ml_review/ezm_unet/training_per_video_curated.csv`

Important columns:
- `label_source`: `derived` (parametric mask) or `annotations` (raw Fabric objects from JSON)
- `frame_idx`: respected per-row; otherwise training falls back to the global `--frames` list

### 3) Train + QC

Slurm wrapper: `workspace/dlc_ezm_open_closed/torch_ml/run_train_unet_open_closed_from_zones_augfix_sched_and_qc.slurm`

That script:
- trains into the project-scoped run directory (`MUS1_RUN_DIR`)
- writes labeled QC overlays under `qc_overlays/`
- samples unlabeled set and writes QC overlays under `qc_unlabeled_infer/overlays/`

**SAFE_BG augmentation**: to include weak labels, add a `label_mode` column to the training CSV:
- `full` = standard open/closed mask
- `safe_bg` = enforce background in safe center + outside; ignore everything else (`IGNORE_LABEL=255`)
- SAFE_BG items are forced into train (never validation)

**Warm start**: set `EZM_UNET_RESUME` to a checkpoint path (e.g. `<prior_run>/checkpoints/checkpoint_latest.pt`). Without it, trains from scratch. If a warm-start run never beats the previous best score, it may not write `model_best.pt`; for unlabeled QC inference prefer `model_best.pt` if present, else `model_last.pt`.

## NOR/NOF marking loop

1. In the web app: **Mode -> NOR/NOF ROI**
2. Focus the list using your DLC project (paste the project dir or `config.yaml` path)
3. Export QC CSV list and click **Open annotator (NOR/NOF) in this app**
4. Save v2 JSONs into `workspace/arena_zones/nor_nof_per_video_v2/`
5. Back in NOR/NOF ROI, click **Run: `mus1 import arena-zones`** to index into DB

NOR/NOF object marking is **COMPLETE** — all 339 sessions marked with arena_boundary geometric circle fit. QC flags seeded on all 339 experiments. Publication cohort: 324 sessions (`data/cohorts/nor_nof_publication.json`).

## Training run monitoring

The Training Monitor view shows:
- Slurm job status (from `squeue`/`sacct`)
- ML run discovery under `<project_path>/runs/`
- Metric trend plots from `metrics.csv` when present

This covers both EZM U-Net iterations and ML tracking model iterations. Each model type has its own run kind (`ezm_unet`, `ml_tracking`) and runs are compared within their kind.

Run records are created before Slurm submission:
```bash
mus1 runs new <kind> --project-path <path> --name "optional label"
```

The Slurm wrappers export `MUS1_RUN_DIR` so outputs land in the project-scoped run directory for automatic discovery by the monitor.

ML tracking model development details (what was tried, what worked, current best config) live in:
- `ml_workspace/ml_tracking_metadata_model/README.md`

## DB sync and import

### workspace-db-sync (default metadata sync)

Subject Explorer and Experiment Browser **counts come from mus1.db**. After you add or move experiment data (e.g. new sessions under `data/experiment_data/OF`), run this so the DB reflects the session index; no app restart needed. In Subject Explorer, use "Refresh experiment data index" to clear the 5-min cache of the experiment_data JSON scan (enrichment only).

```bash
mus1 import workspace-db-sync \
  --project-path "<project_path>" \
  --workspace-root "<workspace_root>"
```

Includes: session index import, rotarod ingestion, KPMS recordings ingestion.

Optional (explicit opt-in):
```bash
mus1 import workspace-db-sync \
  --project-path "<project_path>" \
  --workspace-root "<workspace_root>" \
  --include-arena-zones \
  --include-run-indexes
```

### Fast post-run sync

```bash
./scripts/post_run_sync.sh "<project_path>" "<workspace_root>"
```

Indexes latest ML tracking + EZM runs without full metadata sync. Set `RUN_FULL_METADATA_SYNC=1` for the full pass.

### Input vetting

```bash
./scripts/vet_workspace_inputs.sh "<workspace_root>"
```

Quick check of required upstream inputs before large retrains.

## DB filtering policy

Keep `mus1.db` as curated metadata + selected artifacts, not a dump of everything.

- Store in DB: experiments, subjects, assay measurements, and processed artifacts that are intentionally tracked
- Keep outside DB: scratch runs, trial outputs, intermediate files
- Operational split: `moseq2_workspace` is the broad working area; MUS1 project (`projects/...`) holds indexed run dirs and queryable artifacts

## Path resolution

The web app accepts:
- `--project-path`: directory containing `mus1.db` (or the DB file directly)
- `--workspace-root`: root of the moseq2_workspace

Known path issues after Stage 2 workspace restructure:

| Issue | Status |
|-------|--------|
| DLC project discovery: app prefers `workspace_root/data/behavior_videos/dlc_projects` | Partially fixed: `paths.py` checks `dlc_workspace/projects/` when available |
| Session index: primary path stale, fallback to contract works | Contract copy at `workspace/contracts/.../session_index_filtered.csv` is the working path; refresh from `ml_workspace` after rebuilds |
| Project path default: launcher defaults to `apps/mus1/projects/moseq2_workspace_db` | Use `--project-path /path/to/WDMOSEQ2/data` for canonical DB |

## Session index contract

The session index contract lives at:
- `apps/mus1/workspace/contracts/ml_tracking_metadata_model/index/session_index_filtered.csv`

It is built by scripts in `ml_workspace/ml_tracking_metadata_model/` and must be refreshed (copied) after any rebuild so the web app and importers use current data.

**Planned**: Session index will be buildable from `data/experiment_data` (or mus1.db) so that resolving missing data, fixing paths, or improving tracking flows cleanly into ML training. See `ml_workspace/ml_tracking_metadata_model/README.md` section "Relationship to experiment_data reorganization" for the plan.

## Streamlit dependency note

MUS1 uses `streamlit-drawable-canvas-fix` (the original `streamlit-drawable-canvas` is archived and breaks on Streamlit >= 1.41).


### To Do: -lp
- the workprocesses that create outputs that would be included in data/experiment_data experiment jsons need to write their output paths to that json. We need a mechanism to trigger this and accept the input be written to the json. this should be resolved before reindexing. the app should not auto update the db on its own unless we trigger it and jsons are updated.

See `data/DATA_ARCHITECTURE.md` for the full data flow rules and migration roadmap (items M-1 through M-15).

### Current Next Steps (2026-03-12)

**Manuscript-driven priorities** (see `docs/web/ROADMAP.md` for full context):

1. **EZM tracking QC Phase 3**: Visual review of 155 experiments sorted by artifact_rate — mark QC status in JSONs via app
2. **NOR/NOF QC flags in views**: Wire `qc_flags` into NOR/NOF app views (Phase 2c-app)
3. **5 partner experiments**: Need arena marking in app (NOR/NOF)
4. **Figure viewer**: Display generated figures from `statistics_workspace/output/*/figures/` — enables fast visual QC iteration
5. **Stats re-run integration**: Cohort management + one-click stats script re-run for iteration

**Blocked (waiting on compute):**
- KPMS no-trim syllable extraction → regenerate EZM + NOR/NOF stats + figures
- OF MoSeq2 kappa scan → production fit → OF publication stats
- Cross-task phenotypic fingerprint (all per-task stats must be current)
- ML tracking model update (needs no-trim syllables)

**Figure/table workflow**: See `reports_workspace/FIGURE_TABLE_WORKFLOW.md` for standard iteration process.