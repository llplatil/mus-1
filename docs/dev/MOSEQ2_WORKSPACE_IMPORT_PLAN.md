# MoSeq2 Workspace → MUS1 DB Import Plan (branch: `feature/moseq2-workspace-import`)

## Goal (this branch)

Create a **first-class import path** from this MoSeq2 analysis workspace (`moseq2_workspace/`) into a MUS1 project database (`mus1.db`) so that:

- MUS1 can **represent sessions/recordings** as `subjects` + `experiments` + `videos` (existing tables).
- The MoSeq2 workspace artifacts (MoSeq2 `.h5` results, YAMLs, metadata JSON, syllable UUID maps, arena ROI JSONs, downstream stats outputs, **rotarod rerun tables**, and **KPMS trimmed-30s reruns**) become **queryable DB records** with **provenance**, without requiring ingesting huge arrays into SQL.
- The resulting DB schema stays **portable** (SQLite now; later Postgres on Chinook).

Hard constraint for Chinook storage:

- **Do not copy videos** into a MUS1 project folder for this dataset. Persist **absolute file locations** (and optionally content hashes) into the DB. This keeps disk usage bounded under the Chinook quota.

This document is planning + orientation only. Implementation should follow MUS1’s existing service/repository layering (see `docs/dev/ARCHITECTURE_CURRENT.md`).

## Current state (what exists today)

### MUS1 core data model (already implemented)

MUS1 already has project-local tables for:

- `subjects` (`SubjectModel`)
- `experiments` (`ExperimentModel`) with `processing_stage`
- `videos` (`VideoModel`) with `(path UNIQUE, hash NOT NULL)`
- `experiment_videos` many-to-many association
- plus lab/user tables that are orthogonal to this import

These live in:

- `src/mus1/core/schema.py`
- `src/mus1/core/repository.py`
- `src/mus1/core/project_manager_clean.py`

### MoSeq2 workspace “index of record”

The most useful “single source of truth” for import is:

- `ml_tracking_metadata_model/index/session_index_filtered.csv`
  - Contains (at least): `session_id`, `task`, `subject_id`, `recording_date`, `birthdate`, `sex`, `genotype`, `treatment`, `arena_bucket`
  - Contains paths to key artifacts such as:
    - `moseq2_results_h5_path` (aggregate results `.h5`)
    - `moseq2_results_yaml_path` (proc `results_00.yaml`)
    - `moseq2_metadata_path` (`metadata.json`)
    - `moseq2_identifier_path` (a MUS1 identifier file already exists in this workspace)
    - `syllable_uuid` (UUID for this session) + `syllable_stats_path` (CSV)
- `ml_tracking_metadata_model/index/syllable_uuid_map.csv`
  - Maps `uuid → h5_path/session_name/start_time/subject_name/group`

Critical workflow note from this workspace:

- `session_index_filtered.csv` is not “hand-edited”; it is the output of a multi-source build + filter pipeline:
  - built by `ml_tracking_metadata_model/scripts/build_session_index.py` (joins rosters + MP4 identifiers + KPMS recordings + MoSeq2 identifiers)
  - filtered by `ml_tracking_metadata_model/scripts/filter_session_index.py` (enforces required labels/paths per task; de-dups `session_id`)
- Therefore MUS1 should **consume the compiled index as the data contract**, and record **its provenance** (which index file, which workspace root, and ideally the `integrity_report.txt` summary) rather than re-implementing indexing heuristics inside MUS1.

### Subject rosters (additional sources of truth; required)

These already exist and should be treated as independent, partially-trustworthy sources:

- `resources/metadata/subjects_roster.csv`
  - Minimal “authoritative” per-subject info (tag, genotype, sex, birthdate, treatment type)
- `resources/metadata/open_field_roster.cleaned.csv`
  - Session-level OF info (tag, genotype/sex/birthdate/treatment, test_date, bucket_type, notes)

Plan requirement: before “final DB build”, run integrity checks that **cross-compare multiple sources** (rosters, session indexes, and any identifier JSONs), and record mismatches as structured QC outputs.

### Operational reality: missing/corrupt assets must be first-class

`docs/CURRENT_STATUS.md` shows the real failure modes you already encounter (and work around):

- missing DLC inference outputs for a small subset of recordings
- corrupted MP4s (e.g. “moov atom not found”)
- duplicate/archived sessions and repaired identifiers

The MUS1 import must be **tolerant**:

- do not fail the entire import when a subset is missing
- instead, persist a QC/event record for each missing/corrupt dependency and keep importing the rest

