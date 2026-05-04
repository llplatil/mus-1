# MUS1 Architecture (current state)

**Last updated:** 2026-05-03

MUS1 is a Streamlit web app and CLI toolset for browsing, annotating, QC'ing,
and managing experiment data on Chinook. **Per-experiment JSONs are the
sole source of truth**; `mus1.db` is a rebuildable index. The repository
also contains a FastAPI backend + service layer (Phases 1–3 of the
open-source rewrite) and a deterministic compute library that the
Streamlit panes increasingly delegate to.

A legacy Qt desktop GUI exists in `src/mus1/gui/` but is not maintained.
Treat the Streamlit web app + FastAPI backend as the architecture; ignore
`src/mus1/gui/`.

---

## 1. Streamlit web app (`src/mus1/web/`)

Entry point: `app.py`, launched via `scripts/run_experiment_browser.sh web`.

### 1.1 Sidebar contract (three tiers)

Every pane shares the same sidebar layout, anchored by `web/filters.py`:

```
Database          ← project_path + db_path
Scope             ← cohort picker (universal, persists across panes)
View              ← pane radio
Filters           ← cohort-aware widgets the pane opts into
Display           ← pane-specific render toggles
```

Cross-cutting helpers in `web/filters.py`:
- `SCOPE_KEY` — single session-state key holding the active cohort.
- `render_scope_picker(project_path)` — sidebar selector wired in `app.py`.
- `render_scope_banner()` — inline caption every pane prints near its
  header so users see the active scope without re-opening the sidebar.
- `render_filters(rows, fields, key_prefix, …)` — single source of truth
  for the standard filters expander (qc_statuses, genotypes, sexes,
  text, marking_status, date_range). Filter widgets only render when
  the pane opts in via `fields={…}`.
- `mode_settings(label, key_prefix)` — context manager for the Display
  expander.
- `filter_by_cohort(rows, cohort, project_path)` — predicate used by
  every loader-consumer.
- `pkey(pane, widget)` — namespaced key builder; prevents silent
  state-bleed between panes.
- `invalidate_after_write()` — replaces scattered `st.cache_data.clear()`
  calls; called once per JSON write.

### 1.2 Panes

Sidebar order is **task-aligned lifecycle** — Browse → Cohort scoping →
EZM (Mark → arena QC → tracking QC) → NOR/NOF (Mark → arena/object QC
→ tracking QC) → Train. Cohort Management sits up top because users
pick or define a cohort *before* doing Mark or QC work.

| Group | Pane | File | Reads | Writes |
|---|---|---|---|---|
| Browse | Subjects | `views/subjects.py` | `subjects` SQLite + JSONs (timepoint enrichment) | — |
| Browse | Experiments | `views/experiments.py` | `experiments` SQLite | qc_events (delete/edit) |
| Cohort | Cohort Management | `views/cohort_management.py` | All experiment JSONs (multi-root); `data/cohorts/*.json` | `data/cohorts/*.json` (members[], description, objects[], summary auto-recomputed); per-experiment `nor_nof_pair` blocks |
| EZM Mark | EZM Wedge Marking | `views/ezm_wedge_marking.py` | EZM JSONs without `arena_markings.ezm_wedge_points` | EZM JSON: `arena_markings.ezm_wedge_points.points[]` + provenance |
| EZM QC | EZM Zones QC | `views/ezm_zones_qc.py` | EZM JSON `arena_markings.ezm_wedge_points` + computed circle fit | EZM JSON: `arena_markings.ezm_wedge_points.qc.{status,notes,reviewed_at}` |
| EZM QC | EZM Tracking QC | `views/ezm_tracking_qc.py` | EZM JSON + DLC CSV + 8-variant computed metrics | EZM JSON: `computed_metrics.ezm_open_closed.qc_review.{status,notes}` |
| NOR/NOF Mark | NOR/NOF Object Marking | `views/nor_nof_object_marking.py` | NOR/NOF JSONs without `arena_markings.object_left_xy` | NOR/NOF JSON: `arena_markings.{object_left_xy,object_right_xy,arena_boundary}` + optional task-type fix |
| NOR/NOF QC | NOR/NOF Object Association | `views/nor_nof_object_qc.py` | NOR/NOF JSON + paired-experiment lookup (multi-root) | NOR/NOF JSON: `metadata.experiment_level.{object_left,object_right,novel_side}` + `object_qc.{status,notes,reviewed_at}` |
| NOR/NOF QC | NOR/NOF Tracking QC | `views/nor_nof_interaction_qc.py` (file name lags rename) | NOR/NOF JSON + DLC CSV | NOR/NOF JSON: `interaction_qc.{notes,reviewed_at}` |
| Train | EZM ML | `views/ezm_ml.py` | Cohort JSON + EZM masks (`mus1.compute.ezm_masks`) | Slurm job submission via `mus1_runs/` registry |
| Train | ML Genotype | `views/ml_genotype.py` | Cohort JSON + per-experiment KPMS labels | Dataset YAML + Slurm submission via `mus1_runs/` |
| Train | Training Monitor | `views/training_monitor.py` | `mus1_runs/` registry + `ml_workspace/*/logs/` | — (planned rename → "Job Monitor"; see ROADMAP) |

