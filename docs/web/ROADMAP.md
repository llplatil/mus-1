# MUS1 Web App Roadmap

Priorities for the Streamlit web app and CLI toolset. Ordered by impact on the current workflow.

**Last updated:** 2026-03-12

## Current project context

The project is assembling a **single unified manuscript** covering all 4 behavioral tasks (EZM, NOR/NOF, OF, RR) plus a cross-task phenotypic fingerprint and ML validation. The app's role is shifting from annotation/QC toward **figure generation, stats iteration, and cohort management**.

Full execution plan: `~/.claude/plans/deep-juggling-sundae.md`
Manuscript skeleton: `reports_workspace/manuscript_unified.md`
Per-task methods+results: `reports_workspace/{ezm,nof_nor,of,rr}/*_methods_results.md`

## Active work

### Publication figure generation and QC (HIGH PRIORITY)

The unified manuscript needs consistent figures across all 4 tasks. Stats scripts produce figures but iteration requires:

- **Figure viewer in app**: Display generated figures from `statistics_workspace/output/*/figures/` with experiment drill-down
- **Cohort management view**: Already exists (`views/cohort_management.py`) — extend to show all 4 cohort JSONs side-by-side with group balance summaries
- **Stats re-run trigger**: Button to re-run a publication stats script and diff output against prior run

Current figure outputs:
- EZM: `statistics_workspace/output/ezm_publication_stats_20260310/figures/` (6 figs, regenerating from no-trim)
- NOR/NOF: `statistics_workspace/output/nor_nof_publication_stats_20260311/` (figures pending)
- RR: `statistics_workspace/output/rr_publication_stats_20260312/figures/` (4 figs, complete)
- OF: blocked on MoSeq2 pipeline

### EZM tracking QC completion

- Phase 3 visual QC: sort 155 experiments by artifact_rate, review in tracking QC pane
- Mark QC status in experiment JSONs via app
- Consensus multi-track overlay (head=blue, neck=green, nose=orange) already implemented

### NOR/NOF QC flags in views

- QC flags seeded on all 339 experiments (shared module `apps/mus1/src/mus1/web/qc_flags_shared.py`)
- Wire flags into NOR/NOF views (Phase 2c-app from NOR/NOF pipeline plan)
- 5 new partner experiments need arena marking in app

### EZM arena annotation: COMPLETE

All 171 EZM experiments marked and QC-passed. 4-point wedge marking approach fully deployed.

## Pipeline status (data feeding the app)

| Pipeline | Status | Blocking |
|---|---|---|
| EZM DLC | Complete (155/155) | Nothing |
| NOR/NOF DLC | Complete (339/339) | Nothing |
| EZM KPMS no-trim | Fitting Stage 2 (job 573050, bio) | Stats regeneration |
| NOR/NOF KPMS no-trim | Fitting Stage 2 (job 573051, t1small) | Stats regeneration |
| OF MoSeq2 kappa scan | Running (job 575828, t1small) | OF stats script |
| RR stats | Complete (135 sessions, 8 tables, 4 figs) | Nothing |
| Cross-task fingerprint | Not started | KPMS extraction + OF pipeline |
| ML tracking model | Stale (trim30s syllables) | KPMS extraction |

## Next priorities

### Experiment JSON → app pipeline

Workprocesses that create outputs need to write paths to experiment JSONs. The app should not auto-update the DB — require explicit trigger:
1. Script writes output path to experiment JSON (`computed_metrics`, `artifacts`)
2. User triggers `mus1 import workspace-db-sync` (or app button)
3. DB reflects current JSON state

See `data/DATA_ARCHITECTURE.md` for full data flow rules.

### Experiment browser improvements

- Show per-experiment artifact summary (what exists, what is missing)
- Surface QC flags inline with experiment detail
- Filter/sort by cohort membership, QC status, annotation status

### Reports workspace integration

- Link `statistics_workspace/output/*/figures/` to experiments that contributed to them
- Display figure thumbnails in experiment detail view

## Lower priority

### DB schema evolution

- Current schema uses `create_all()` (no migrations)
- `videos.hash` is NOT NULL but imports rarely have hashes — consider nullable
- Postgres migration story needed if shared access required

### Path alignment (partially done)

| Issue | Status |
|---|---|
| DLC project discovery | Partially fixed in `paths.py` |
| Session index resolution | Contract copy works; needs refresh after rebuilds |
| Project path default | Document `--project-path /path/to/WDMOSEQ2/data` |

### Legacy desktop GUI

Code in `src/mus1/gui/` is not used. No active work planned.

## Completed

- Streamlit web app with 8+ view modes
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
