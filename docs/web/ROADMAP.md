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

| Group | Pane | Use it for | Reads | Writes |
|---|---|---|---|---|
| Browse | **Subjects** | Per-subject summary across all task types | `subjects` SQLite table + experiment JSONs (for timepoint enrichment) | — |
| Browse | **Experiments** | Browse all experiments, filter by task/cohort/QC | `experiments` SQLite table | — |
| Mark | **EZM Wedge Marking** | Click 4 wedge points on a frame to define EZM arena | EZM experiment JSONs (`arena_markings.ezm_wedge_points` empty) | EZM JSON: `arena_markings.ezm_wedge_points.points[]` + provenance |
| Mark | **NOR/NOF Object Marking** | Click left + right object centers on a frame | NOR/NOF JSON without `arena_markings.object_left_xy` | NOR/NOF JSON: `arena_markings.{object_left_xy,object_right_xy,arena_boundary}`, optional task-type fix |
| QC | **EZM Zones QC** | Visually approve/reject the wedge-fit circle overlay | EZM JSON `arena_markings.ezm_wedge_points` + computed circle fit | EZM JSON: `arena_markings.ezm_wedge_points.qc.{status,notes,reviewed_at}` |
| QC | **EZM Tracking QC** | Approve DLC tracks against marked arena (per-experiment) | EZM JSON + DLC CSV + 8-variant computed metrics | EZM JSON: `computed_metrics.ezm_open_closed.qc_review.{status,notes}` |
| QC | **NOR/NOF Object QC** | Visually approve object marks + arena ROI | NOR/NOF JSON + paired-experiment lookup | NOR/NOF JSON: `object_qc.{status,notes,reviewed_at}` |
| QC | **NOR/NOF Interaction QC** | Approve interaction zones (radius around objects) + nose trajectory | NOR/NOF JSON + DLC CSV | NOR/NOF JSON: `computed_metrics.nor_nof.qc_review` |
| Cohort | **Cohort Management** | Add/remove members, auto-link NOR↔NOF pairs, export training CSVs | All experiment JSONs across both data roots; `data/cohorts/*.json` | `data/cohorts/*.json` (members[], description, summary block recomputed on save); per-experiment `nor_nof_pair` blocks |
| Train | **EZM ML** | Submit U-Net training jobs, review predicted-mask QC | Cohort JSON + EZM masks (`mus1.compute.ezm_masks`) | Slurm job submission via `mus1_runs/` registry |
| Train | **ML Genotype** | Build datasets, submit training, monitor learning curves | Cohort JSON + per-experiment KPMS labels | Dataset YAML + Slurm submission via `mus1_runs/` |
| Train | **Training Monitor** | Slurm job status + metric trend plots for U-Net + ML tracking | `mus1_runs/` registry, log files in `ml_workspace/*/logs/` | — |

Removed in 2026-04-27 cleanup: `Annotator` (legacy embed of arena_annotation app, separate discovery), `NOR/NOF QC` aka "Paired QC Review" (CSV-driven), `NOR/NOF ROI` (CSV-driven). All three were superseded by the per-task Mark/QC panes above.

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

## Streamlit UI overhaul plan (2026-04-27)

The current Streamlit app accumulated multiple generations of marking/QC
flows over the manuscript push: a mix of "good" per-task panes, "legacy"
CSV-driven panes, and an embedded `Annotator` that duplicated discovery
logic. The roadmap below cuts that surface area down so each lifecycle
stage has exactly one pane, every loader uses the multi-root discovery
layer, and cohort affordances cover the gaps that previously required
shell scripts (NOR↔NOF pairing, cohort task-type filters).

### Iteration 1.5 — UI standardization (DONE 2026-04-28)

Three-tier sidebar contract (Scope · Filters · Display) backed by a single
shared module. Concrete deliverables:

- **`web/filters.py`** — single source of truth for filter state and UI:
  - `FilterState` (frozen dataclass): cohort + marking_status + qc_statuses
    + genotypes + sexes + text + date_range. Pure data; testable without
    a Streamlit runtime.
  - `render_scope_picker(project_path)` — universal cohort selector at
    the top of the sidebar; persists to `st.session_state[SCOPE_KEY]`.
  - `render_filters(rows, fields, key_prefix, marking_field, qc_field)`
    — renders the standard "Filters" expander, returns
    `(state, filtered_rows)`. Filter widgets only render when the pane
    opts in via `fields={…}` (subset of `KNOWN_FIELDS`).
  - `mode_settings(label, key_prefix)` — context manager that opens the
    standard "Display" expander for pane-specific toggles (overlays,
    color choices, frame stride, …).
  - `filter_by_cohort(rows, cohort, project_path)` — predicate used by
    every loader-consumer.
  - `pkey(pane, widget)` — namespaced key builder, prevents silent
    state-bleed between panes.
  - `invalidate_after_write()` — replaces scattered
    `st.cache_data.clear()` calls; called once per JSON write.
