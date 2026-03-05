# MUS1

Streamlit web app for managing and annotating the WDMOSEQ2 experiment dataset on Chinook. Backed by a project-scoped SQLite database (`mus1.db`) and a CLI import pipeline.

## Launch

```bash
./scripts/run_experiment_browser.sh web --install
```

The script activates conda env `mus1-dev`, prints the SSH port-forward command, and launches the Streamlit app. Pass explicit paths when needed:

```bash
./scripts/run_experiment_browser.sh web \
  --project-path "/center1/WDMOSEQ2/llplatil/WDMOSEQ2/data" \
  --workspace-root "/center1/WDMOSEQ2/llplatil/WDMOSEQ2/moseq2_workspace"
```

## What this app does

### 1. Experiment data overview

Browse experiments, subjects, artifacts, and QC events from `mus1.db`. The DB is populated via CLI importers that read from the session index, subject rosters, rotarod data, and KPMS recordings. This is the foundation for reproducible statistical analyses against a structured, queryable dataset.

Web app mode: **Experiments**

### 2. EZM arena annotation and U-Net training

Annotate EZM open/closed zones, curate training sets, train U-Net segmentation models via Slurm, and visually QC both labeled and unlabeled predictions.

Web app modes: **Annotator** (EZM full marking + **EZM Wedge** boundary refinement), **EZM Zones QC** (training set curation), **EZM Border QC** (prediction QC), **EZM ML** (submit training, review frames)

**EZM Wedge mode** (2026-02-24): faster boundary marking that reuses existing outer ellipse data. Click 2 border points per open wedge, adjust radial center, save. Replaces the slower 4-step freehand approach for boundary refinement.

I want to click the 4 wedge points on a single frame now -lp (3/3/36)

### 3. NOR/NOF arena annotation and model training

Annotate NOR/NOF arena boundaries and object placements, export QC CSVs, and index annotations into the DB. Model training infrastructure for NOR/NOF is the next build target.

Web app modes: **NOR/NOF ROI** (task list + annotation launch), **NOR/NOF QC** (annotation QC), **Annotator** (NOR/NOF marking)

### 4. Training run monitoring

Monitor Slurm job status, discover ML training runs (both U-Net and tracking model iterations), and compare metric trends across runs within each model type.

Web app mode: **Training Monitor**

## CLI (import pipeline)

```bash
mus1 import workspace-db-sync     # unified sync: session index + rotarod + KPMS
mus1 import arena-zones            # index arena zone JSONs into DB
mus1 import ezm-unet-runs         # index EZM U-Net training runs
mus1 import ml-tracking-runs       # index ML tracking training runs
```

## Documentation

Operational reference for all workflows: `docs/web/README.md`
