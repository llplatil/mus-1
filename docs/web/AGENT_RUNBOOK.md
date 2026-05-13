# MUS1 Agent Runbook

This document is for autonomous agents (Claude Code, GitHub Copilot Workspace,
or a human collaborator with shell access) who need to add new experiments
to a mus1 project and manage cohort membership without touching the UI.

The same affordances power the Streamlit UI, the CLI, and any agent driver,
so every operation has one canonical command. There is no separate "MCP
server" — agent integration is pure CLI.

---

## 1. Mental model

A mus1 project is a directory (typically `…/data/`) with this layout:

```
data/
├── mus1.toml                # optional — overrides defaults below
├── cohorts/                 # cohort manifests, JSON-per-cohort
│   ├── ezm_publication.json
│   └── validation_2026.json
├── experiment_data/         # primary data root (publication cohorts)
│   ├── EZM/{EXP_ID}/{EXP_ID}.json + recording/{video}
│   ├── NOR/...
│   ├── NOF/...
│   ├── OF/...
│   └── RR/...
├── validation_data/         # additional data root (validation cohorts)
│   └── (same per-task layout)
└── pilot_data/              # pilot / supplementary cohorts
    └── (same per-task layout)
```

**Data roots** are the directories the app scans for experiments. The
defaults are:

  - `experiment_data/` — publication-grade experiments
  - `validation_data/` — held-out validation experiments
  - `pilot_data/`      — pilot / supplementary cohorts

This list is **config-driven** via `mus1.toml` at the project path. To
add or reorder roots, write the override:

```toml
# data/mus1.toml
[paths]
data_roots = ["experiment_data", "validation_data", "pilot_data", "external_lab_data"]
```

Resolution order (override → fallback):

  1. `[paths] data_roots` in `<project_path>/mus1.toml`
  2. The hard-coded defaults above (when the file is absent or the key
     unset)

For most workflows, adding a new cohort manifest in `data/cohorts/` is
the right answer rather than a new root. New roots are appropriate when
you need a structurally separate task-folder tree (different naming,
different validator constraints, different ownership).

Every experiment lives in `{ROOT}/{TASK}/{EXP_ID}/` with a single
`{EXP_ID}.json` file inside. `EXP_ID` follows `{TASK}_{SUBJECT}_{DATE}`
or `{TASK}_VAL_{SUBJECT}_{DATE}` for validation experiments.

Cohort manifests in `cohorts/*.json` carry a `members[]` list of
`{experiment_id, added_at, notes}` objects. Members are tracked by ID — the
app resolves each ID against the configured data roots when it needs the
JSON contents.

---

## 2. Print the configured data roots

Always start by confirming what mus1 will scan, so you don't write JSONs
into a directory the app ignores. The output now also prints the
**source** of the configured list (`config` if read from `mus1.toml`,
`default` if using the built-in defaults).

```bash
mus1 experiment data-roots -p /path/to/data
```

If a configured root is missing from the printed list, create it on
disk — it will be picked up automatically on next scan (no registration
step). To add a non-default root, edit `<project_path>/mus1.toml` and
re-run the command — no code change required.

---

## 3. Add a new experiment

`mus1` does not "ingest" experiments — it discovers them. To add one:

1. Create the folder: `{ROOT}/{TASK}/{EXP_ID}/`
2. Move the video into `{ROOT}/{TASK}/{EXP_ID}/recording/{video}`
3. Write `{EXP_ID}.json` in the experiment folder with at minimum:

   ```json
   {
     "experiment_id": "EZM_VAL_1017_2026-04-08",
     "experiment_type": "EZM",
     "video": {
       "filename": "2026-04-08_15-51-03_1017EZM.mp4",
       "path": "/abs/path/to/video.mp4",
       "duration_seconds": 305.47,
       "frame_rate": 60,
       "resolution": [1080, 1080]
     },
     "metadata": {
       "experiment_type": "EZM",
       "date_recorded": "2026-04-08",
       "subject_id": "1017",
       "sex": "F",
       "genotype": "KO",
       "treatment": "CONTROL",
       "birthdate": "2026-01-08",
       "experiment_level": {
         "timepoint": 1,
         "cohort": "validation_2026",
         "notes": "bucket_subletter=C"
       },
       "age_in_days": 90
     },
     "extraction": {},
     "arena_markings": {
       "arena_profile": {
         "profile_id": "tamco_black_bucket",
         "state_id":   "resanded"
       }
     },
     "artifacts": []
   }
   ```

   The `experiment_level.bucket` field used to carry two unrelated
   meanings (Brio station id A/B/C/D, *or* bucket condition NEW/OLD/
   UNK). It was retired by the 2026-05-07 migration: A/B/C/D values
   now live in `experiment_level.notes` as `bucket_subletter=<X>`,
   and NEW/OLD/UNK values were promoted into
   `arena_markings.arena_profile.state_id` (the registered tamco
   states are `new`, `old`, `unk`, `resanded`).

