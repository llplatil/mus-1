# MUS1 schema: variants, exploratory runs, canonical selection

**Last updated:** 2026-05-04
**Status:** authoritative — all task panes / compute services / CLI / harness must conform

This document fixes the contract for how compute outputs (tracking
confidence, zone classifications, interaction metrics, …) live inside
per-experiment JSONs and cohort JSONs. It supersedes the ad-hoc shapes
that EZM Tracking QC (`computed_metrics.ezm_open_closed.variants.*` +
top-level legacy variant blocks) and NOR/NOF Interaction QC
(`computed_metrics.interaction.r{N}cm`) inherited from earlier
generations.

---

## 0. Arena profile + state (input layer)

Arena physical dimensions are **not** carried per-task as constants.
A task references a default :class:`ArenaProfile` by id (e.g. NOR →
`tamco_black_bucket`); the profile owns the geometry and a list of
named states. Per-experiment override + cohort canonical (Iter 10)
sit above this.

```json
"arena_markings": {
  "arena_profile": {
    "profile_id": "tamco_black_bucket",   ← override; omit to use task default
    "state_id":   "resanded"              ← optional state hint
  },
  "arena_boundary": { "ellipse": {...} }, ← per-experiment fit
  "object_left_xy":  [...],
  "object_right_xy": [...]
}
```

Resolution cascade — `mus1.compute.scaling.compute_px_to_mm`:

1. `arena_markings.arena_profile.profile_id` (per-experiment override)
2. `task_def.arena_profile_id` (task default)
3. (Iteration 10) cohort-canonical
4. Missing — return `(None, "missing_*")`. Pane surfaces a banner; no
   silent guess.

`profile_id` cascades; `state_id` is independent and may be set even
when the profile_id is the task default. Profiles + states are
catalogued in `mus1.arena_profiles.builtins`; labs can extend via
`mus1.arena_profiles.registry.ArenaProfileRegistry.load_from_yaml`.

---

## 1. Three layers of compute output

| Layer | What it is | Where it lives | Who writes it | Who reads it |
|---|---|---|---|---|
| **Tracking confidence** | DLC-only baseline stats per bodypart + overall + flags. Idempotent function of the DLC CSV. Task-agnostic. | `extraction.tracking_confidence` | `mus1.compute.tracking_confidence` (via CLI, batch, or pane) | Every Tracking QC pane (top-of-panel summary), auto-flag aggregation, downstream "is this experiment usable?" filters |
| **Batch runs** | Cohort-canonical-candidate runs of a task-specific calculation. Run via CLI / Job Manager / Slurm. May be tagged as canonical for one or more cohorts. | `computed_metrics.{task}.batch_runs[]` | CLI (`mus1 compute …`), Slurm batch wrappers, FastAPI `/api/compute` | Stats scripts, dashboards, comparison views |
| **Exploratory runs** | In-pane experimentation by a human reviewer. Append-only audit trail attached to the QC review block. Never read by stats / publication code. | `computed_metrics.{task}.qc_review.exploratory_runs[]` | The QC pane's "Compute" button, on Save only | The QC pane itself (current vs. saved comparison dropdown) |

The three layers serve three different audiences (machines, downstream
analyses, humans-reviewing-quality) and must not bleed into each other.

---

## 2. Per-experiment JSON shape