### Rotarod rerun dataset (required)

There is already a cleaned, join-enriched rotarod dataset under:

- `statistics_summaries/rotarod_reanalysis/rotarod_clean.csv` (session-level wide table with QC flags)
- `statistics_summaries/rotarod_reanalysis/rotarod_sessions_cleaned.csv` (session-level long-ish)
- `statistics_summaries/rotarod_reanalysis/rotarod_attempts_long_cleaned.csv` (attempt-level long table)

These should be imported as first-class assay data (not just “artifact pointers”).

### KPMS “trimmed 30s” reruns (required)

There are explicit rerun projects that include trimmed video + CSV inputs and a `recordings.csv` index:

- `analysis_keypoint_moseq/_reruns/20260122_trim30s_ezm/metadata/recordings.csv`
- `analysis_keypoint_moseq/_reruns/20260122_trim30s_nor_nof/metadata/recordings.csv`

These include:

- `input/*.mp4` (trimmed clips; already exist on disk)
- `input/*.csv` (paired tracking/keypoint inputs)
- model outputs under `*_kpms_trim30s_20260122_iters100/`

We should index these reruns in the same way we index the baseline KPMS projects, but without copying any video content into a MUS1 project directory.

### Arena annotations + task metrics already exist (workspace side)

Arena annotation produces **versioned per-video JSON files** used by downstream scripts:

- EZM zones:
  - `resources/arena_zones/ezm_per_video_v2/<video_stem>_ezm_open_closed_v2.json`
- NOR/NOF object ROIs:
  - `resources/arena_zones/nor_nof_per_video_v1/<video_stem>_nor_nof_objects_v1.json`

Arena annotation tool and geometry definitions:

- `scripts/arena_annotation/app.py` (Streamlit UI)
- `scripts/arena_annotation/ezm_geometry.py`
- `scripts/arena_annotation/nor_nof_geometry.py`

Downstream “stats outputs” currently land as CSVs under `statistics_summaries/...` (e.g. NOR/NOF object-interaction metrics from `scripts/statistics_organized/dlc_nor_nof_object_interactions/compute_nor_nof_object_interactions.py`).

## Proposed branch deliverables (incremental)

## Current implementation status (as of 2026-01-28)

Implemented in `feature/moseq2-workspace-import`:

- ✅ **Core tables added**:
  - `external_artifacts`
  - `qc_events`
  - `assay_sessions`
  - `assay_measurements`
- ✅ **MoSeq2 session index importer**:
  - CLI: `mus1 import moseq2-workspace`
  - Reads: `ml_tracking_metadata_model/index/session_index_filtered.csv`
  - Writes: `subjects`, `experiments`, `external_artifacts`, `qc_events` (path-only; missing paths become QC events)
- ✅ **Rotarod ingestion**:
  - CLI: `mus1 import-rotarod`
  - Reads: `statistics_summaries/rotarod_reanalysis/rotarod_attempts_long_cleaned.csv`
  - Writes: `assay_sessions` and `assay_measurements` (preserves exclude/qc fields into measurement qc flags/details)
- ✅ **KPMS trim30s recordings index**:
  - CLI: `mus1 project import-kpms-recordings --workspace-root ... <csv1,csv2>`
  - Indexes the rerun `metadata/recordings.csv` files as `external_artifacts` (path-only; no video copying)
- ✅ **Unified deterministic sync entrypoint** (new):
  - CLI: `mus1 import workspace-db-sync`
  - Runs: session index import + rotarod import + KPMS recordings index in one command.

Not yet implemented (still planned):

- ⏳ Reading/importing additional “sources of truth” (rosters, `syllable_uuid_map.csv`) as first-class inputs.
- ⏳ Dedicated tables like `moseq_sessions` / `moseq_syllable_uuid_map` (beyond generic `external_artifacts`).
- ⏳ `videos.hash` nullable change / new file locator strategy (schema direction still pending).
- ⏳ Export/bundling workflow (`manifest.json` + portable bundle) (Deliverable C).

### Deliverable A — importer creates core entities and indexes (dataset-first)

Implement a new MUS1 import entrypoint that:

- Reads:
  - `ml_tracking_metadata_model/index/session_index_filtered.csv`
  - `ml_tracking_metadata_model/index/syllable_uuid_map.csv` (optional but recommended)
  - `resources/metadata/subjects_roster.csv`
  - `resources/metadata/open_field_roster.cleaned.csv`
  - rotarod reanalysis CSVs under `statistics_summaries/rotarod_reanalysis/`
  - KPMS trimmed-30s rerun `metadata/recordings.csv` for EZM + NOR/NOF reruns