- **Sidebar layout** in every migrated pane is now identical:
  Scope (top) → View radio → Filters expander → Display expander.
- **Migrated panes:** `EZM Zones QC`, `EZM Tracking QC`, `EZM Wedge
  Marking`, `NOR/NOF Object QC`, `NOR/NOF Object Marking`,
  `NOR/NOF Interaction QC`. Each lost its bespoke Cohort/Genotype/Sex/
  Status/Search filter widgets; gained the shared ones (which adapt
  automatically to additions like new genotypes or QC statuses).
- **Cohort Management** retains its own "cohort being edited" picker
  plus its data-source / unassigned-only filters (cohort-add-specific),
  but now also honors the universal scope picker — set scope to cohort
  X, edit cohort Y, and the add-experiments pool restricts to X's
  members. Surfaces a banner so the side-effect is obvious.
- **Net code:** `web/filters.py` is ~370 LOC; net diff across panes is
  −300 LOC after consolidating duplicate filter blocks.

### Iteration 1 — Pane consolidation (DONE 2026-04-27)
- **Removed (file deleted + sidebar entry dropped):**
  `Annotator` (`views/annotator_embed.py`), `NOR/NOF QC` aka "Paired QC
  Review" (`views/nor_nof_qc.py`, CSV-driven), `NOR/NOF ROI`
  (`views/nor_nof_roi.py`, CSV-driven). Each was superseded by a per-task
  pane that uses the canonical experiment-JSON discovery.
- **Promoted to top-level pane:** `EZM Wedge Marking`. Previously only
  reachable through the deleted Annotator embed; now first-class.
- **Sidebar ordering:** grouped by lifecycle (Browse → Mark → QC →
  Cohort → Train) for cognitive load reduction. Mark panes immediately
  precede their QC pane.
- **Cohort task_types auto-fill:** `cohorts.save_cohort()` now derives
  `task_types` from `summary.task_type_counts` whenever the field is
  empty. Fixes the EZM Tracking/Zones QC cohort dropdown silently
  hiding cohorts (e.g. `validation_2026` had no `task_types` so
  `list_cohorts(task_type="EZM")` filtered it out).
- **NOR↔NOF auto-pair:** new `link_nor_nof_pairs()` in `cohorts.py`
  joins by `(subject_id, date_recorded)`; surfaced as
  `mus1 cohort link-nor-nof [<cohort>]` and a button in the Cohort
  Management pane. Idempotent; flags conflicts; never overwrites an
  existing-but-different link.

### Iteration 2 — One-stop "Marking Dashboard" landing pane (NEXT)

With the shared filter module in place from Iteration 1.5, this is now
straightforward: the dashboard reuses `render_filters` against the
discovery output and emits one row per (task, marking-status) pairing
with deep-links into the relevant pane.


Replace the current "Subjects/Experiments" landing with a dashboard that
shows, at a glance, what work is owed across every cohort:

  EZM       │ N experiments need wedge points  · click → Wedge Marking
  EZM       │ N experiments need zone QC       · click → Zones QC
  NOR/NOF   │ N experiments need object marks  · click → Object Marking
  NOR/NOF   │ N experiments need object QC     · click → Object QC
  NOR/NOF   │ N experiments unpaired           · click → "Auto-link" flow
  …

Each row is one filter applied to the canonical discovery scan. The
target pane opens with the filter pre-applied (Streamlit query params).
Implementation: ~150 LOC in a new `views/marking_dashboard.py`; reuses
the existing per-pane filter predicates verbatim.

### Iteration 3 — Surface QC gaps, not just marking gaps
Today the marking dashboards count "missing arena_markings.X." Add the
mirror counts for QC: "marked but not yet QC-approved/rejected." Wire
this through the same dashboard.

### Iteration 4 — Cohort templates
Half the cohort JSONs in `data/cohorts/` are minor variants of one
another (publication cohorts per task, validation cohort, pilots).
Add a "Clone cohort with filter" UI and corresponding `mus1 cohort
clone <src> <dst> --add-where ...` so common operations (e.g. "make a
QC-only subset of the publication cohort") don't require hand-editing
JSON.

### Iteration 5 — Phase 4 React rewrite
Existing roadmap goal. The work above intentionally minimises
"Streamlit-shaped" features so the React port can lift each pane
1:1 against the FastAPI service layer (`server/services/`) without
inheriting Streamlit-specific affordances (caching contracts,
session_state hacks, etc.).

### Loose ends for future iterations
- `views/ezm_ml.py` still uses `sys.path.insert()` to reach
  `workspace/torch_ml/`; should move into `mus1.compute.ezm_zones_model`.
- `views/experiments.py` still uses the legacy `has_nor_nof_roi` artifact
  flag in its filter; that flag was meaningful when the v2 ROI pane
  produced its own JSONs but is now redundant with `arena_markings`.
- `mus1.db` is a rebuildable index but several views still query it
  directly (`Subjects`, `Experiments`); migrating those to
  `ExperimentService` keeps a single discovery contract.

---

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