```json
{
  "experiment_id": "EZM_159_2023-12-20",
  "extraction": {
    "tracking_file_path": "...",                ← legacy schema
    "dlc_runs": [...],                          ← new schema (validation_2026)
    "tracking_confidence": {
      "computed_at": "2026-05-04T12:34:56Z",
      "module_version": "1.0",
      "pcutoff": 0.6,
      "per_bodypart": {
        "head": {
          "mean_likelihood": 0.94,
          "median_likelihood": 0.96,
          "frac_above_pcutoff": 0.97,
          "longest_dropout_run_frames": 12
        },
        "nose": { ... }, "neck_base": { ... }, ...
      },
      "overall": {
        "n_frames": 36067,
        "median_frac_above_pcutoff": 0.95,
        "min_bodypart_frac_above_pcutoff": 0.82,
        "longest_any_dropout_run_frames": 18
      },
      "flags": []                              ← from TRACKING_QUALITY_FLAGS
    }
  },
  "computed_metrics": {
    "ezm_open_closed": {
      "batch_runs": [
        {
          "name": "consensus_06",
          "parameters": { "position_mode": "consensus", "lh": 0.6, ... },
          "metrics": { "open_fraction": 0.42, ... },
          "computed_at": "2026-04-01T10:00:00Z",
          "computed_by": "mus1.compute.ezm_zones",
          "module_version": "1.0",
          "job_id": "mus1_runs/ezm_pub_consensus_2026-04-01",
          "canonical_for_cohort": ["ezm_publication"]
        }
      ],
      "qc_review": {
        "status": "good",
        "notes": "tracking clean; checked frame 2100",
        "reviewed_at": "2026-05-04T13:00:00Z",
        "auto_flags": ["LOW_TRACKING"],
        "exploratory_runs": [
          {
            "name": "raw_head_06",
            "parameters": { "position_mode": "raw", "bodypart": "head", "lh": 0.6 },
            "metrics": { "open_fraction": 0.41, ... },
            "computed_at": "2026-05-04T12:50:00Z",
            "computed_by": "mus1_browser",
            "operator_note": "comparing to consensus baseline"
          }
        ]
      }
    },
    "nor_nof_interaction": {
      "batch_runs": [...],
      "qc_review": {
        "exploratory_runs": [
          {
            "name": "r3cm_lh06_fix_bb60",
            "parameters": {
              "radius_cm": 3.0,
              "likelihood_threshold": 0.6,
              "buffer_mode": "fixed",
              "bodypart_bound_px": 60
            },
            "metrics": { "left_time_s": 12.3, "d2": 0.18, ... },
            "computed_at": "...", "computed_by": "mus1_browser"
          }
        ]
      }
    }
  }
}
```

### Variant naming conventions
- **Batch runs** use task-conventional names operators recognize
  (`consensus_06`, `raw_head_06`, `r3cm`). Human-friendly is fine
  because batch run names come from CLI flags / cohort recipes.
- **Exploratory runs** use a deterministic slug derived from
  parameters: `{axis_short}_{value}_{axis_short}_{value}_…`. For
  NOR/NOF: `r3cm_lh06_fix_bb60` = radius 3cm, LH 0.6, fixed buffer,
  bodypart-bound 60px. Slugging is reversible: the `parameters` field
  is authoritative; the slug is for display + dedup only.

### Append-only invariants
- `batch_runs[]`: append-only. Re-running the same `(task, parameters)`
  produces a new entry with a fresh `computed_at`; the old one is
  preserved (or rotated when there are >N runs — see §6).
- `exploratory_runs[]`: append-only on **Save only**. Computing
  without saving leaves session state and never writes the JSON.
- Never edit the `parameters` or `metrics` of an existing entry.
  Mistakes get fixed by adding a new entry and (optionally) noting
  the prior one as superseded in `operator_note`.

---

## 3. Cohort JSON shape

```json
{
  "name": "ezm_publication",
  "members": [...],
  "summary": {
    "n_experiments": 171, "subjects": [...], "groups": {...},
    "canonical_metrics": {
      "ezm_open_closed": {
        "variant": "consensus_06",
        "computed_at": "2026-04-01T10:30:00Z",
        "groups": {
          "WT_F": {"open_fraction_mean": 0.42, "open_fraction_sd": 0.08, "n": 24},
          "HET_F": {...}, "KO_F": {...},
          "WT_M": {...}, "HET_M": {...}, "KO_M": {...}
        }
      },
      "nor_nof_interaction": { ... }
    }
  },
  "canonical_variants": {
    "ezm_open_closed": "consensus_06",
    "nor_nof_interaction": "r3cm_lh06_fix_bb60"
  }
}
```

