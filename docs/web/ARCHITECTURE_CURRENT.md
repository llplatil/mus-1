# MUS1 Architecture (current state)

MUS1 is a Streamlit web app and CLI toolset for browsing, annotating, and managing the WDMOSEQ2 experiment dataset on Chinook. It reads from and writes to a project-scoped SQLite database (`mus1.db`) and a set of workspace contracts (CSVs, JSONs, artifact paths).

A legacy Qt desktop GUI exists in `src/mus1/gui/` but is not actively used or maintained. The web app is the primary interface.

## Components

### Streamlit web app (`src/mus1/web/`)

Entry point: `app.py` (launched via `scripts/run_experiment_browser.sh web`)

Views (sidebar mode selector):

| Mode | File | What it does |
|------|------|-------------|
| Experiments | `views/experiments.py` | Browse experiments, subjects, artifacts, QC events from mus1.db |
| EZM Zones QC | `views/ezm_zones_qc.py` | Visual QC of EZM zone annotations; curate training set CSV |
| EZM Border QC | `views/ezm_border_qc.py` | QC of EZM border/mask predictions |
| EZM ML | `views/ezm_ml.py` | EZM U-Net retrain: submit Slurm jobs, review frame queues, export training CSVs |
| NOR/NOF ROI | `views/nor_nof_roi.py` | Task list for NOR/NOF ROI annotation; export QC CSV; launch annotator |
| NOR/NOF QC | `views/nor_nof_qc.py` | Visual QC of NOR/NOF ROI annotations and object placements |
| Annotator | `views/annotator_embed.py` | Embedded arena annotator (EZM zone marking, NOR/NOF object + arena marking) |
| Training Monitor | `views/training_monitor.py` | Slurm job status, ML run discovery, metric trend plots |

Supporting modules:

| Module | Purpose |
|--------|---------|
| `db.py` | SQLite connection helper (raw `sqlite3`, not SQLAlchemy) |
| `paths.py` | Path resolution: DB path, session index CSV, DLC config, arena zone dirs, mount-alias handling (`/center1` vs `/import/c1`) |
| `session_index.py` | Load and filter the session index CSV |
| `models.py` | `ExperimentRow` dataclass for typed query results |
| `ml_tables.py` | ML frame review and training queue DB helpers |
| `slurm.py` | Slurm submit/status helpers |
| `io.py` | File I/O utilities |
| `utils.py` | Miscellaneous helpers |

### CLI (`src/mus1/core/simple_cli.py`)

Typer-based CLI. The import commands are the most actively used:

```
mus1 import workspace-db-sync    Unified sync: session index + rotarod + KPMS recordings
mus1 import moseq2-workspace     Import session index into subjects/experiments/artifacts
mus1 import arena-zones           Index arena zone JSONs as external_artifacts
mus1 import ezm-unet-runs        Index EZM U-Net training runs
mus1 import ml-tracking-runs      Index ML tracking training runs
mus1 import-rotarod               Import rotarod assay data
```

Other CLI subcommands exist for setup, lab management, project management, and run registry but are secondary to the web workflow.

### Importers (`src/mus1/core/importers/`)

Each importer reads from a specific workspace source and writes to mus1.db:

| Importer | Source | DB tables written |
|----------|--------|-------------------|
| `moseq2_workspace.py` | `session_index_filtered.csv` | subjects, experiments, external_artifacts, qc_events |
| `rotarod.py` | `rotarod_attempts_long_timepoint_cleaned.csv` | assay_sessions, assay_measurements |
| `kpms_recordings.py` | KPMS rerun `recordings.csv` files | external_artifacts |
| `arena_zones.py` | Arena zone JSON directories | external_artifacts |
| `ezm_unet_runs.py` | EZM U-Net run directories | external_artifacts |
| `ml_tracking_runs.py` | ML tracking run directories | external_artifacts |

### Core data model (`src/mus1/core/schema.py`)

