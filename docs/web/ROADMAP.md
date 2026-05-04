# MUS1 Web App Roadmap

Forward-looking work, ordered by impact. Anything already shipped lives
in [`ARCHITECTURE_CURRENT.md`](ARCHITECTURE_CURRENT.md), not here.

**Last updated:** 2026-05-03

## Project context

mus1 is being rewritten from Streamlit to FastAPI + React for
open-source release targeting rodent behavior labs. The core value —
annotation workflows, experiment JSON as source of truth, calculation
variant comparison, and QC with provenance — is preserved. Phases 1–3
of the rewrite (TaskRegistry, service layer, FastAPI backend) are
complete; Phase 4 (React frontend) is the major outstanding milestone.
Streamlit improvements in this roadmap are scoped to **changes that
also benefit the React port** — anything Streamlit-shaped that
wouldn't survive the port is rejected.

Full rewrite plan: `~/.claude/plans/ancient-jumping-ritchie.md`
Manuscript skeleton: `reports_workspace/manuscript_unified.tex`
Per-task methods+results: `reports_workspace/{ezm,nof_nor,of,rr}/*_methods_results.md`

---

## Iteration 2 — Marking dashboard landing pane (NEXT)

Replace the current "Subjects/Experiments" landing with a dashboard
that shows, at a glance, what work is owed across every cohort:

```
EZM       │ N experiments need wedge points  · click → Wedge Marking
EZM       │ N experiments need zone QC       · click → Zones QC
EZM       │ N experiments need tracking QC   · click → Tracking QC
NOR/NOF   │ N experiments need object marks  · click → Object Marking
NOR/NOF   │ N experiments need object QC     · click → Object QC
NOR/NOF   │ N experiments need interaction QC · click → Interaction QC
NOR/NOF   │ N experiments unpaired           · click → Auto-link flow
…
```

Each row is one filter applied to the canonical discovery scan. The
target pane opens with the filter pre-applied (Streamlit query params).

**Implementation**
- New `views/marking_dashboard.py`, ~150 LOC.
- Reuses `discovery.discover_experiments()` + `render_filters` predicates.
- Each row's link sets `?pane=...&filter=...` so the target pane lands
  on the pre-filtered subset.
- Counts respect the active scope (cohort) from `SCOPE_KEY`.

---

## Iteration 3 — Surface QC gaps, not just marking gaps

Today the marking dashboard counts "missing `arena_markings.X`." Add
the mirror counts for QC: "marked but not yet QC-approved/rejected."

**Surfaces**
- "EZM experiments with wedge points but no `arena_markings.ezm_wedge_points.qc.status`"
- "EZM experiments with computed metrics but no `qc_review.status`"
- "NOR/NOF experiments with `interaction` metrics but no `interaction_qc.reviewed_at`"
- "NOR/NOF unpaired (where pair would be expected from cohort task_type_counts)"

**Discipline**: every row corresponds to a single predicate against
the canonical loader output — no bespoke counters. New rows are added
by writing a predicate function, not new SQL.

---

## Iteration 4 — Cohort templates / clone-with-filter

