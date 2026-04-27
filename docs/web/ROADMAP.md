# MUS1 Web App Roadmap

Priorities for the mus1 platform. Ordered by impact.

**Last updated:** 2026-03-27

## Current project context

mus1 is being **rewritten from Streamlit to FastAPI + React** for open-source release targeting rodent behavior labs. The core value — annotation workflows, experiment JSON as source of truth, calculation variant comparison, and QC with provenance — is preserved. Hardcoded task types, cluster paths, and object definitions are being replaced with a configurable task definition system.

Full rewrite plan: `~/.claude/plans/ancient-jumping-ritchie.md`
Manuscript skeleton: `reports_workspace/manuscript_unified.tex`
Per-task methods+results: `reports_workspace/{ezm,nof_nor,of,rr}/*_methods_results.md`

## What work happens where (Streamlit pane map)

Quick reference for "which pane do I use for X?" Each row lists the pane,
the canonical task you use it for, what it reads from disk, and what it
writes back. All panes scan the canonical data roots
(`experiment_data/` + `validation_data/`) — see
[`AGENT_RUNBOOK.md`](AGENT_RUNBOOK.md) for the discovery rules.

| Pane | Use it for | Reads | Writes |
|---|---|---|---|
| **Subjects** | Per-subject summary across all task types | `subjects` SQLite table + experiment JSONs (for timepoint enrichment) | — |
| **Experiments** | Browse all experiments, filter by task/cohort/QC | `experiments` SQLite table | — |
| **Cohort Management** | Add/remove members, create cohorts, export training CSVs | All experiment JSONs across both data roots; `data/cohorts/*.json` | `data/cohorts/*.json` (members[], description, summary block recomputed on save) |
| **EZM Wedge Marking** | Click 4 wedge points on a frame to define EZM arena | EZM experiment JSONs (`arena_markings.ezm_wedge_points` empty) | EZM JSON: `arena_markings.ezm_wedge_points.points[]` + provenance |
| **EZM Zones QC** | Visually approve/reject the wedge-fit circle overlay | EZM JSON `arena_markings.ezm_wedge_points` + computed circle fit | EZM JSON: `arena_markings.ezm_wedge_points.qc.{status,notes,reviewed_at}` |
| **EZM Tracking QC** | Approve DLC tracks against marked arena (per-experiment) | EZM JSON + DLC CSV + 8-variant computed metrics | EZM JSON: `computed_metrics.ezm_open_closed.qc_review.{status,notes}` |
| **EZM ML** | Submit U-Net training jobs, review predicted-mask QC | Cohort JSON + EZM masks (`mus1.compute.ezm_masks`) | Slurm job submission via `mus1_runs/` registry |
| **NOR/NOF ROI** | Select arena ROI for one experiment (legacy alias) | NOR/NOF JSON `arena_markings.arena_boundary` | Same field |
| **NOR/NOF Object Marking** | Click left + right object centers on a frame | NOR/NOF JSON without `arena_markings.object_left_xy` | NOR/NOF JSON: `arena_markings.object_left_xy`, `object_right_xy`, optional task-type fix |
| **NOR/NOF Object QC** | Visually approve object marks + arena ROI | NOR/NOF JSON + paired-experiment lookup | NOR/NOF JSON: `object_qc.{status,notes,reviewed_at}` |
| **NOR/NOF Interaction QC** | Approve interaction zones (radius around objects) + nose trajectory | NOR/NOF JSON + DLC CSV | NOR/NOF JSON: `computed_metrics.nor_nof.qc_review` |
| **Annotator** | Generic launcher; hands off to the right marking pane based on task type | — | — |
| **ML Genotype** | Build datasets, submit training, monitor learning curves | Cohort JSON + per-experiment KPMS labels | Dataset YAML + Slurm submission via `mus1_runs/` |
| **Training Monitor** | Slurm job status + metric trend plots for U-Net + ML tracking | `mus1_runs/` registry, log files in `ml_workspace/*/logs/` | — |

**Conventions:**
- "Reads" and "Writes" are about per-experiment JSONs; the `mus1.db` SQLite is a rebuildable index, not a source of truth.
- Marking panes auto-discover work to do by scanning JSONs for an empty/missing `arena_markings.*` block; the count is recomputed on each page load (cached for 5 min — hit the sidebar Refresh after intake to invalidate sooner).
- QC panes write a structured `qc` or `qc_review` block alongside the data they reviewed, with `reviewed_at` timestamps and optional operator notes; nothing is overwritten silently.