**QC pane contract.** A QC pane filters by *input* prerequisites only —
markings, DLC linkage, video resolvability. The *output* it reviews
(computed metrics, masks, syllable assignments, …) may be present or
absent. When absent, render whatever overlay is computable from the
inputs and surface a banner naming the missing artifact and how to
produce it. **Never hide an experiment because the artifact under review
doesn't exist** — that's exactly the experiment most in need of
attention.

### 1.3 Discovery and data roots

`web/discovery.py` is the single source of truth for "which experiments
exist." Two canonical roots are scanned (in declaration order):

```
{project_path}/experiment_data/   # publication-grade
{project_path}/validation_data/   # held-out validation cohorts
```

Both are hard-coded by design (`DATA_ROOTS`); a third root would be a
code change, not a config tweak. Each root has the same internal
layout: `{ROOT}/{TASK}/{EXP_ID}/{EXP_ID}.json` with `recording/{video}`
alongside.

`task_dirs_across_roots()` enumerates folders; `find_experiment_dir()`
resolves an experiment_id to its folder regardless of root. Loaders
never construct a JSON filename — they glob `*.json` inside the folder.

`web/discovery.py` also exposes `resolve_dlc_csv_path(extraction)` that
abstracts over the **two extant DLC schemas**:

| Schema | Field | Where seen |
|---|---|---|
| Legacy | `extraction.tracking_file_path` | publication batches (171 EZM, 339 NOR/NOF) |
| New | `extraction.dlc_runs[-1].output.csv` | validation_2026 batches (12 EZM_VAL, 24 NOR/NOF_VAL) |

Every loader/view that needs the DLC CSV path reads it through this
helper. Direct reads of `tracking_file_path` are a regression and will
silently exclude validation experiments.

### 1.4 Caching

`@st.cache_data(ttl=CACHE_TTL_SECONDS)` (5 min) on filesystem loaders.
Panes that mutate JSONs call `invalidate_after_write()` to clear the
caches; lower TTLs are not used.

### 1.5 Mount aliases

Some recorded paths use `/center1/...` while runtime mounts as
`/import/c1/...` (or vice versa). `resolve_path()` in
`web/ezm_qc_shared.py` and equivalent helpers in NOR/NOF panes try both
forms before giving up. New code reading absolute paths should use
these helpers, not raw `Path.exists()`.

---

## 2. CLI (`src/mus1/core/simple_cli.py`)

Typer-based CLI. The canonically-used subcommands:

```
mus1 import workspace-db-sync     Unified sync: session index + rotarod + KPMS recordings
mus1 import moseq2-workspace      Import session index → subjects/experiments/artifacts
mus1 import arena-zones           Index arena zone JSONs as external_artifacts
mus1 import ezm-unet-runs         Index EZM U-Net training runs
mus1 import ml-tracking-runs      Index ML tracking training runs
mus1 import-rotarod               Import rotarod assay data
mus1 cohort link-nor-nof [<n>]    Auto-pair NOR↔NOF by (subject_id, date)
mus1 serve --data-root PATH       Launch FastAPI backend (Phase 3)
mus1 runs new <kind> ...          Create a MUS1 run record (used by Slurm wrappers)
```

Other subcommands exist for setup, lab management, project management,
and the run registry but are secondary to the web workflow.

---

## 3. FastAPI backend (`src/mus1/server/`)

Status: **Phases 1–3 complete (2026-04-01).** Tested against 895 real
experiments; 19/19 endpoint tests pass. The Streamlit app does not yet
consume it; the React frontend (Phase 4) is the planned client.

### 3.1 Service layer (`src/mus1/server/services/`)

Framework-agnostic business logic, no Streamlit or FastAPI imports:

| Service | Responsibility |
|---|---|
| `ExperimentService` | Consolidated discovery from JSONs (<5 s scan, <1 ms cached). Replaces 6+ duplicate patterns formerly in views. |
| `CohortService` | Wraps `cohorts.py` with ExperimentService-backed metadata resolution |
| `QCService` | Task-registry-aware auto-flag computation; delegates to `TaskDefinition` |
| `AnnotationService` | Marking CRUD + provenance frame export (PNG overlay) |

Dependency injection via `ServiceContainer` (singleton services per app
lifetime) wired in `server/deps.py`.

### 3.2 Routers (`src/mus1/server/routers/`)

6 routers, 19 endpoints, OpenAPI spec auto-generated at `/docs`
(Swagger) and `/openapi.json`:

```
/api/tasks         /api/experiments    /api/cohorts
/api/qc            /api/annotations    /api/compute
```

The compute endpoint computes NOR/NOF interaction metrics on-demand
from DLC CSV + arena markings.

### 3.3 Project config (`src/mus1/server/config.py`)

`ProjectConfig` loaded from `mus1.yaml` — replaces all hardcoded paths
in `web/paths.py`. Used by FastAPI; the Streamlit app still uses
`paths.py` directly.

---

## 4. Task definition system (`src/mus1/tasks/`)

Replaces all hardcoded task types with a configurable registry. Status:
**Phase 1 complete (2026-03-27).**

| Module | Responsibility |
|---|---|
| `base.py` | `TaskDefinition` ABC: annotation fields, arena geometry, QC flag vocabulary, calculation variants, physical dimensions |
| `builtins/` | 5 built-in tasks (EZM with 8 variants; NOR, NOF, OF, RR) |
| `registry.py` | `TaskRegistry` — loads builtins + user-defined YAML tasks |
| `yaml_task.py` | `YAMLTaskDefinition` — labs/agents define new tasks without writing Python (`mus1_tasks.yaml`) |

The Streamlit app reads the task definitions for variant lists,
auto-flag vocabularies, and object definitions. Hardcoded task
references are limited to `discovery.SUPPORTED_TASKS` (folder name
enumeration).

---

## 5. Compute library (`src/mus1/compute/`)

Deterministic scientific calculations — pure-functional, no side
effects, no I/O outside of opening files passed by path. ~3500 LOC
across 7 modules:

| Module | Purpose |
|---|---|
| `arena_geometry.py` | EZM circle fit, NOR/NOF arena boundary fit |
| `ezm_zones_model.py` | TinyUNet for EZM open/closed segmentation |
| `ezm_zones.py` | 8-variant zone classification (raw/bounded/consensus × head/nose/body) |
| `ezm_masks.py` | Mask generation + `blend_mask_overlay()` for QC display |
| `tracking.py` | DLC CSV reading (consolidated; was duplicated across 3 files) |
| `nor_nof_interaction.py` | Object zone + bout + d2 computation |
| `overlay.py` | Generic frame-overlay helpers used across QC panes |