4. Verify discovery picks it up:

   ```bash
   mus1 experiment list -p /path/to/data --task EZM | grep EZM_VAL_1017
   ```

There is no DB write step — discovery is on-demand from the JSONs on disk.
If a Streamlit pane caches the previous scan, click *Refresh* in its sidebar
or wait for the 120 s TTL to expire.

### Arena profile + state (per-experiment override)

When an experiment is recorded in a non-default arena (or in a known
state of the default arena, e.g. resanded vs. original surface), record
that under `arena_markings`:

```json
"arena_markings": {
  "arena_profile": {
    "profile_id": "tamco_black_bucket",
    "state_id":   "resanded"
  }
}
```

Profile ids are sourced from the arena profile registry — built-ins are
`tamco_black_bucket`, `home_depot_5gal_orange`, `ezm_460mm`. Add lab-specific
profiles by writing `<project_path>/arena_profiles.yaml` (or
`~/.config/mus1/arena_profiles.yaml` for user-level entries). State ids are
profile-specific; use `""` (or omit) for profiles without states.

This per-experiment block takes precedence over the cohort-level default
(see §4) and over the task default at compute time. See
`mus1.compute.scaling.compute_px_to_mm` for the resolution cascade.

For batch ingest, write a small Python intake script that ffprobes each
video and emits one JSON per experiment. See
`scripts/intake_validation_batch2.py` in this repo for a canonical example —
it handles ffprobe, age-in-days computation, NOR object metadata, and bulk
file moves out of `_transfer_staging/`.

---

## 4. Manage cohorts

```bash
# List cohorts in this project.
mus1 cohort list -p /path/to/data

# Show one cohort's summary + members.
mus1 cohort show validation_2026 -p /path/to/data --members

# Create a new empty cohort (writes data/cohorts/{name}.json).
mus1 cohort create my_new_cohort -p /path/to/data \
    --description "..." --task EZM --task NOR

# Add / remove a single experiment (idempotent).
mus1 cohort add-member validation_2026 EZM_VAL_1017_2026-04-08 -p /path/to/data
mus1 cohort remove-member validation_2026 EZM_VAL_1017_2026-04-08 -p /path/to/data

# Bulk-add by filter. Always preview with --dry-run first.
mus1 cohort add-where validation_2026 \
    --task EZM --root validation_data --unassigned --dry-run \
    -p /path/to/data

# Manage the cohort's NOR/NOF object vocabulary (e.g. fish/atom/dino/tube).
# This list seeds the marking + QC selectors; per-experiment values still win.
mus1 cohort set-objects   validation_2026 fish atom dino tube  -p /path/to/data
mus1 cohort add-object    validation_2026 sponge               -p /path/to/data
mus1 cohort remove-object validation_2026 sponge               -p /path/to/data
```

Every write triggers `compute_cohort_summary()`, so the cohort JSON's
`summary` block (subject counts, group breakdown, warnings) stays in sync.

**Canonical arena (cohort default)**: a cohort may carry a
cohort-level arena profile + state at `cohort.canonical_arena`:

```json
"canonical_arena": {
  "profile_id": "tamco_black_bucket",
  "state_id":   "resanded"
}
```

