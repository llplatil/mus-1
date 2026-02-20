# MUS1 Web App Roadmap

Priorities for the Streamlit web app and CLI toolset. Ordered by impact on the current workflow.

## Active work

### EZM arena annotation completion

- Finish full-set batch annotation pass (remaining sessions without zone JSONs)
- Settings sweep on EZM U-Net training (learning rate, augmentation params, safe_bg ratio)
- Goal: reliable EZM open/closed mask inference across all EZM sessions without per-video manual correction

### NOR/NOF arena model training

- Annotate enough NOR/NOF ROI JSONs (v2) to train a first NOR/NOF arena/object model
- The web flow is already in place: NOR/NOF ROI view -> export QC CSV -> annotator -> save JSONs -> `mus1 import arena-zones`
- Training infrastructure needs: decide on model architecture (U-Net reuse or separate), Slurm wrapper, QC overlay pipeline

### Path alignment after Stage 2 workspace restructure

Current issues and fixes needed:

| Issue | Current state | Fix |
|-------|--------------|-----|
| DLC project discovery | App tries `workspace_root/data/behavior_videos/dlc_projects` first | Resolve from `WDMOSEQ2/dlc_workspace/projects/` when present (partially done in `paths.py`) |
| Session index resolution | Primary path is stale; fallback to contract works | Add `ml_workspace/ml_tracking_metadata_model/index/` as a resolution candidate |
| Project path default | Launcher defaults to `apps/mus1/projects/moseq2_workspace_db` | Document using `--project-path /path/to/WDMOSEQ2/data` or make launcher auto-detect `../data/mus1.db` |

### Session index contract refresh

- The contract copy at `workspace/contracts/ml_tracking_metadata_model/index/session_index_filtered.csv` is built by ML workspace scripts
- After any index rebuild, the contract must be refreshed so the web app and importers use current data
- Add a small script or document the copy step explicitly

## Next priorities

### experiment_data integration

- `moseq2_workspace/data/experiment_data/` is the canonical per-experiment folder structure with resolved metadata JSONs
- The web app could read from these JSONs to backfill/cross-check mus1.db entries or to provide a QC view of resolution status
- Not a replacement for the current DB-driven browser; additive view or import path

### Experiment browser improvements

- Show per-experiment artifact summary more clearly (what exists, what is missing)
- Surface QC events inline with experiment detail
- Filter/sort by annotation status (has EZM zone, has NOR/NOF ROI, missing tracking, etc.)

### Reports workspace integration

- `reports_workspace/` contains statistical report outputs
- Web app could link report CSVs/figures to the experiments that contributed to them
- Requires experiment_data resolution to be far enough along that we know which sessions fed which reports

## Lower priority

### Workspace-db-sync reliability

- `workspace-db-sync` runs session index + rotarod + KPMS in one pass
- Add better error reporting when individual import steps fail (currently silent on partial failures)
- Add `--dry-run` mode for previewing what would change

### DB schema evolution

- Current schema uses `create_all()` (no migrations). If schema changes, existing DBs need manual attention
- If we move to Postgres for shared access, need Alembic or equivalent migration story
- `videos.hash` is NOT NULL but imports rarely have hashes; consider making it nullable

### Standalone mus1-web extraction

- Extract the Streamlit app + minimal deps into its own repo/package
- Deferred until the web app stabilizes and the desktop GUI is definitively retired

### Legacy desktop GUI

- Code in `src/mus1/gui/` is not used
- No active work planned
- If removed, the core/importers/web modules and CLI would remain as the full MUS1 toolset

## Completed

- Streamlit web app with 8 view modes (experiments, EZM zones/border/ML, NOR/NOF ROI/QC, annotator, training monitor)
- CLI import pipeline: workspace-db-sync, moseq2-workspace, arena-zones, rotarod, KPMS recordings, EZM/ML run indexing
- mus1.db schema: subjects, experiments, external_artifacts, qc_events, assay_sessions, assay_measurements
- NOR/NOF v2 annotation flow (clean reset from v1, session_id prefix in filenames, embedded annotator handoff)
- EZM annotator with undo/clear controls and pre-save preview overlay
- ML tracking training submission with MUS1 run records and project-scoped output layout
- Mount-alias aware path deduplication (`/center1` vs `/import/c1`)
- Training monitor with Slurm job status and metric trend plots