SQLAlchemy models defining the mus1.db schema. Tables actively used by the web workflow:

| Table | Purpose |
|-------|---------|
| `subjects` | Per-animal metadata (sex, genotype, birthdate, treatment) |
| `experiments` | Per-session records (experiment_type, date_recorded, processing_stage) |
| `external_artifacts` | Artifact pointers with kind/path/experiment linkage (zone JSONs, h5 files, stats CSVs, run outputs) |
| `qc_events` | Integrity findings (missing files, roster mismatches, corrupt inputs) |
| `assay_sessions` | Non-video assay sessions (rotarod) |
| `assay_measurements` | Metric-level assay data with QC flags |
| `experiment_videos` | Many-to-many experiment-video associations |
| `videos` | Video records (path, hash) |

Other tables exist for the legacy desktop app (users, labs, colonies, lab_members, lab_projects, workgroups) but are not used by the web workflow.

### Workspace contracts

MUS1 consumes data from the broader WDMOSEQ2 workspace through a contract layer:

```
apps/mus1/workspace/contracts/
  ml_tracking_metadata_model/
    index/session_index_filtered.csv     Session index (compiled, filtered)
    segments/*.py                         Thin shims that runpy canonical implementations
```

The session index is the single compiled data contract that drives the experiment browser and import pipeline. It is built by scripts in `ml_workspace/ml_tracking_metadata_model/` and copied here.

### Slurm wrappers

```
apps/mus1/workspace/ml_tracking/slurm/*.slurm     ML tracking model training jobs
workspace/dlc_ezm_open_closed/torch_ml/*.slurm     EZM U-Net training jobs
```

Wrappers create a MUS1 run record (via CLI), export `MUS1_RUN_DIR`, and submit to Slurm. Outputs land in the project-scoped run directory for indexing.

## Data flow

```
Workspace sources (CSVs, H5s, JSONs, rosters)
    |
    v
CLI importers (mus1 import ...)
    |
    v
mus1.db (SQLite)
    |
    v
Streamlit web app (reads DB + workspace files for display)
    |
    v
User actions: annotate arena zones, submit Slurm jobs, QC overlays
    |
    v
Arena zone JSONs / run outputs written to workspace
    |
    v
Re-index into DB (mus1 import arena-zones / ezm-unet-runs / ml-tracking-runs)
```

## Path resolution

The web app accepts two primary path arguments:
- `--project-path`: directory containing `mus1.db` (or path to the DB file directly)
- `--workspace-root`: root of the moseq2_workspace for resolving data inputs

`paths.py` handles:
- DB path resolution (dir or file)
- Session index CSV: tries `workspace_root/ml_tracking_metadata_model/index/` then falls back to the contract copy
- DLC project config: prefers Stage 2 layout (`dlc_workspace/projects/`) over legacy paths
- Mount alias normalization: `/center1/` and `/import/c1/` treated as equivalent
- Arena zone output directories

## What the legacy Qt GUI code is

`src/mus1/gui/` contains a PyQt-based desktop application with:
- Setup wizard, user/lab/colony management
- Project discovery, subject/experiment CRUD
- Settings view, theme manager
- Service layer (GUIServiceFactory, GUISubjectService, etc.)

This code is not actively used. The web app replaced it for the Chinook workflow. It remains in the codebase but should not be treated as current architecture. If the desktop app is needed again, it would require updating to match the current DB schema and data model.

## Environment

- Python environment: `mus1-dev` conda env
- Runs on Chinook via SSH port-forwarding for Streamlit
- Slurm jobs submitted to `bio` partition (or idle nodes via `sbatch_on_idle_node.sh`)
- DB: SQLite (local file, rebuildable from experiment JSONs); future option for Postgres

### Data architecture decision (2026-03-27)

**Experiment JSONs are the sole source of truth.** The mus1.db and
session_index CSV are deprecated as primary data sources. All
experiment metadata, QC flags, arena markings, computed metrics, and
provenance live in the per-experiment JSON files.

