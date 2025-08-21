### MUS1 Roadmap — Authoritative

This roadmap reflects how the code works today and what is planned next. It avoids dates and versions; items are prioritized by impact and risk.

## What works today (observed in code)
- Project lifecycle and persistence via `ProjectManager`; default projects live under `~/MUS1/projects` (env override `MUS1_PROJECTS_DIR`).
- Shared projects directory via `MUS1_SHARED_DIR` with advisory `.mus1-lock` during saves; CLI and GUI can create/list/switch to shared projects.
- Dynamic plugin discovery and registration from `src/mus1/plugins/*` with `PluginManager` indices by readable formats and capabilities.
- Analysis orchestration: `ProjectManager.run_analysis(experiment_id, capability)` validates via plugin, calls `analyze_experiment`, stores results, and advances `processing_stage` when appropriate.
- Data IO helpers in `DataManager`: `read_yaml`, `read_csv`, `read_hdf`; handler invocation through `call_handler_method`.
- Video discovery and ingestion: pluggable scanners (`macOS` specialized, base for others), `discover_video_files`, `deduplicate_video_list`, and unassigned→assigned workflow using `sample_hash` keys.
- Typer CLI (`mus1`) with commands: `scan videos`, `scan dedup`, `project add-videos`, `project list`, `project create`, `project scan-and-add`.
 - Typer CLI (`mus1`) with commands: `scan videos`, `scan dedup`, `project add-videos`, `project list`, `project create`, `project scan-and-add`, and `project scan-from-targets` (now with `--dry-run` and `--emit-*`). Root supports `--version`.
- UI: `ExperimentView` builds parameter forms from plugin metadata, separates Importer/Analysis/Exporter lists, supports bulk add, and links videos through the unassigned workflow.
- Plugins:
  - `DeepLabCutHandlerPlugin` (handler): extract body parts, validate/ack tracking sources, load DataFrame via helper with optional likelihood thresholding.
  - `Mus1TrackingAnalysisPlugin` (analysis): kinematics, heatmap, zones/objects, NOR index, partial OF metrics; loads tracking data via handler/DataManager.
  - `SubjectImporterPlugin` (project-level import).
  - `GcpMoSeq2OrchestratorPlugin` marked deprecated (kept for reference only).

## Known gaps and quirks (truthful)
- Handler uses likelihood filtering but relies on `numpy`; this is imported in the handler, but ensure it remains imported to avoid runtime NameError in future edits.
- `PluginManager` still exposes legacy “supported_*” shims; keep canonical stage list from metadata and avoid introducing new legacy surfaces.
- `DataManager.get_experiment_data_path` is present; call sites should rely on it (or a central helper) rather than recomputing output paths.
- Windows/Linux scanners currently use the base scanner; OS-specific exclusions and removable drive handling are not implemented.
- `Mus1TrackingAnalysisPlugin` contains duplicated internal method names in places and mixes frame/series APIs; safe but should be tidied for clarity.

## Highest-priority next steps
1) Tighten correctness and remove misleading surfaces
- Remove/retire broken or misleading `PluginManager` aggregators. Keep: canonical stages via metadata and capability/format indices.
- Ensure all docs and UI refer to realistic capabilities; keep MoSeq2 as future server-backed plan, not current capability.

2) Strengthen IO and handler ergonomics
- Keep `DataManager.read_hdf` as the single path for HDF5 DLC reads; plumb structured warnings when non-standard column indexes are detected.
- Add `DataManager.get_experiment_data_path` usage wherever plugins persist outputs.

3) Scanner parity and progress UX
- Implement `WindowsVideoScanner` and `LinuxVideoScanner` with hidden/system file handling and removable drive traversal options.
- File dialog filters provided by plugins (e.g., `*.csv;*.h5`) through field metadata in the UI.

4) Analysis depth and tests
- Extend OF metrics (entries to center, thigmotaxis/perimeter time) with small synthetic tests.
- Add light-weight tests for NOR DI and zone-time on toy trajectories.

5) Code hygiene
- Remove duplicated private helpers in `Mus1TrackingAnalysisPlugin`; consolidate on the series-based implementations.

## Feature track: Targets/Workers/Shared-root scanning + predictable installs

Goal: Make MUS1 remember shared storage, known targets/workers, and scan across them (locally and over SSH/WSL) to produce a unique list of videos to add to a shared project. Keep installs predictable on macOS/Linux/WSL and minimize permission friction.

Principles
- Prefer a single shared root that is accessible to lab machines; register only files under this root. Stage external files into it first.
- Deduplicate on content-hash before registering; idempotent re-runs do nothing.
- Avoid new legacy surfaces: use typed fields in `ProjectState`.