### Canonical variant rules
- `canonical_variants` is **the cohort's promise**: every member's
  `computed_metrics.{task}.batch_runs[]` MUST contain an entry
  whose `name` matches the value here, and that entry's
  `canonical_for_cohort` MUST include this cohort's name.
- Mismatch (e.g. user changes the cohort's canonical pointer to a
  variant some members don't have) is a hard error in
  `cohorts.save_cohort()` — fail loud, do not silently accept.
- `summary.canonical_metrics` is **derived**: recomputed on every
  `save_cohort()` call from the per-experiment values. Never hand-edit.
- One canonical per `task` per cohort. If you need different variants
  for different manuscript sections of the same cohort, make those
  separate cohorts (clone-with-filter — Iteration 4).

---

## 4. The QC pane contract (cross-reference)

This shape composes with the QC pane contract codified in
ROADMAP.md / ARCHITECTURE_CURRENT.md §1.2:

- A QC pane filters by **input prerequisites only**. None of the
  three layers above are *inputs* — they are outputs. Their absence
  must never hide an experiment.
- Tracking confidence is the most common reason an experiment is
  un-QC-able-yet — surface it prominently and offer a one-click
  compute (which writes to `extraction.tracking_confidence`).
- Exploratory runs let an operator *decide* the QC review status,
  but they do not commit a canonical analysis decision. That happens
  via Job Manager batch jobs writing `batch_runs[]`.

---

## 5. Rationale (why three layers, not one)

We considered collapsing to a single `computed_metrics.{task}.runs[]`
list with a `kind` discriminator (`batch | exploratory | confidence`).
Rejected because:

- **Audience separation**. Stats scripts must never accidentally
  ingest exploratory or confidence runs. A type tag is easy to forget;
  a structural separation is enforceable.
- **Layering by stability**. Tracking confidence is idempotent
  (re-run = same answer). Batch runs are versioned, slow, expensive.
  Exploratory runs are operator-attached and append-only. The three
  have different write/read/cleanup policies — fighting them into one
  collection costs more than the path duplication.
- **Extension without break**. Adding a new compute layer (e.g.,
  segment-level features for behavioral fingerprinting) becomes a new
  top-level key, not a new tag in a shared list — existing readers
  ignore it cleanly.

---

## 6. Retention / cleanup

- `extraction.tracking_confidence` — **single block, overwritten** on
  re-compute. (Idempotent; no audit value in keeping prior versions.)
- `batch_runs[]` — keep all runs that are tagged
  `canonical_for_cohort` for any cohort. Untagged runs older than 90
  days from the most recent canonical run for the same `name` may be
  pruned by `mus1 compute prune --task=…` (manual, opt-in).
- `exploratory_runs[]` — never auto-pruned. Operator-attached audit
  trail. If a list grows beyond 50 entries, the QC pane shows only
  the most recent 20 with a "show all" expander.

---

## 7. Migration policy

- **EZM existing data (171 publication JSONs + the 12 validation):**
  not migrated. The legacy `computed_metrics.ezm_open_closed.{name}`
  blocks AND `computed_metrics.ezm_open_closed.variants.{name}.metrics`
  blocks are read by an adapter in `ezm_qc_shared.load_legacy_variants()`
  that synthesizes the new shape on-the-fly. New writes go to
  `batch_runs[]` / `qc_review.exploratory_runs[]`.
- **NOR/NOF existing data (339 publication JSONs):**
  the historical `computed_metrics.interaction.r{N}cm.{...}` shape is
  legacy. Adapter reads, new writes go to the new shape.
- **NOR/NOF `interaction_qc` (top-level):** the partial review block
  shipped 2026-05-03 (`{notes, reviewed_at}`) becomes
  `computed_metrics.nor_nof_interaction.qc_review.{status, notes,
  reviewed_at}` in Iteration 5.5d. One-time read-and-rewrite migration
  on first save.

The principle: never silently rewrite finalized publication data.
Adapters in the read path bridge the schemas; new writes use the new
shape.