| Data | Source of truth | Old source | Status |
|------|----------------|-----------|--------|
| Subject metadata | experiment JSON `metadata.*` | mus1.db `subjects` table | JSON authoritative |
| QC flags | experiment JSON `qc_flags.*` | mus1.db `qc_events` | JSON authoritative |
| Arena markings | experiment JSON `arena_markings.*` | zone JSONs on disk | JSON authoritative |
| Computed metrics | experiment JSON `computed_metrics.*` | CSV outputs | JSON authoritative |
| Cohort membership | `data/cohorts/*.json` | manual lists | Cohort JSONs authoritative |
| DLC artifact paths | experiment JSON `extraction.*` | session_index CSV | JSON authoritative |
| RR assay data | experiment JSON `metadata.experiment_level.attempts` | mus1.db `assay_sessions` | JSON authoritative |
| Session index CSV | **DEPRECATED** | Was primary | Replaced by ExperimentService |

The DB will be rebuilt from JSONs on demand (`mus1 index rebuild`)
rather than being synced incrementally via importers.
### My points for app improvement -lp (3/14/26)
- Eventually I want to build the app to be essentially an LLM wrapped, or I don't really know what's meant by MCP wrapped, or to have an MCP. Each lab is going to be storing and have different compute in different places, right, and it doesn't really make sense to support all of it. What does make sense is to integrate the consistently used stats and some of the actually good layouts that we have, etc., and usable tools in a way that should stay. I leave the deterministic stuff that really needs to be deterministic, and build the app around an easy stochastic implementation around things that are going to need to be modulable per lab. I think that makes sense for current era design.
- I also want to be able to support saving annotated frames from final QC images for things that are relevant to a publication, right? Like, if we want to say, "Hey, we verified this," it should be easy to save the frame that I verified on and have that included in a supplement link when somebody provides their data for review.

## New architecture (in progress, 2026-03-27)

The rewrite adds three new packages alongside the existing Streamlit web app:

### Task definition system (`src/mus1/tasks/`)
Replaces all hardcoded task types with a configurable registry:
- `base.py`: `TaskDefinition` ABC — annotation fields, arena geometry, QC flags, calculation variants, physical dimensions
- `builtins/`: 5 built-in tasks (EZM, NOR, NOF, OF, RR) with full variant specs
- `registry.py`: `TaskRegistry` — loads builtins + user-defined YAML tasks

### Service layer (`src/mus1/server/services/`)
Framework-agnostic business logic (no Streamlit or FastAPI imports):
- `ExperimentService`: consolidated discovery of all experiments from JSONs on disk (replaces 6+ duplicate patterns in views)
- `CohortService`: wraps existing `cohorts.py` with service-backed metadata resolution
- `QCService`: task-aware auto-flag computation (delegates to task definitions)
- `AnnotationService`: arena marking CRUD + provenance frame export (PNG overlay)

### Compute library (`src/mus1/compute/`)
Deterministic scientific calculations — pure-functional, no side effects:
- All code produces identical outputs given identical inputs
- See `compute/README.md` for the deterministic-vs-stochastic boundary
- Modules planned: `arena_geometry.py`, `ezm_zones.py`, `nor_nof_interaction.py`, `tracking_utils.py`, `overlay.py`

### Project config (`src/mus1/server/config.py`)
`ProjectConfig` loaded from `mus1.yaml` — replaces all hardcoded paths in `paths.py`.

### Data flow (new)
```
Experiment JSONs on disk (source of truth)
    |
    v
ExperimentService (scans, caches in memory, serves queries)
    |
    +-> CohortService (membership, summaries)
    +-> QCService (flags, auto-computation via TaskDefinition)
    +-> AnnotationService (marking CRUD, provenance export)
    +-> ComputeService (planned: deterministic metric computation)
    |
    v
FastAPI routers (planned Phase 3)  <-->  React UI (planned Phase 4)
    |
    v
OpenAPI / MCP (for agent consumption)
```