Half the cohort JSONs in `data/cohorts/` are minor variants of one
another (publication cohorts per task, validation cohort, pilots).
Add a "Clone cohort with filter" UI plus `mus1 cohort clone <src>
<dst> --add-where ...` so common operations (e.g. "make a QC-only
subset of the publication cohort") don't require hand-editing JSON.

---

## Iteration 5 — Phase 4 React rewrite

The work above intentionally minimises "Streamlit-shaped" features so
the React port can lift each pane 1:1 against the FastAPI service
layer (`server/services/`) without inheriting Streamlit-specific
affordances (caching contracts, session_state hacks). Vite + React
Router + TanStack Query + Tailwind; Fabric.js or Konva.js for the
annotation canvas (replaces `streamlit-drawable-canvas`). Static
build bundled in the pip package — no Node.js on HPC at runtime.

---

## Iteration 5.4 — Pre-Phase-B cleanup (must land before 5.5)

The Phase A foundations work (2026-05-04) revealed duplication that
will compound if Phase B (Iteration 5.5) lands on top of it. These
five small refactors are scheduled FIRST so 5.5 gets a clean substrate
— each is mechanical, has zero behavior change, and is independently
testable. They map to items in the original cleanup catalog (now moved
to "Cleanup follow-ups" below for post-5.5 work).

### 5.4a — Lift mount-alias normalization to `mus1.paths`

Today the `/center1/` ↔ `/import/c1/` swap is reimplemented in 5+
places (`web/paths.py`, `web/ezm_qc_shared.py:resolve_path`,
`web/views/nor_nof_interaction_qc.py`, `core/importers/arena_zones.py`,
the new `core/compute_cli.py`). Phase B's compute button + frame nav
will touch this code path again — fixing it once now prevents copy 6.

**Plan**: new `mus1.paths.resolve_with_mount_aliases(p) -> Optional[Path]`
in a new top-level `mus1.paths` module (the package level, not
`web/paths.py`). All five existing implementations become one-line
wrappers or are deleted outright. Acceptance: every `/center1/` /
`/import/c1/` literal is gone outside the new helper + tests.

### 5.4b — Move `resolve_dlc_csv_path` from `web.discovery` to `compute.tracking`

It's a pure function over an `extraction` dict — no Streamlit, no
filesystem, no UI coupling. CLI + FastAPI both already import it from
`web/`, which is backwards. Phase B will call it from one more place
(the pane's compute path); now is the time.

**Plan**: physical move to `mus1.compute.tracking`, leave a deprecation
alias in `web.discovery` for one release. Update the four current
import sites (`ezm_qc_shared`, `nor_nof_interaction_qc`,
`compute_cli`, `experiment_service`).

### 5.4c — Migrate `nor_nof_interaction_qc` + `ezm_tracking_qc` to `try_read_dlc_csv`

Phase B adds a Compute button to NOR/NOF Tracking QC. Today the file
has its own inline `pd.read_csv(p, header=[0,1,2], index_col=0)` plus
`droplevel(0)` plus its own bodypart-bound nose-correction logic. The
canonical reader at `compute.tracking.try_read_dlc_csv` already exists
(8 callers reinvent it; this iteration migrates the two we're about
to touch). The other six are deferred (post-5.5 cleanup).

**Plan**: `_load_nose_track_corrected` reads via `try_read_dlc_csv`;
`ezm_tracking_qc`'s in-pane Compute path does the same. Both retain
their post-read filtering logic — the migration is the read step
only. Acceptance: no `pd.read_csv(.. header=[0,1,2] ..)` literal in
either pane file.

### 5.4d — Extract `TRACKING_QUALITY_FLAGS` to `compute.tracking_flags` + flag merger

Two related reorganizations done together because Phase B needs both:

1. The Phase A3 vocabulary lives in `web/qc_flags_shared.py` today,
   which is misnamed (it's universal, not NOR/NOF-only). Move
   `TRACKING_QUALITY_FLAGS` to `mus1.compute.tracking_flags`. Re-export
   from `qc_flags_shared` for one release for backwards compat.
2. Add `mus1.compute.tracking_flags.merge_into_qc_flags(qf, tc) -> qf`
   — the single helper that copies `tracking_confidence.flags` into
   `qc_flags.auto_flags`. Phase B's Compute button calls this; the
   CLI `--write` path calls it too. **One merger, two call sites,
   guaranteed not to drift.** This is "Better approach D" from the
   original cleanup catalog, promoted to prep because it's small and
   actively prevents a Phase B bug.

**Plan**: new `mus1.compute.tracking_flags` (~50 LOC + tests). Wire
the CLI `--write` path now (single line); Phase B wires the pane.

### 5.4e — Delete hardcoded `EXPERIMENT_DATA_ROOT` in `nor_nof_interaction_qc.py:55`

Trivial. Discovery already covers multi-root scanning; the hardcoded
absolute path is a dead fallback. Acceptance: line removed, no
referencing call sites broken.

### 5.4 acceptance gate

All five 5.4 items must pass before 5.5 starts:
- [ ] `pytest` — existing 19 tests still pass + at least 5 new tests
      across the 5 items (one happy path each, minimum)
- [ ] No literal `/center1/` or `/import/c1/` strings outside
      `mus1.paths` and its tests
- [ ] `grep -rn "tracking_file_path"` returns only doc strings + the
      resolver itself
- [ ] `grep -rn "header=\[0, 1, 2\]"` returns 6 instances down from 8
      (the remaining 6 are tracked under "Cleanup follow-ups")
- [ ] `mus1 compute tracking-confidence --write …` writes flags into
      both `extraction.tracking_confidence.flags` AND
      `qc_flags.auto_flags` (via the new merger)

LOC estimate: ~200 added (mostly tests), ~150 deleted (dedup), net
+50. No behavior change for users.

---

## Iteration 5.5 — NOR/NOF Tracking QC function parity (was: Interaction QC)

The pane formerly named **"NOR/NOF Interaction QC"** has been renamed
to **"NOR/NOF Tracking QC"** to mirror EZM Tracking QC, since both
panes serve the same lifecycle role (review DLC tracks against marked
arena/objects). The rename ships now (2026-05-03); this iteration is
the function-parity work that makes the renamed pane behave like its
EZM counterpart.

### Current state vs. EZM Tracking QC

| Capability | EZM Tracking QC | NOR/NOF Tracking QC (today) |
|---|---|---|
| Per-experiment frame navigation | ✓ slider + frame buttons | ✗ mid-frame only |
| Variant selector | ✓ 8 zone-classification variants | ✗ no variant concept yet |
| In-pane "Compute metrics" button | ✓ | ✗ (CLI/batch only) |
| Auto-flag display | ✓ | partial (tracking_qc only) |
| Save QC review block | ✓ `qc_review.{status,notes,reviewed_at}` | partial (`interaction_qc.{notes,reviewed_at}`, no status) |
| Graceful degradation when metrics absent | ✓ | ✓ (shipped 2026-05-03) |

### Plan

**5.5a — Frame navigation.** Add the same frame slider + ◀ 1s / ◀ /
▶ / 1s ▶ cluster used by EZM Tracking QC, scoped per-experiment via
`pkey(PANE, "frame_{exp_id}")`. The overlay re-renders at the chosen
frame; trajectory polyline still draws over the full session.

**5.5b — Radius variants treated like EZM variants.** Today the radius
selector (2 / 3 / 4 cm) is a Display setting and selects which metric
block to render. Promote it to a "Variant" selector that also tags the
QC write block, so a session can be reviewed-with-r3cm-OK and
re-reviewed-with-r4cm separately if needed (matches the EZM variant
model where each (position_mode, bodypart, LH) tuple is a variant).
Variant naming convention: `r{2,3,4}cm`.

**5.5c — In-pane compute button.** Wire
`mus1.compute.nor_nof_interaction.compute_interaction_metrics` to a
"Compute interaction metrics" button. The wrapper that produces the
`r{2,3,4}cm` blocks lives today in the batch script
(`reports_workspace/.../nor_nof_compute_metrics.py` or similar) — lift
it into `mus1.server.services.compute_service.compute_nor_nof_interaction_for_experiment(json_path)`
and call from both the pane and the existing CLI batch. The button
writes session-state metrics (unsaved) until the user clicks Save,
matching the EZM flow.

**5.5d — Standardize the QC write block.** Replace the partial
`interaction_qc.{notes,reviewed_at}` write with the full EZM-style
`qc_review.{status,notes,reviewed_at,auto_flags}` block at
`computed_metrics.nor_nof.qc_review`. Status options: `(not reviewed)`,
`good`, `poor_tracking`, `exclude`, `needs_re_review` — same vocabulary
as EZM Tracking QC. Migrate any existing `interaction_qc` blocks to
the new path on first save (preserve original keys; one-time
migration captured in provenance).

**5.5e — Visual identity.** Use the canonical EZM/wedge palette
(Iteration 6a) for any zone-tinted overlays. Trajectory keeps the
existing temporal gradient (cyan → green → yellow) since it's
session-time-coloring, not zone classification — same convention as
EZM Tracking QC.

### Acceptance

- [ ] Pane name is `NOR/NOF Tracking QC` everywhere (sidebar, header,
      docs, view file). View filename rename is deferred to avoid
      breaking import statements; tracked separately under Loose ends.
- [ ] Frame navigation works (matches EZM Tracking QC affordances).
- [ ] Variant selector exposes r2/r3/r4cm with the EZM variant pattern.
- [ ] "Compute interaction metrics" button populates session-state
      metrics; Save & next persists them under
      `computed_metrics.nor_nof.r{N}cm.metrics`.
- [ ] QC review block matches EZM schema.

---

## Iteration 6 — Unify EZM ML into the arena-marking lifecycle

> *(Unpacked from the user's note on the prior roadmap line 318:*
> *"EZM ML: It should really be an arena marking inference qc pane and*
> *function as one. make the EZM inference colors the same as the wedge*
> *marking colors and the EZM arena detection qc rn looks good enough*
> *to actually use as an arena marking mode variant if the functionality*
> *is built out.")*

Today the EZM U-Net work is split across panes whose lifecycle
boundaries don't match what the user actually does:

| Pane | Today | Issue |
|---|---|---|
| EZM ML | Mixed: cohort overview, validation inference *preview*, training set mask preview, training submission, post-training QC | Tries to be three different things; "preview" is QC in disguise |
| EZM Wedge Marking | Manual 4-click marking only | Can't take a U-Net suggestion as a starting point |
| EZM Zones QC | Reviews wedge-circle-fit overlay only | Could review U-Net masks the same way |

Color drift compounds the confusion: wedge marking uses green points
(`#00ff00`), the trajectory overlay uses green/blue zone tints
(`(0,200,0)`/`(80,80,255)`), and the U-Net mask overlay uses
yellow-for-open + blue-for-closed (`(255,255,0)`/`(0,0,255)` from
`ezm_masks.blend_mask_overlay`). A reviewer comparing GT vs. prediction
sees green-vs-yellow for the same conceptual region.

### Plan (3 sub-iterations)

**6a — Color unification (small, blocks nothing).** Adopt the wedge
marking palette as the EZM canonical palette in `mus1.compute.overlay`:

```
OPEN    = (0, 200, 0)     # green   (matches wedge fill_color, zones QC)
CLOSED  = (80, 80, 255)   # blue    (matches zones QC)
WEDGE_PT= (0, 255, 0)     # bright green  (matches st_canvas stroke)
PREDICTED_OPEN   = (0, 200, 0,  α=0.45)   # solid green tint
PREDICTED_CLOSED = (80, 80, 255, α=0.45)  # solid blue tint
DELTA_TINT = (255, 80, 255)  # magenta — predicted ≠ GT
```

Update `ezm_masks.blend_mask_overlay()` to read those constants.
Yellow disappears from the EZM workflow. EZM Tracking QC's
"corrected frames" tint already uses magenta — keep it; magenta now
also marks "predicted-vs-GT disagreement" in the new pane (semantic:
"a frame the human should look at"). This is a 1-file change with no
downstream rewires.

**6b — New pane `EZM Arena Inference QC`.** Replace the EZM ML
"Validation Inference Preview" + "Training Set Mask Preview" sections
with a first-class QC pane that follows the QC pane contract:

- Inputs filter: `has_wedge_points` AND has-active-model.
- Layout matches EZM Zones QC: experiment list (filtered by scope), one
  experiment per render, mid-frame view, navigation, save+next.
- Overlay shows three layers, toggleable:
  1. GT mask from wedge points (green/blue, α=0.30)
  2. U-Net prediction (green/blue, α=0.45)
  3. Disagreement mask (magenta) — pixels where GT ≠ pred
- Per-frame metrics in the right column: IoU(open), IoU(closed),
  pixel-disagreement %.
- QC actions write `arena_markings.ezm_inference_qc.{status,notes,reviewed_at}`
  (status: `keep` / `re_train` / `disagree_visual_only`).
- Cohort/genotype filters carried through the standard `render_filters`.

**6c — "U-Net suggestion" as a wedge-marking input variant.** In
`EZM Wedge Marking`, add a `Suggestion source` selector:

| Option | Behavior |
|---|---|
| Manual (default) | Today's blank canvas, user clicks 4 points |
| U-Net auto-suggest | Run inference → derive 4 boundary points from the predicted open/closed border crossings → pre-populate the canvas. User accepts (Save) or edits (drag/replace) before saving. |

The auto-suggest path writes a richer provenance block:

```json
"arena_markings": {
  "ezm_wedge_points": {
    "points": [...],
    "provenance": {
      "method": "unet_suggested+human_accepted" | "unet_suggested+human_edited" | "manual",
      "model_path": "...",
      "model_sha": "...",
      "edits": [{"original_xy": [...], "final_xy": [...]}, ...]
    }
  }
}
```

This makes the U-Net a **marking-mode variant** without dropping the
4-point contract that downstream zone fitting depends on. The model
remains optional; users without the model just see "Manual".

### Demolition

After 6b ships, the existing `EZM ML` pane shrinks to the parts that
don't fit the QC contract: cohort overview, training submission, and
post-training run-status. Rename it `EZM Arena Inference Training`
(or merge into `Training Monitor`). The validation inference preview
moves to 6b; the training set mask preview is dropped (its only user
was developer debugging, which the harness covers).

### Acceptance

- [ ] No yellow anywhere in the EZM workflow.
- [ ] Validation cohort viewable end-to-end through the new pane with
      no DLC dependency (arena inference is upstream of tracking).
- [ ] Wedge marking pane offers the "U-Net auto-suggest" toggle when a
      model is registered, falls back gracefully when not.
- [ ] Provenance distinguishes manual / suggested-accepted /
      suggested-edited.
- [ ] EZM Wedge Marking + EZM Inference QC + EZM Zones QC share a
      visual identity (same colors, same overlay primitives in
      `mus1.compute.overlay`).

---

## Iteration 7 — Save-and-advance workflow

Today the QC panes use a "Save" button that writes the QC block and
re-renders the same experiment. Operators QC'ing 100+ experiments
in a row repeatedly Save → click Next → wait for re-render. The Save
and Next steps belong together.

### Plan

**7a — Single primary action "Save & next".** Replace the current
"Save…" button in every QC pane with a single primary action that:

1. Persists the QC block (existing logic).
2. Calls `invalidate_after_write()` so the count caches refresh.
3. Advances `idx` to the next experiment in the filtered list. If at
   the end, shows a "Review complete" toast and stays put.
4. Triggers `st.rerun()` once, not twice.

A secondary "Save & stay" button (de-emphasized) covers the "I want
to keep tweaking this one" case. Keyboard shortcut `Shift+Enter` for
"Save & next" once we add the keybinding helper (Iteration 8 below).

**7b — Skip-already-reviewed by default.** Add a sidebar toggle
"Show only unreviewed" (default ON for QC panes). When ON, "Save &
next" advances past the just-reviewed experiment by virtue of the
filter, not by walking past it manually. This is the natural QC
loop: open pane → review → save → review next → … → "Review complete."

**7c — Auto-save on intent, not on every keystroke.** The current
code keys widget state on `(pane, exp_id)` so partial inputs survive
re-renders, but the actual write only happens on click. Keep this —
auto-save would conflict with the "Save & stay" intent. Document
the explicit-save invariant in the QC pane contract.

**7d — Surface the queue position prominently.** Today the count is
`5 / 23 experiments` in a markdown caption. Promote it: a thin
progress bar at the top of the pane (`st.progress(idx / n)`) plus
the X / Y in the same row. After "Save & next" the bar fills
incrementally, giving a visceral sense of progress for long QC
sessions.

### Acceptance

- [ ] `Save & next` is the *only* primary button in every QC pane.
- [ ] Stays put at the end of the queue with a clear "Review complete" toast.
- [ ] "Show only unreviewed" toggle is sticky per pane, defaults ON
      for QC panes, OFF for marking panes (where you may want to revisit).
- [ ] Progress bar visible at top of every QC pane.
- [ ] Behavior is identical across all four QC panes (EZM Zones, EZM
      Tracking, NOR/NOF Object Association, NOR/NOF Interaction).

---

## Iteration 8 — Navigation reliability + redundancy elimination

The navigation cluster currently rendered as `[Prev] [Index ± input]
[Next] [n / N]` is **redundant and historically unreliable**:

```
col_prev, col_idx, col_next, col_count = st.columns([1, 2, 1, 2])
```

- The `st.number_input` already exposes ± spinner buttons that step by 1.
- `[Prev]` and `[Next]` step by 1.
- All three do the same thing.
- The Prev/Next buttons write `st.session_state["{pane}_idx"]` while
  `st.number_input` writes `st.session_state["{pane}_idx_input"]`
  (separate keys). Race conditions during `st.rerun()` cause the two
  to desync, producing the "I clicked Next and it jumped two
  experiments / went back / showed a stale frame" symptoms.
- When the active filter set narrows the list, `idx` may exceed the
  new `max_value`; the number input clamps silently while the canonical
  `_idx` key keeps the old value, so the next Prev click "jumps."

### Plan

**8a — Single source of truth for the navigation index.** Build
`web/navigation.py`:

```python
def render_nav(
    *, pane: str, n: int, label: str = "experiment",
) -> int:
    """Render the standard pane navigator and return the resolved idx.

    Single canonical session-state key: `pkey(pane, "nav_idx")`.
    Clamps to [0, n-1] on every render. Renders the buttons + a
    progress display; widgets share the same key, so there is no
    second-state drift.
    """
```

Layout:

```
[◀ prev]   [ Frame 5 of 23 ]      [next ▶]
══════════════════════════════════════════
[━━━━━━━━━━━━━━ progress ━━━━━━━━━━━━━━━━ ]
```

- Drop the `st.number_input` entirely. It was redundant with
  Prev/Next.
- Provide a "Jump to experiment_id…" `st.text_input` separately for
  the rare case where the user knows which experiment they want.
  This is a lookup, not a stepper, so it doesn't fight with Prev/Next.
- Keyboard: `←` / `→` arrow keys via `streamlit-shortcuts` (or
  equivalent) wired in 8c.

**8b — Filter-change resync.** When `n` shrinks, clamp the canonical
index *before* widgets render, and emit a single `st.toast(
"Filters changed — jumped to first match.")` if the previous idx was
out of bounds. No silent jumps.

**8c — Keybindings.** Add the shortcut layer once in `web/navigation.py`:
- `←` / `→` — prev / next
- `Shift+Enter` — Save & next (Iteration 7a)
- `j` / `k` — vim-style prev/next (off by default; toggle in
  user-level settings file at `~/.config/mus1/keybindings.toml`)

**8d — Migrate panes one at a time.** Order matches QC priority:
EZM Tracking QC → EZM Zones QC → NOR/NOF Interaction QC →
NOR/NOF Object Association → EZM Wedge Marking → NOR/NOF Object
Marking. Each migration is one file, ~15 LOC removed, ~5 added (the
old custom 4-column nav cluster swapped for a single
`render_nav(...)` call).

### Acceptance

- [ ] Exactly one canonical session_state key per pane for the
      navigation index.
- [ ] Prev/Next buttons survive a filter change with no jump or
      desync.
- [ ] No `st.number_input` step-by-one widgets in any pane (jump-to-id
      uses a different control).
- [ ] Keyboard shortcuts work in every QC pane.
- [ ] Progress visible at all times.

### Why this matters beyond ergonomics

Every QC session that has to be redone because "Prev jumped two
experiments" wastes operator time and corrupts the audit trail
(`reviewed_at` timestamps no longer reflect actual review order).
Reliability of navigation is a correctness property, not a polish item.

---

## Cleanup follow-ups (post-5.5; not blocking Phase B)

These items were catalogued during the Phase A sweep (2026-05-04) but
do *not* gate Iteration 5.5. The five items that DO block 5.5 were
promoted into Iteration 5.4 above. Everything below is genuine
follow-up work.

### Already shipped during Phase A (2026-05-04)
- `tracking_file_path` direct reads in FastAPI/services — `server/routers/compute.py` (×2) and `server/services/experiment_service.py` were using the legacy field directly. All three now use `resolve_dlc_csv_path`. (The helper itself moves to `compute.tracking` in 5.4b.)

### Deferred refactors (no Phase B dependency)

**1. Migrate the remaining 6 inline DLC reads to `try_read_dlc_csv`.**
After 5.4c, the panes Phase B touches are clean. Six callers remain:
- `compute/ezm_zones.py`, `compute/overlay.py`
- `web/ezm_compute_bridge.py`, `web/ezm_trajectory_overlay.py`
- `compute/tracking_confidence.py:_try_read_dlc_csv` (deliberate
  Phase-A decoupling; remove once `compute.tracking` is the single
  canonical reader)
- one more in `web/views/ezm_tracking_qc.py` if 5.4c only catches the
  primary read path
Migrate each with a small commit to the existing canonical reader.

**2. CLI default project-path resolution.**
`compute_cli` and `experiment_cli` share `_resolve_project_path` via
a private-name import (`from .experiment_cli import _resolve_project_path`).
Promote to `mus1.core.cli_helpers` (new tiny module). One change,
two import-site updates.

### Better-approach proposals (architectural, not just cleanup)

**A. `try_read_dlc_csv` should return a typed `DLCTracks` object.**
Today it returns a `pd.DataFrame` with a 2-level column MultiIndex,
and every consumer remembers to call `.droplevel(0)` first. The
shape encodes a precondition checked nowhere. Wrap into a
`DLCTracks` dataclass with explicit accessors
(`tracks.likelihood("nose") -> np.ndarray`,
`tracks.xy("head") -> tuple[np.ndarray, np.ndarray]`,
`tracks.bodyparts -> list[str]`). Type checking finds mistakes a
year sooner. Net: ~150 LOC across all callers, mostly mechanical.

**B. Full split of `qc_flags_shared`.**
5.4d extracts `TRACKING_QUALITY_FLAGS`. The remaining work:
- `mus1.tasks.{task}.flags` — task-specific vocabularies (currently
  `NOR_NOF_FLAG_VOCABULARY` plus EZM's auto-flags in
  `ezm_qc_shared`), owned by each TaskDefinition.
- `mus1.experiments.qc_block` — readers/writers for the `qc_flags`
  block in the experiment JSON (currently `read_qc_flags`,
  `set_status`, `set_notes`, `set_auto_flags`, history helpers).
Composes with the TaskRegistry from Phase 1 — task vocabularies
travel with the task definition rather than living in a shared web
module.

**C. Shared `mus1.experiments` facade for views + routers.**
Today, panes do their own discovery and their own JSON reads.
Phase 2 introduced `ExperimentService`; only the FastAPI side uses
it. Streamlit panes would benefit from a thin facade exposing the
read-side API both can share. Reduces "this loader is in the wrong
place" questions and lets the Phase 4 React port lift each pane's
data-access pattern unchanged.

---

## Iteration 9 — Performance: smart-fetch vs auto-fetch frames

The current frame-by-frame UX in EZM Tracking QC reads each requested
frame on demand (`cv2.VideoCapture` seek + read). For long sessions
(18k–36k frames) and slow filesystem mounts, the slider feels laggy
because every drag emits a new render that re-opens the video.
Operators on Chinook tolerate it; new users won't.

The user has asked for this to live behind a **preference toggle** so
the trade-off is explicit:

| Mode | Behavior | When to pick |
|---|---|---|
| `smart_fetch` (default) | On-demand seek+read with a small lookahead window | Daily QC, mount usually warm |
| `auto_fetch_all` | Pre-decode the full video into memory at experiment-load time | Long QC sessions on cold mounts; expensive but smooth |

### Plan

1. Extend `mus1.preferences` with a `compute.video_fetch` section:
   ```yaml
   compute:
     video_fetch:
       mode: smart_fetch  # | auto_fetch_all
       prefetch_window_frames: 60
       max_inmemory_seconds_per_session: 600
   ```
2. New module `mus1.compute.video_cache` providing two backend classes
   that share a `read_frame(idx)` interface; pane code does not need to
   know which backend is active.
3. EZM Tracking QC + NOR/NOF Tracking QC consume the preference at
   pane-load time and render through the same slider.
4. Auto-fetch backend gated by an explicit progress bar (so the
   operator sees the upfront cost) and a
   `max_inmemory_seconds_per_session` ceiling that triggers a fallback
   to smart-fetch with a toast.

This is a **preference-driven choice**, not a heuristic — agents can
populate it in `~/.config/mus1/preferences.yaml` from a chat about
"my mount is slow today, prefetch please" and the app picks it up
next render. Composes with Iteration 8's nav reliability work.

---

## Iteration 10 — Cohort-canonical arena boundary (pitch deferred)

> **User ask (2026-05-04, paraphrased)**: "Is Arena boundary fit wired
> to the cohort? If so, the cohort should be updatable by an agent in
> the CLI to use the known outer arena marking from either inferred
> arena (once implemented fully) or the geometric fit based on the
> marked experiments. Note in docs with a plan to pitch to me later."

### Current state (so the pitch starts on solid ground)

- Per-experiment arena boundary lives in `arena_markings.arena_boundary`
  (NOR/NOF) or is derived from `arena_markings.ezm_wedge_points`
  (EZM). Each experiment has its *own* fit.
- Cohort JSONs do not record any arena-boundary information. There is
  no concept of "the cohort's canonical arena" today.
- Two arena-boundary sources exist or are in flight:
  - **Marked**: per-experiment circle/ellipse from the user's clicks
    (current SOT).
  - **Inferred**: U-Net predictions (Iteration 6 — EZM Arena Inference
    QC). Not yet a marking-mode variant.

### What "cohort-canonical arena" would mean

A cohort whose recordings share an arena geometry (same room, same
camera, same arena physical artifact) could carry one canonical
boundary that overrides per-experiment fits — useful when individual
fits diverge due to sparse edge points or dim frames.

Proposed cohort JSON additions:

```json
"canonical_arena": {
  "source": "marked_aggregate" | "inference" | "manual",
  "geometry": { "ellipse": {...}, "fit_residual_px": ..., "n_contributing": ... },
  "computed_at": "...",
  "computed_by": "mus1 cohort fit-arena ..."
}
```

Stats + overlay code reads `cohort.canonical_arena` first, falls back
to per-experiment marking if absent. Switching is one line in the
overlay code per pane.

### Open design questions (the pitch)

Before building this, decide:

1. **Authoritativeness.** When `canonical_arena` and per-experiment
   markings disagree, who wins?
   (a) Cohort wins for cohort-scoped analyses; per-experiment wins
       for ad-hoc views.
   (b) Cohort is a *suggestion*; per-experiment markings remain SOT.
   (c) Cohort is canonical and per-experiment markings get a
       provenance tag pointing at the cohort fit.
   Lean: (a) — cohort-scoped analyses use cohort geometry; cohort
   QC dashboards already enforce that scope.

2. **Aggregation method.** "Marked aggregate" could be per-coordinate
   median, circle fit through all per-experiment centers + radii, or
   outlier-resistant geometric mean. Default suggestion: median
   ellipse + reject any contributing fit beyond 2σ in axes / center
   distance.

3. **Inference path.** Iteration 6 ships EZM U-Net QC; until then,
   cohort-canonical arena is marked-aggregate only for EZM. NOR/NOF
   has no inference pipeline planned today.

4. **Trigger.** Explicit (`mus1 cohort fit-arena <name>`) or
   recomputed on every `save_cohort()`. Lean: explicit — silent
   recomputation makes downstream stats results vary based on
   cohort-edit history rather than scientific decisions.

5. **CLI surface (the user's specific ask)**:
   - `mus1 cohort fit-arena <name> --source marked` (today)
   - `mus1 cohort fit-arena <name> --source inference` (post-Iter 6)
   - `mus1 cohort fit-arena <name> --source manual --ellipse '{...}'`
     for explicit overrides.
   - `mus1 cohort show-arena <name>` prints the current canonical.

### When to bring this back to the user

Deferred for explicit pitch + go-ahead before implementation. Not
gated on Iteration 6 (marked-aggregate works standalone), more useful
once inference exists. The pitch should include a side-by-side
overlay of marked-aggregate vs three example-experiment fits for
one publication cohort and one validation cohort — visual evidence
drives the design decisions above.

---

## Loose ends for future iterations

- **NOR/NOF Tracking QC trajectory rendering — VERIFIED RENDERS CORRECTLY
  AFTER CACHE INVALIDATION (2026-05-03).** User initially reported
  trajectory not visible on `NOR_VAL_1002_2026-04-07`. End-to-end
  reproduction outside Streamlit (loader → overlay drawer) confirms
  the trajectory renders: 36066/36067 valid frames, ~6.7% of pixels
  changed by the overlay (zones + trajectory + dividers + radius
  circle), trajectory cleanly visible cyan→green→yellow across the
  arena. Output verified at `/tmp/test_overlay.png` during diagnosis.
  Validation videos are 1080×1080 (vs. 1280×720 for publication) — no
  bug, just a different resolution; DLC and overlay coordinates are
  consistent because both reference the same source video. **Root
  cause of the user-visible symptom: stale Streamlit cache served
  from before the DLC schema fix shipped.** Fix shipped 2026-05-03:
  added `Refresh (clear cache)` button to the pane (matching the EZM
  panes). One-time workaround for already-running sessions: hit the
  new Refresh button or restart `streamlit run`.
- **`views/nor_nof_interaction_qc.py` filename should track the rename
  to `NOR/NOF Tracking QC`.** The display label was renamed
  2026-05-03; the file rename is deferred to avoid breaking the
  `from .views.nor_nof_interaction_qc import render_nor_nof_interaction_qc`
  import chain in `app.py`. Do as part of Iteration 5.5d.
- **Training Monitor → Job Monitor.** The current name "Training
  Monitor" undersells the pane: it tracks any Slurm job created via
  the `mus1_runs/` registry, not just training. Rename when scope
  expands beyond ML training (e.g., compute jobs from Iteration 5.5c
  surfaced through the same registry).
- `views/ezm_ml.py` still uses `sys.path.insert()` to reach
  `workspace/torch_ml/`; the model definition should move into
  `mus1.compute.ezm_zones_model` (in progress; see Iteration 6).
- `views/experiments.py` still uses the legacy `has_nor_nof_roi`
  artifact flag in its filter; that flag was meaningful when the v2
  ROI pane produced its own JSONs but is now redundant with
  `arena_markings`.
- `mus1.db` is a rebuildable index but `Subjects` and `Experiments`
  panes still query it directly; migrate them to `ExperimentService`
  to keep a single discovery contract.
- **DB schema migrations.** Today `create_all()` is the only schema
  evolution mechanism. Phase 4 should add Alembic-style forward-only
  migrations; SQLite stays as a rebuildable cache.
- **Frame export for publication supplements.** Per the user note in
  ARCHITECTURE_CURRENT.md §12, QC panes should support "save the
  reviewed frame as PNG with overlays burned in" so manuscript
  supplements can include the exact frame the human verified.
  AnnotationService already exports provenance frames; expose a
  per-pane button.

---

## Future research (deferred, tracked)

These features are in research/exploration phase. Revisit when the
core platform is stable and their upstream dependencies mature.

| Feature | Depends on | Notes |
|---------|-----------|-------|
| Arena inference (automated boundary detection) | U-Net training pipeline (EZM in progress, NOR/NOF research) | EZM addressed by Iteration 6. NOR/NOF: brightness edge detection. |
| ML genotype classifier | KPMS syllable extraction complete | Predict genotype/phenotype from behavioral syllable profiles. Promising but data-limited. |
| ML tracking metadata model | KPMS extraction + cross-task fingerprint | Classify sessions by behavioral regime. Currently stale (built on trim30s syllables). |
| Figure viewer + stats integration | Stats package extracted as a separate pip package | Display generated figures in app, trigger stats re-runs, diff outputs. |
| Training monitor for DLC/SLEAP | React UI rebuild | Monitor GPU job status, view training curves. Useful for any lab training models on cluster. |
| LLM/MCP-wrapped lab interface | Service layer + FastAPI complete (DONE) | Per the user note in ARCHITECTURE_CURRENT.md §12: integrate the consistently-used stats and good layouts as MCP tools, leave deterministic computation deterministic. |

---

## Recently shipped (one-line tail; full detail in ARCHITECTURE_CURRENT.md)

- 2026-05-04 — **Bug fix + UX clarity**: dropped buggy frame-nav button cluster from EZM Tracking QC (StreamlitAPIException after slider instantiation; operator never used the buttons; emojis annoying); slider remains. Added "effect only on Compute" caption to NOR/NOF Tracking QC variant section; unsaved-compute display now stamps the variant slug it was computed for and shows ⚠ when current axes drift from it. Iterations 9 + 10 added to roadmap (frame-fetch preference; cohort-canonical arena boundary — pitch deferred).
- 2026-05-04 — **Iteration 5.5 (Phase B) — NOR/NOF Tracking QC parity**: 4-axis variant picker (radius / LH / buffer mode / bodypart bound), baseline DLC confidence panel at top of pane, in-pane Compute (session state, "(unsaved)") + Save → `qc_review.exploratory_runs[]`, Compare-against-saved dropdown, QC review schema migrated to `computed_metrics.nor_nof_interaction.qc_review` with one-time legacy migration on first save (history-preserving). 10 new helper tests (46/46 passing).
- 2026-05-04 — **Iteration 5.4 — pre-Phase-B cleanup**: `mus1.paths.resolve_with_mount_aliases` (5 reimplementations collapsed); `resolve_dlc_csv_path` moved `web.discovery → compute.tracking` (alias kept); two QC panes migrated to `compute.tracking.try_read_dlc_csv` (8→6 inline DLC reads); `mus1.compute.tracking_flags` (vocabulary + `merge_into_qc_flags` helper, single source for CLI `--write` and pane); dead `EXPERIMENT_DATA_ROOT` deleted; `views/subjects.py` and `core/importers/ezm_unet_runs.py` migrated off direct `tracking_file_path` reads. 17 new tests.
- 2026-05-04 — **Phase A foundations shipped** (5 modules + 19 tests passing): `docs/web/SCHEMA_VARIANTS.md` (three-layer compute schema), `mus1.compute.tracking_confidence` (task-agnostic DLC baseline confidence), `TRACKING_QUALITY_FLAGS` vocabulary in `qc_flags_shared`, `mus1.preferences` (cascading user → project YAML), `mus1 compute tracking-confidence <id|--cohort>` CLI; FastAPI/services migrated off direct `tracking_file_path` reads (same bug class as the web fix); cleanup sweep cataloged in this doc
- 2026-05-03 — Sidebar reorder (task-aligned lifecycle: Browse → Cohort → EZM Mark/QC → NOR/NOF Mark/QC → Train); pane rename `NOR/NOF Interaction QC` → `NOR/NOF Tracking QC` (display label only — file rename deferred); `Refresh (clear cache)` button added to NOR/NOF Tracking QC (parity with EZM panes); Tracking QC Review block in NOR/NOF Tracking QC now matches EZM (5-status radio: `(not reviewed)`/`good`/`poor_tracking`/`exclude`/`needs_re_review` — schema migration to `computed_metrics.nor_nof.qc_review` deferred to Iteration 5.5d)
- 2026-05-03 — DLC schema duality resolver; per-pane scope banner; QC pane contract codified; NOR/NOF Tracking QC degrades gracefully when metrics absent
- 2026-04-28 — Iteration 1.5: three-tier sidebar contract (`web/filters.py`); 6 panes migrated; net −300 LOC
- 2026-04-27 — Iteration 1: pane consolidation (Annotator / NOR/NOF QC / NOR/NOF ROI removed; EZM Wedge Marking promoted; sidebar grouped by lifecycle; `cohorts.save_cohort()` auto-derives `task_types`; NOR↔NOF auto-pair)
- 2026-04-01 — Phases 1+2+3 complete in one session: TaskRegistry, ExperimentService / CohortService / QCService / AnnotationService, compute library, ComputeHarness, FastAPI backend (19 endpoints, all tested)
- 2026-03-27 — Phase 1: Task definition system (5 built-ins, YAML extensibility, configurable objects)