**Adding new experiments** is purely a "drop the JSON in the right place"
operation — there is no registration step. See `AGENT_RUNBOOK.md` §3 for
the canonical layout. After files land on disk, the relevant panes will
list them within one cache TTL window (5 minutes) or immediately on
sidebar refresh.

## Open-source rewrite (active)

### Phase 1: Task Definition System — COMPLETE (2026-03-27)
- `TaskDefinition` ABC with annotation fields, arena geometry, QC flags, calculation variants
- 5 built-in tasks: EZM (8 variants), NOR, NOF, OF, RR
- `TaskRegistry` loads builtins + custom YAML tasks (`mus1_tasks.yaml`)
- `ProjectConfig` replaces hardcoded `paths.py` with `mus1.yaml`
- `YAMLTaskDefinition` allows agents/labs to define tasks without Python
- Files: `src/mus1/tasks/`, `src/mus1/server/config.py`

### Phase 2: Service Layer + Compute Extraction — COMPLETE (2026-04-01)
- `ExperimentService`: consolidated experiment discovery (895 experiments, <5s scan, <1ms cached). Fixed: RR JSONs have `video: null` / `qc_flags: null` — use `or {}` not `get(key, {})`.
- `CohortService`: wraps existing cohorts.py with ExperimentService-backed metadata resolution
- `QCService`: task-registry-aware auto-flag computation (delegates to TaskDefinition)
- `AnnotationService`: annotation read/write with provenance frame export (PNG overlay)
- Compute library: 7 modules extracted (~3500 LOC) — arena_geometry, ezm_zones_model, ezm_zones, tracking, nor_nof_interaction, overlay, ezm_masks
- `ComputeHarness`: determinism check, parameter sweep, snapshot regression, benchmark, human-readable reports
- Session index CSV deprecated; experiment JSONs declared sole source of truth
- Files: `src/mus1/server/services/`, `src/mus1/compute/`

### Phase 3: FastAPI Backend — COMPLETE (2026-04-01)
- 6 routers: `/api/tasks`, `/api/experiments`, `/api/cohorts`, `/api/qc`, `/api/annotations`, `/api/compute`
- 19 endpoints, all tested against 895 real experiments (19/19 pass)
- OpenAPI spec auto-generated at `/docs` (Swagger UI) and `/openapi.json`
- CLI: `mus1 serve --data-root PATH --port 8100`
- Dependency injection via `ServiceContainer` (singleton services per app lifetime)
- Video frame extraction as JPEG, provenance overlay as PNG
- Compute endpoint: NOR/NOF interaction metrics computed on-demand from DLC CSV + arena markings
- Files: `src/mus1/server/app.py`, `src/mus1/server/deps.py`, `src/mus1/server/routers/`

### Phase 4: React Frontend — PLANNED
- Vite + React Router + TanStack Query + Tailwind
- Fabric.js/Konva.js annotation canvas (replaces streamlit-drawable-canvas)
- Pages: ExperimentBrowser, AnnotationWorkflow, QCReview, VariantComparison, CohortManagement
- Static build bundled in pip package (no Node.js on HPC at runtime)

## Manuscript-related work (continuing in parallel)

### EZM tracking QC completion
- Phase 3 visual QC: sort 155 experiments by artifact_rate, review in tracking QC pane
- Mark QC status in experiment JSONs via app
- Consensus multi-track overlay (head=blue, neck=green, nose=orange) already implemented

### NOR/NOF QC flags in views
- QC flags seeded on all 339 experiments (shared module `qc_flags_shared.py`)
- Wire flags into NOR/NOF views
- 5 new partner experiments need arena marking in app

### EZM arena annotation: COMPLETE
All 171 EZM experiments marked and QC-passed. 4-point wedge marking approach fully deployed.

### Configurable object definitions: ADDRESSED IN PHASE 1
The task definition system makes object names, counts, and roles configurable per task. NOR/NOF `ObjectDefinition` supports any number of objects with custom labels and roles. Pilot NOR (P_NO) can define its own object set via YAML.

## Future research (deferred, tracked)

These features are in research/exploration phase. They will be revisited when the core platform is stable and their upstream dependencies mature.