- Upserts:
  - **Subject** per `subject_id` (string)
    - `sex` from `sex`
    - `birth_date` from `birthdate`
    - `individual_genotype` from `genotype`
    - `individual_treatment` from `treatment`
  - **Experiment** per `session_id` (string)
    - `experiment_type` from `task` (e.g. `OF`, `EZM`, `NOR`, `NOF`)
    - `date_recorded` from `recording_date`
    - `processing_stage` derived from artifact presence:
      - baseline: `TRACKED` when `moseq2_results_h5_path` exists
      - optionally: `INTERPRETED` when downstream metric artifacts are present/imported
  - **Video** record + **experiment↔video** link when a stable video identifier is present.

Important constraint (current MUS1 schema): `videos.hash` is **NOT NULL** and `videos.path` is **UNIQUE**. The import needs a stable rule:

- Prefer a workspace-provided stable identifier already in the index:
  - `moseq2_session_name` looks like a stable hex session ID in the CSV.
- Use `video_path` if present; otherwise store the best available path we have (`moseq2_source_filename` alone is not a full path).

If actual video files are accessible at import time, MUS1 can compute its normal sample hash; but the import should not assume that. For Chinook scale and storage limits, we will primarily store:

- the **absolute path** of each video (original or trimmed rerun path), and
- a hash only when the file is reachable and hashing is affordable.

Meaningful refinement (recommended schema change):

- For this dataset-first path-only workflow, change MUS1 `videos.hash` to **nullable** and treat it as an optional optimization (dedupe/verification), not a required field.
- If we later want “stable IDs” independent of path, add a separate `file_locators`/`file_uris` concept rather than overloading `hash`.

### Deliverable B — add queryable “artifact + annotation” tables (recommended)

To support a web app and real querying, avoid storing everything as opaque JSON blobs. Add minimal normalized tables that:

- link artifacts to existing MUS1 entities (`experiments`, optionally `videos`)
- keep raw payload paths + lightweight parsed metadata + provenance

Proposed new tables (names are suggestions; finalize after inspecting existing patterns and tests):

1) `external_artifacts`
- `id` (PK)
- `experiment_id` (FK → `experiments.id`)
- `kind` (string; e.g. `moseq2_results_h5`, `moseq2_results_yaml`, `moseq2_metadata_json`, `syllable_stats_csv`, `dlc_csv`, `ezm_zone_json_v2`, `nor_nof_objects_json_v1`, `stats_output_csv`)
- `path` (text)
- `content_sha256` (nullable; if file reachable)
- `created_at`
- `payload_json` (nullable text; used for small JSON payloads like zone JSON)
- `meta_json` (nullable text; e.g. derived fields like schema version, fps flags, etc.)

2) `moseq_sessions` (optional but useful if we want session-specific fields without abusing experiment notes)
- `session_id` (PK, FK → `experiments.id` OR standalone + FK)
- `syllable_uuid` (nullable; UUID from session index)
- `arena_bucket`, `kpms_recording_id`, `moseq2_session_name`
- any other stable identifiers we rely on

3) `moseq_syllable_uuid_map` (optional)
- `uuid` (PK)
- `group`
- `h5_path`
- `session_name`
- `start_time`
- `subject_name`

Why these tables:
- They let us keep **arena ROI JSONs** and **stats outputs** in the DB with a stable link to an `experiment_id`.
- They are small and portable to Postgres later.
- They don’t force loading huge `.h5` arrays into SQL.

### Deliverable B1 — QC/event table (small, high leverage)

Add a minimal table to record integrity findings without blocking the import:

- `qc_events`
  - `id` (PK)
  - `scope` (e.g. `subject`, `experiment`, `video`, `artifact`)
  - `subject_id` / `experiment_id` (nullable FKs)
  - `code` (e.g. `MISSING_DLC_CSV`, `CORRUPT_MP4`, `ROSTER_MISMATCH`, `DUPLICATE_SESSION_ID`)
  - `details_json`
  - `created_at`

### Deliverable B2 — assay tables for rotarod and other non-video assays (recommended)

Rotarod should not be “shoehorned” into generic plugin JSON results; it is a structured longitudinal assay with attempts/timepoints.

Two reasonable options:

1) **Dedicated rotarod tables**
- `rotarod_sessions` (one row per subject×timepoint session)
- `rotarod_attempts` (one row per attempt within a session)