`ComputeHarness` provides determinism check, parameter sweep, snapshot
regression, benchmark, and human-readable reports — used in CI to
guarantee variants don't drift.

The Streamlit panes reach into compute modules directly today; the
React rewrite will route everything through the FastAPI compute
endpoint.

---

## 6. Importers (`src/mus1/core/importers/`)

Each importer reads from a specific workspace source and writes to
`mus1.db`. The DB is a rebuildable index, not a source of truth — see §8.

| Importer | Source | DB tables written |
|---|---|---|
| `moseq2_workspace.py` | `session_index_filtered.csv` | subjects, experiments, external_artifacts, qc_events |
| `rotarod.py` | `rotarod_attempts_long_timepoint_cleaned.csv` | assay_sessions, assay_measurements |
| `kpms_recordings.py` | KPMS rerun `recordings.csv` files | external_artifacts |
| `arena_zones.py` | Arena zone JSON directories | external_artifacts |
| `ezm_unet_runs.py` | EZM U-Net run directories | external_artifacts |
| `ml_tracking_runs.py` | ML tracking run directories | external_artifacts |

The session index CSV is **deprecated as a source of truth** (see §8);
the moseq2_workspace importer now backfills the SQLite index from
JSONs.

---

## 7. Database schema (`src/mus1/core/schema.py`)

SQLAlchemy models. Tables actively used:

| Table | Purpose |
|---|---|
| `subjects` | Per-animal metadata |
| `experiments` | Per-session records |
| `external_artifacts` | Artifact pointers (zone JSONs, h5, stats CSVs, run outputs) |
| `qc_events` | Integrity findings |
| `assay_sessions` / `assay_measurements` | Non-video assays (rotarod) |
| `experiment_videos` / `videos` | Many-to-many video associations |

Other tables (users, labs, colonies, lab_members, lab_projects,
workgroups) exist for the legacy desktop app and are unused by the
current workflow.

Schema uses `create_all()` — no migrations yet. Forward-only versioned
migrations are a planned cleanup (see ROADMAP).

---

## 8. Source-of-truth contract

```
EXPERIMENT JSONs (per-experiment, on disk, in canonical roots)
    │ source of truth for: metadata, QC flags, arena_markings,
    │ computed_metrics, extraction (DLC paths), provenance
    ▼
mus1.db (SQLite, rebuildable index)
    │ rebuild: `mus1 index rebuild` — reads JSONs
    │ used by:  Subjects + Experiments panes (legacy reads)
    │           cohort task_type filtering
    ▼
data/cohorts/*.json  (cohort manifests; their `summary` block is
                      auto-recomputed on every save)
```

| Data | Source of truth | Status |
|---|---|---|
| Subject metadata | experiment JSON `metadata.*` | JSON authoritative |
| QC flags | experiment JSON `qc_flags.*` | JSON authoritative |
| Arena markings | experiment JSON `arena_markings.*` | JSON authoritative |
| Computed metrics | experiment JSON `computed_metrics.*` | JSON authoritative |
| Cohort membership | `data/cohorts/*.json` | Cohort JSONs authoritative |
| DLC artifact paths | experiment JSON `extraction.*` (legacy + `dlc_runs`) | JSON authoritative |
| RR assay data | experiment JSON `metadata.experiment_level.attempts` | JSON authoritative |
| Session index CSV | **DEPRECATED** | Replaced by ExperimentService |

The DB is rebuilt from JSONs on demand rather than synced incrementally.

---

## 9. Workspace contracts

```
apps/mus1/workspace/contracts/
  ml_tracking_metadata_model/
    index/session_index_filtered.csv     Session index (deprecated as SoT)
    segments/*.py                         Thin shims that runpy canonical impls
```

Slurm wrappers used by the training panes:

```
apps/mus1/workspace/ml_tracking/slurm/*.slurm     ML tracking training jobs
workspace/dlc_ezm_open_closed/torch_ml/*.slurm    EZM U-Net training jobs
```

Wrappers create a MUS1 run record (`mus1 runs new`), export
`MUS1_RUN_DIR`, and submit via `sbatch`. Outputs land in the
project-scoped run directory and are indexed by the corresponding
importer.

---

## 10. Path resolution

The web app accepts:
- `--project-path` — directory containing `mus1.db` (or DB file path)
- `--workspace-root` — root of moseq2_workspace for resolving inputs

`web/paths.py` handles DB path resolution, session index CSV fallback,
DLC project config (Stage 2 layout preferred), arena-zone output
directories, and mount-alias normalization (§1.5). The FastAPI server
uses `ProjectConfig` from `mus1.yaml` instead.

---

## 11. Environment

- Python env: `mus1-dev` conda env (`~/miniconda3/envs/mus1-dev`)
- Runs on Chinook via SSH port-forward for Streamlit
- Slurm jobs submit to `bio` (preferred) or `t1small` (overflow)
- DB: SQLite (rebuildable from JSONs); Postgres remains a future option

---

## 12. Lessons learned during the rewrite

### What worked well
- Experiment JSONs as single source of truth (metadata + QC + metrics +
  provenance in one file)
- 4-point wedge marking for EZM (simple, fast, reliable)
- 8-variant calculation comparison for visual QC of analysis methodology
- Cohort auto-summary computation on save (no stale counts)
- QC flag audit history (append-only, operator attribution)
- Three-tier sidebar contract (Scope · Filters · Display) — one filter
  module owns state for every pane

### What didn't work / needed fixing
- Hardcoded task types scattered across 10+ files — replaced by
  `TaskRegistry`.
- `video: null` / `qc_flags: null` in some JSONs crashed parsers using
  `.get(key, {})` — `.get()` returns the stored `None`, not the
  default. Use `or {}` everywhere.
- Session index CSV contract was fragile (manual refresh after
  rebuilds) — replaced by `ExperimentService` scanning JSONs directly.
- 6 separate importers writing the same tables — replaced by
  `ExperimentService` scan.
- NOR/NOF object names hardcoded to `object_a`/`object_b` —
  `ObjectDefinition` is configurable per task.
- `@st.cache_data` was the only caching; NOR/NOF views had none —
  service layer uses an in-memory dict cache with explicit invalidation.
- `ezm_compute_bridge.py` used `sys.path.insert()` to reach the workspace —
  extracted into `mus1.compute.ezm_zones_model`.
- DLC CSV reading was duplicated in 3 files — consolidated into
  `mus1.compute.tracking`.
- FastAPI TestClient needs `httpx` (not installed by default with
  `fastapi`).
- `TaskDefinition` attribute names: it's `qc_flag_vocabulary`, not
  `qc_auto_flag_names` — always check the actual API before wiring.
- DLC schema duality: legacy `tracking_file_path` vs.
  new `dlc_runs[*].output.csv`. Solved by `discovery.resolve_dlc_csv_path`.
- Hidden hard-filters in QC panes (NOR/NOF Interaction QC required
  `computed_metrics` to even show an experiment) silently excluded
  freshly-tracked cohorts. The QC pane contract (§1.2) prevents the
  recurrence.

### My points for app improvement (-lp, 3/14/26)
- Eventually I want to build the app to be essentially an LLM-wrapped
  / MCP-wrapped tool. Each lab is going to be storing and have
  different compute in different places, and it doesn't really make
  sense to support all of it. What does make sense is to integrate the
  consistently used stats and the actually-good layouts in a way that
  should stay deterministic where it must be deterministic, and build
  the app around an easy stochastic implementation where things are
  going to be modulable per lab. Current-era design.
- I also want to be able to support saving annotated frames from final
  QC images for things that are relevant to a publication — e.g. "we
  verified this" should produce a frame export easy to include in a
  supplement when somebody provides their data for review.