Incremental plan (each step independently shippable)
1) Data model (typed) [dev]
- Add to `ProjectState`: `shared_root: Optional[Path]`, `workers: List[WorkerEntry]`, `scan_targets: List[ScanTarget]`.
- Define `WorkerEntry` (name, ssh_alias, optional role, provider="ssh"|"wsl").
- Define `ScanTarget` (name, kind="local"|"ssh"|"wsl", roots: List[Path], ssh_alias optional).
- Migration note: deprecate `settings["workers"]` usages and switch CLI to typed fields in a later step.

2) CLI surfaces (typed) [dev]
- `mus1 project set-shared-root PATH`.
- `mus1 workers list|add|remove|test` backed by `ProjectState.workers` (fix current list/remove bugs).
- `mus1 targets list|add|remove` backed by `ProjectState.scan_targets`.
- `mus1 project scan-from-targets PROJECT [--targets ...]` → scan all/selected targets, dedup, register unassigned; filter to `shared_root`.

3) Remote scanning service [dev]
- Implement `core/remote_scanner.py` that:
  - Local: uses `DataManager.discover_video_files`.
  - SSH: runs remote `mus1 scan videos` via `ssh alias ...` and streams JSONL.
  - WSL: runs `wsl.exe -e mus1 scan videos` when invoked on Windows or via SSH to a Windows host with WSL.
  - Merges and dedups via `DataManager.deduplicate_video_list`; filters to `shared_root`.
  - Preview mode with `--dry-run` and JSONL emission (`--emit-in-shared`, `--emit-off-shared`) for safe review prior to registering or staging.

4) GUI surfaces [dev]
- Project Settings: set `shared_root`.
- Workers tab: CRUD over `workers`.
- Targets tab: CRUD over `scan_targets`.
- Scan dialog: select targets, show per-target progress, summary (total/unique/outside-shared), actions: "Add to project" and "Stage to shared" (staging implemented in step 6).

5) Access and permissions (defaults) [ops]
- Document a shared directory policy: group-writable path owned by a lab group, with user umask honoring group write.
- Default to permissive local-network access: rely on OS user/group permissions; no MUS1 auth layer.
- Ensure project saves use advisory lock only (already in code) and write atomically.

6) Staging tool [dev]
- `mus1 project stage-to-shared <jsonl> --dest <subdir>`: copy/rsync into `shared_root`, verify hash, then register.

7) Job execution (initial) [dev]
- Define minimal `JobProvider` (provider: ssh). Execute analysis where data lives; write logs under project path.
- Add `mus1 workers run --name <worker> -- command...` (optional helper) to test remote execution.

8) Installation and environment [ops]
- macOS/Linux: recommend isolated user installs (pipx or uv tool); ensure `typer[all]`, `rich`, `tqdm` present (already in `pyproject.toml`).
- Windows: standardize on WSL2; install MUS1 inside WSL. Access Windows drives via `/mnt/*`.
- SSH consistency: keep aliases in `~/.ssh/config` (e.g., `copperlab-server`, `lab-windows`); use key-based auth; test via `mus1 workers add --test`.
- Shared root mount guidance: ensure mounts are stable on boot with correct ownership and group-writable permissions.

9) Git workflow for dev branch [ops]
- Use feature branches off `dev` (e.g., `feat/targets-scanning-step1`). Submit PRs into `dev`. Keep linear history (rebase preferred).
- Automated checks: lint, type check, and a fast smoke test on PR.
- Avoid inline versions in code/docs; keep single source in `pyproject.toml`.

Acceptance criteria for the feature track
- From a fresh project, user sets a `shared_root`, defines one or more targets, runs a scan across them, sees unique list, and adds unassigned videos to the project.
- Re-running scans is idempotent; only new unique items are added.
- Windows targets work reliably via WSL2.
- Installs on macOS/Linux/WSL are predictable; basic SSH tests pass from MUS1.

Follow-up documentation tasks (post immediate work)
- Cross-OS install and verification guide (WSL2, macOS, Linux):
  - How to install MUS1 (pipx/uv), ensure `mus1` is on PATH, verify with `mus1 --version` and `mus1 scan videos --help`.
  - SSH setup: key generation, `~/.ssh/config` examples (`copperlab-server`, `lab-windows`), connectivity checks.
  - Shared projects first: mounting guidance, permissions/umask, write tests, and `mus1 setup shared`.
  - WSL2 specifics: enabling WSL, installing Ubuntu, installing MUS1 inside WSL, accessing `/mnt/*`, remote invocation via SSH + `wsl.exe`.
  - Verification checklist for a new lab machine (local scan, remote scan, add-videos to shared project).