| Feature | Depends on | Notes |
|---------|-----------|-------|
| Arena inference (automated boundary detection) | U-Net training pipeline, geometric fitting | EZM: U-Net predicts open/closed masks. NOR/NOF: brightness edge detection. Would reduce manual annotation burden at scale. |
| ML genotype classifier | KPMS syllable extraction complete | Predict genotype/phenotype from behavioral syllable profiles. Promising but needs more data. |
| ML tracking metadata model | KPMS extraction + cross-task fingerprint | Classify sessions by behavioral regime. Currently stale (was built on trim30s syllables). |
| Figure viewer + stats integration | Stats package extracted as separate pip package | Display generated figures in app, trigger stats re-runs, diff outputs |
| Training monitor for DLC/SLEAP | React UI rebuild | Monitor GPU job status, view training curves. Project-specific but useful for any lab training models on cluster. |

## Lower priority

### DB schema evolution
- Current schema uses `create_all()` (no migrations) — Phase 3 will add versioned forward-only migrations
- SQLite stays as rebuildable cache; experiment JSONs remain source of truth

### Path alignment: ADDRESSED IN PHASE 1
- `ProjectConfig` (`mus1.yaml`) replaces all hardcoded paths
- Mount-alias normalization (`/center1` vs `/import/c1`) no longer needed — paths are relative to project root

## Completed

- Streamlit web app with 14 view modes
- CLI import pipeline (workspace-db-sync, arena-zones, rotarod, KPMS, EZM/ML runs)
- mus1.db schema (subjects, experiments, artifacts, QC events, assay data)
- EZM annotator: 4-point wedge marking, full zone annotation, undo/clear, preview overlay
- NOR/NOF v2 annotation flow (clean reset, embedded annotator handoff)
- EZM compute bridge: 8 zone classification variants, consensus multi-bodypart voting
- EZM tracking QC pane: frame navigation, crosshair trajectory, variant selector
- NOR/NOF object marking: all 339 sessions marked, arena_boundary geometric circle fit
- Cohort management view (all task types)
- QC flags system: unified schema across EZM/NOR/NOF, auto-flags + manual status
- ML tracking training submission with MUS1 run records
- Mount-alias aware path deduplication
- Training monitor with Slurm job status and metric plots
- RR publication cohort built (135 sessions, 45 subjects)
- All 4 publication cohort JSONs created (`data/cohorts/`)
- **Phase 1: Task definition system** (2026-03-27) — 5 built-in tasks, YAML extensibility, configurable objects
- **Phase 2 (partial): Service layer** (2026-03-27) — ExperimentService, CohortService, QCService, AnnotationService, compute README

## Lessons learned during rewrite

### What worked well in the original app
- Experiment JSON as single source of truth (metadata + QC + metrics + provenance in one file)
- 4-point wedge marking for EZM (simple, fast, reliable)
- 8-variant calculation comparison for visual QC of analysis methodology
- Cohort auto-summary computation on save (no stale counts)
- QC flag audit history (append-only, operator attribution)

### What didn't work / needed fixing
- Hardcoded task types scattered across 10+ files — now replaced by TaskRegistry
- `video: null` in RR JSONs crashed parsers that used `.get("video", {})` — Python's `.get()` returns the stored `None`, not the default. Use `or {}` pattern.
- Session index CSV contract was fragile (needed manual refresh after rebuilds) — replaced by ExperimentService scanning JSONs directly
- 6 separate importers for different data sources — replaced by single ExperimentService scan
- NOR/NOF object names hardcoded to `object_a`/`object_b` — now configurable via ObjectDefinition
- Streamlit `@st.cache_data` was the only caching; NOR/NOF views had no caching at all — service layer uses in-memory dict cache with explicit invalidation
- `ezm_compute_bridge.py` used `sys.path.insert()` to import `ezm_open_closed_zones` from workspace — extracted into proper package import `mus1.compute.ezm_zones_model`
- DLC CSV reading was duplicated in 3 files (ezm_compute_bridge, nor_nof_object_interactions, overlay) — consolidated into `mus1.compute.tracking`
- FastAPI TestClient needs `httpx` package (not installed by default with fastapi)
- `TaskDefinition` attribute names differ from what was assumed in router code (`qc_auto_flag_names` doesn't exist, it's `qc_flag_vocabulary`) — always check actual API before wiring
- **Phase 1 → 2 → 3 completed in one session** (2026-04-01): task registry, service layer, compute extraction, harness, FastAPI backend with 19 tested endpoints