2) **Generic assay tables**
- `assay_sessions` (assay_type + subject + date + metadata)
- `assay_measurements` (assay_session_id + metric_name + value + units + qc flags)

Given your stated direction (“ideal for this dataset rather than legacy MUS1 decisions”), option (2) is more future-proof, but we should implement it only if we’re committing to a dataset-first schema that will become the web app backend.

### Deliverable C — “export workspace to db” workflow

Add a command that produces a portable bundle:

- `mus1.db` (SQLite) + a `manifest.json` of artifact paths and checksums
- optionally a “copy artifacts into bundle” mode (large; may not be desired)

This aligns with your stated goal: “download the workspace dataset in DB format”.

## Where this logic should live (MUS1-side)

Keep with existing architecture:

- **Parsing/transform**: pure functions (new module, e.g. `src/mus1/core/importers/moseq2_workspace.py`)
- **DB writes**: go through `ProjectManagerClean` and repositories, or add a focused service that uses `RepositoryFactory`
- **CLI entrypoint**: add a `typer` subcommand under `src/mus1/core/simple_cli.py`

If we want this import to be “pluggable” (discoverable in GUI), we can also add it as a MUS1 plugin later, but the first pass should be a deterministic CLI import that can be run headless on Chinook.

## Chinook DB hosting + future web app (high-level direction)

### Step 1: Make MUS1 DB backend configurable

Right now `Database` hardcodes a SQLite file URL:

- `create_engine(f"sqlite:///{db_path}")`

For Chinook hosting we’ll need:

- a DB URL configuration mechanism (env var or config key)
- a migration story (Alembic or equivalent) rather than `create_all()` as the only schema management
- the schema to remain SQLAlchemy-native and Postgres-compatible (types, indexes, constraints)

### Step 2: Web app architecture (target)

- Backend: FastAPI (or similar) with SQLAlchemy session mgmt, auth, and endpoints that query:
  - experiments + linked artifacts
  - arena annotations per video
  - computed stats tables
- Frontend: web UI for browsing sessions and viewing annotations/metrics

This branch is not the web app; it is the data foundation to make that feasible.

## Dataset-first schema direction (explicit)

Your stated intent is to **migrate features one at a time** and remove unnecessary MUS1 components, targeting a web UI (Streamlit or otherwise) backed by a Chinook-hosted DB.

That implies a sequencing change:

- Treat the **DB schema + import + QC** as the primary product.
- Treat the existing MUS1 Qt GUI as non-goal for this branch (and likely removable once the web UI replaces it).

Concretely, for implementation we should prefer:

- A schema that models your dataset explicitly:
  - subjects (from roster)
  - sessions/recordings (OF/EZM/NOR/NOF + KPMS reruns + rotarod)
  - artifacts/annotations (zone JSONs, MoSeq2 outputs, KPMS outputs, stats tables)
  - QC findings (mismatches across rosters/index/identifiers)
- A web-facing API/UI layer that queries those tables directly.

## GitHub privacy (repo visibility)

This working copy is connected to the GitHub repo via `origin = https://github.com/llplatil/mus-1.git`.

I can’t switch visibility from here because the GitHub CLI (`gh`) isn’t installed in this environment. The most reliable path is:

- In GitHub UI: repo `Settings → General → (Danger Zone) Change repository visibility → Make private`

If you install `gh` on the machine where you manage repos, the equivalent is:

```bash
gh repo edit llplatil/mus-1 --visibility private
```

## Immediate next steps (actionable)

1) Define the **authoritative import inputs**:
   - `ml_tracking_metadata_model/index/session_index_filtered.csv`
   - `resources/metadata/subjects_roster.csv`
   - `resources/metadata/open_field_roster.cleaned.csv`
   - `statistics_summaries/rotarod_reanalysis/rotarod_clean.csv` (and its long-form companions)
   - KPMS trimmed reruns:
     - `analysis_keypoint_moseq/_reruns/20260122_trim30s_ezm/metadata/recordings.csv`
     - `analysis_keypoint_moseq/_reruns/20260122_trim30s_nor_nof/metadata/recordings.csv`
   - arena zones directory/directories to include
   - which `statistics_summaries/...` outputs should be first-class DB tables vs “artifact pointers”

2) Decide the **video identity rule** for MUS1 `videos`:
   - whether `moseq2_session_name` becomes the canonical `VideoModel.hash` when files aren’t readable

3) Implement Deliverable A (core entity import), then expand to Deliverable B (artifact/annotation tables).