Current status (dev branch)
- Typed data model added in `ProjectState`: `shared_root`, `workers`, `scan_targets` along with models `WorkerEntry` and `ScanTarget`.
- Remote scan aggregator implemented in `core/remote_scanner.py`.
- CLI additions (help texts updated):
  - `mus1 project set-shared-root`: set per-project shared storage root.
  - `mus1 project move-to-shared`: relocate a project under the shared root.
  - `mus1 targets list|add|remove`: manage scan targets (local/ssh/wsl).
  - `mus1 workers list|add|remove`: manage typed worker entries.
  - `mus1 project scan-from-targets`: scan configured targets, dedup, and register unassigned videos (filtered to `shared_root` if set).
  - `mus1 project stage-to-shared`: copy files into `shared_root/<subdir>`, verify hash, and register.
- GUI: Project view now supports setting `shared_root` and moving the project to shared.
  - New Scan & Ingest page for target selection, scanning, summary, add/stage actions.
  - Workers and Targets tabs for CRUD (aligned with CLI), styled via `mus1.qss`.
  - Minimal `JobProvider` (ssh) implemented with a `mus1 workers run` helper for remote command execution.

Next best steps (prioritized)
1) GUI scanning and staging UX
- Add a Scan dialog to select targets, show per-target progress, and present summary (total/unique/outside-shared) with “Add to project” and “Stage to shared”.
- Add a simple staging UI action that calls the staging pipeline with a chosen destination subdir.

2) Workers/targets management in GUI
- Add Workers and Targets tabs with CRUD mirroring the CLI commands.
- Autocomplete `ssh_alias` from `~/.ssh/config`.

3) Job execution groundwork
- Define `JobProvider` interface (initial provider: `ssh`).
- Optional CLI helper: `mus1 workers run --name <worker> -- command…` to validate remote execution path.

4) Scanner polish and parity
- Improve Linux/Windows scanners for removable drives and hidden/system folders where safe; add excludes for common noisy paths.
- Add extension filters and exclude presets in CLI/UI.

5) Tests and reliability
- Add unit tests for `stage_files_to_shared` (happy-path, overwrite, hash mismatch cleanup).
- Add synthetic tests for `scan-from-targets` dedup/filter behavior.

6) Docs: cross-OS install and verification (then code hardening)
- Draft INSTALL guide (WSL2/macOS/Linux), SSH setup, shared-root mounting/permissions, and a verification checklist.
- After docs, add small bootstrap helpers if needed (e.g., `mus1 setup wsl-check`).

7) Distribution hygiene
- Ensure `pyproject.toml` remains the single source of versions; keep CLI deps tidy.
- Consider a `pipx`/`uv` install snippet in README and a minimal smoke test script.

Risks/Notes
- Remote scans require MUS1 installed on remote PATH (or WSL environment); document clearly.
- Moving projects assumes the destination filesystem is writable and has space; staging verifies content-hash to prevent silent corruption.

## Medium-term (architectural enablement)
- Storage/compute providers (mount-first design): local/shared/server storage providers plus local/SSH worker providers; wire into CLI and GUI creation/listing. Persist provider info in project metadata. Advisory lock file and atomic writes on save.
- Project-level data aggregation script (external) to export features and labels for ML training; keep training/inference outside MUS1, but define a minimal “prediction plugin” interface for optional future inference.
- GUI: subject grid gains sort-key aware sorting; basic Analysis tab for capability selection and status.

## Long-term direction
- Robust multimodal workflows (video, MoSeq2 syllables, Rotarod, biochemical CSVs) via dedicated handler/analysis/viewer plugins.
- Optional remote orchestration plugin (SSH/Slurm) for MoSeq2 and heavy jobs; job status and minimal log tailing in CLI/GUI.
- Better distribution: portable builds and UV-based reproducible environments.

## Deprecations and realities
- GCP MoSeq2 orchestrator is deprecated. Treat as reference only; replacement is a server-backed orchestration plugin when provider abstractions land.
- No Keypoint-MoSeq analysis plugin exists today; it is a planned analysis plugin that will consume tracking data via the handler/DataManager path.

## Acceptance snapshots (what “done” means soon)
- CLI and GUI share a single ingestion path; scan→dedup→register unassigned works end-to-end across macOS; parity on Win/Linux scanners.
- Plugins load DLC data through `DataManager.call_handler_method` and return results stored in `ExperimentMetadata.analysis_results` keyed by capability.
- Docs (this file + Architecture) truthfully describe implemented behavior and list gaps explicitly so users aren’t misled.