This is a lightweight cohort-level default — it does NOT yet override
per-experiment `arena_markings.arena_profile` at compute time
(planned for Iteration 10). Use the Cohort Management pane's *Canonical
arena (cohort default)* row to set or change it via the UI; the same
field is accepted by `create_cohort(canonical_arena={...})` and the
helpers `cohort_canonical_arena()` / `set_cohort_canonical_arena()` in
`mus1.web.cohorts`.

**Object vocabulary resolution** (NOR/NOF only): when an experiment is
displayed in the marking or QC pane, the dropdown options come from the
*union* of `objects` lists across every cohort the experiment is a
member of (preserving order). If no cohort declares any objects, the
fallback is the global `CANONICAL_OBJECTS` list in
`web/views/nor_nof_object_qc.py`. Per-experiment values stored in
`metadata.experiment_level.object_left/right` always seed the selector
default and are kept available even if not in the cohort vocabulary
(they appear at the end of the dropdown so existing marks aren't
forced to "(other)").

---

## 5. Marking workflow (filling arena_markings)

Arena marking, object marking, and zone QC happen in the Streamlit UI.
There is no headless CLI for clicking points. The UI panes auto-discover
experiments needing marking by scanning every configured data root for
JSONs without the relevant `arena_markings.*` block.

To make a freshly-added validation experiment appear in the marking pane:

1. Create its JSON (see §3) — make sure `arena_markings` is `{}` or absent.
2. Open the relevant pane (EZM Wedge Marking, NOR/NOF Object Marking, …).
3. The pane will list it in the "needs markings" filter once the on-disk
   scan picks it up (refresh sidebar or wait for cache TTL).

After marking, the pane writes `arena_markings.*` back to the same JSON.

---

## 6. Common agent recipes

**Recipe A — "I just intook a batch of validation videos. Make them
visible to the marking panes."**

```bash
mus1 experiment data-roots -p data         # confirm validation_data is scanned
mus1 experiment list -p data --root validation_data --cohort none
# (no further action needed — UI sees them on next scan)
```

**Recipe B — "Add the 9 validation_data EZM experiments to validation_2026."**

```bash
mus1 cohort add-where validation_2026 \
    --task EZM --root validation_data --dry-run -p data
# review the list, then drop --dry-run to commit
```

**Recipe C — "Spin up a new cohort from a filter and ship."**

```bash
mus1 cohort create batch3_2026 \
    --description "Validation batch 3, recorded 2026-XX-XX." \
    --task OF --task NOR --task NOF --task EZM \
    -p data
mus1 cohort add-where batch3_2026 --root validation_data --cohort batch_3 -p data
```

**Recipe D — "Audit which experiments aren't in any cohort."**

```bash
mus1 experiment list -p data --cohort none
```

**Recipe E — "I'm not sure where my project is."** Run from the parent
directory; the CLI auto-detects `./data/`.

---

## 7. Conventions for agents writing intake scripts

- Use `ffprobe` from `~/miniconda3/envs/moseq2-app/bin/` so `creation_time`
  parses on Azure Kinect MKVs.
- Write the JSON before moving the video, then `mv` the video into
  `recording/`. This keeps the on-disk state consistent if interrupted.
- `experiment_id` MUST equal the folder name. The validator
  `data/experiment_data/validate_experiment_data.py` enforces this.
- `metadata.experiment_level.cohort` is the recommended place to declare
  which cohort an experiment belongs to. `mus1 cohort add-where --cohort X`
  uses this field as the filter source.
- Move videos out of `_transfer_staging/` once intake is complete; never
  delete files (`rm`) without explicit user approval — archive to
  `_workspace_noisy_archive/` instead.

---

## 8. What this runbook does NOT cover

- Running DLC / MoSeq2 / KPMS pipelines against new experiments. See
  `reports_workspace/validation_experiment_plan.md` for the analytical
  pipeline.
- Editing experiment JSONs (provenance for fixes, QC flags). The web QC
  panes write those fields; for scripted edits, prefer a dedicated provenance
  block per the project conventions in `CLAUDE.md`.
- Database synchronization. Discovery is JSON-first; the DB is an index,
  not the source of truth. Run `mus1 import workspace-db-sync` if you need
  the SQLite mirror updated for a new experiment.

When in doubt, run `mus1 experiment data-roots -p <project>` and read the
output. If the path you expect isn't listed, the app cannot see your data.
