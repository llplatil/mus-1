# mus1 Compute Library — Deterministic vs Stochastic Boundary

## What this library is

All code in `mus1/compute/` is **deterministic**: given the same inputs
(tracking CSV + arena definition + parameter set), it always produces
bit-identical outputs. There are no random seeds, no ML inference calls,
no network requests, no floating-point non-determinism from GPU operations.

This is the code that produces the numbers in your paper.

## What "deterministic" means here

| Property | Guarantee |
|----------|-----------|
| Same DLC CSV + same zone definition + same parameters → same metrics | Always |
| Rerunning on a different machine with same Python/numpy versions | Identical |
| Adding new experiments to the dataset changes existing metrics | Never |
| Parameter changes silently propagate | Never — every computation records its full parameter set in the experiment JSON |

## Where stochastic methods live

Stochastic (non-deterministic) processing happens **upstream** of this
library. Their outputs become the inputs to deterministic compute:

| Stochastic stage | Tool | Output (input to compute/) |
|-----------------|------|---------------------------|
| Pose estimation | DeepLabCut, SLEAP | Tracking CSVs (x, y, likelihood per bodypart per frame) |
| Behavioral syllable fitting | KPMS, MoSeq2 | Syllable labels per frame (h5/results files) |
| Arena boundary detection | U-Net, geometric autofitting | Zone definition JSONs |
| Future ML models | Custom | Predictions, embeddings |

The boundary is clear: **raw tracking data in, reproducible metrics out.**

## Parameter provenance

Every time a computation runs, the full parameter set is recorded in the
experiment JSON under `computed_metrics.{task_key}.variants.{variant_name}`:

```json
{
  "computed_metrics": {
    "ezm_open_closed": {
      "variants": {
        "raw_head_06": {
          "parameters": {
            "bodypart_preferred": "head",
            "position_mode": "raw",
            "likelihood_threshold": 0.6,
            "dwell_time_s": 0.5,
            "hysteresis_deg": 2.0,
            "immobility_cm_s": 2.0,
            "outer_diameter_mm": 460.0
          },
          "metrics": {
            "open_time_s": 42.3,
            "closed_time_s": 257.7,
            "open_entries": 8,
            "latency_to_open_s": 15.2
          },
          "computed_at": "2026-03-12T18:30:00+00:00"
        }
      }
    }
  }
}
```

A reviewer can re-run any computation with these parameters and get
identical results. This is the audit trail.

## Agent-generated code and the deterministic boundary

When an AI agent generates a new `TaskDefinition` (via Python subclass or
YAML config), it is generating **configuration** for deterministic code —
the same kind of configuration a human researcher would write. Specifically:

- The agent decides *which* bodypart to track, *what* likelihood threshold
  to use, *how* to define an interaction zone → these are **parameter choices**
- The compute library executes these choices deterministically → the
  **computation itself** is not stochastic

This is the design principle: "leave the deterministic stuff deterministic,
build around easy stochastic implementation for things that need to be
modular per lab." The agent configures; the compute library executes.

Things an agent can safely generate:
- Task definitions (new arena types, annotation schemas, QC flags)
- Variant parameter sets (new bodypart/threshold combinations)
- Interaction zone radius configurations
- Physical dimension specifications (arena diameter in mm)

Things an agent CAN generate with harness validation:
- Core metric formulas (e.g., zone classifier for a new maze type)
- New interaction scoring algorithms
- Novel bout-detection strategies

Things an agent should NOT generate without researcher review:
- Statistical tests and their assumptions
- Threshold values that determine inclusion/exclusion

The distinction: an agent can write the code, but the researcher must
review the harness report before the code goes to production.

## Validation pattern

The **variant comparison workflow** exists specifically so researchers can
visually verify that a computation strategy produces sensible results
before committing to it for publication:

1. Define multiple variants (e.g. different bodyparts, thresholds)
2. Compute all variants on the same experiments
3. Compare side-by-side in the QC view (tracking overlay + metrics table)
4. Select the primary variant for publication
5. Record the selection and its rationale

This is how the gap between "an agent configured this" and "a researcher
approved this for publication" gets bridged.

## Compute harness — vetting agent-generated code

When an agent generates a new compute function (e.g., "write me a zone
classifier for a Y-maze"), it must validate it through `ComputeHarness`
before the researcher reviews. The harness provides structured evidence,
not a pass/fail judgment.

### How the harness works

```python
from mus1.compute.harness import ComputeHarness

harness = ComputeHarness(
    name="ymaze_zone_classifier",
    version="0.1.0",
    output_dir=Path("harness_output/ymaze_v0.1"),
)

# Register the function under test
harness.register(my_classify_function)

# 1. DETERMINISM: same inputs must produce identical outputs
harness.check_determinism(sample_inputs, n_runs=3)

# 2. SENSITIVITY: vary one parameter, show how outputs change
harness.sweep_parameter("threshold", [0.3, 0.5, 0.7, 0.9], base_inputs,
                         output_keys=["open_time_s", "closed_time_s"])

# 3. BENCHMARK: how fast is it per video?
harness.benchmark(sample_inputs, n_runs=5)

# 4. SNAPSHOT: save a baseline for future regression detection
outputs = my_classify_function(**sample_inputs)
harness.save_snapshot("baseline_v1", outputs)

# 5. REGRESSION: compare against baseline after code changes
harness.compare_snapshot("baseline_v1", new_outputs)

# 6. REPORT: generate human-readable markdown
report = harness.write_report()
```

### What the harness report contains

The report is a markdown file the researcher reads before approving:

- **Determinism check**: Did N runs produce identical hashes? If not,
  the function has a non-determinism bug (global state, uninitialized
  memory, accidental RNG).

- **Parameter sweep table**: How does each output metric change as one
  parameter varies? The researcher judges whether the sensitivity is
  reasonable. Example: doubling the interaction radius should roughly
  double interaction time, not produce zero or infinity.

- **Benchmark**: Wall-clock time per call. A function that takes 10s
  per video will be painful at 900 experiments.

- **Snapshot comparison**: After code changes, which specific output
  values changed and by how much? The researcher decides whether the
  changes are expected.

### What the researcher reviews

The harness does NOT decide correctness — the researcher does. The
harness provides evidence; the researcher asks:

1. **Does the function do what I expect?** Run it on a few known
   experiments and compare the output to your mental model or hand
   calculations.

2. **Is it sensitive to the right things?** The parameter sweep should
   show that changing the threshold changes the output in the expected
   direction. If a threshold has no effect, something is wrong.

3. **Does it break when it should?** Feed it garbage inputs (wrong
   bodypart name, empty tracking, tiny video). It should fail
   gracefully, not silently produce zeros.

4. **Does it match prior work?** If replacing an existing function,
   the snapshot comparison shows exactly what changed. Zero diffs means
   exact equivalence. Small diffs need explanation.

### Agent workflow: generating new compute code

When an agent is asked to write a new compute function (e.g., Y-maze
zone classification), the workflow is:

1. **Agent reads the existing patterns**: Look at `ezm_zones.py` or
   `nor_nof_interaction.py` for the input/output contract.

2. **Agent writes the function**: Pure Python, no side effects, takes
   numpy arrays + parameters, returns a dict of metrics.

3. **Agent writes a harness test**: Uses `ComputeHarness` to run all
   5 checks (determinism, sweep, benchmark, snapshot, report).

4. **Agent saves the harness output**: The report goes into a
   directory the researcher can review.

5. **Researcher reviews**: Reads the report, inspects a few
   experiments visually, approves or requests changes.

6. **Agent integrates**: Adds the function to the task definition's
   variant list, re-runs stats scripts.

The harness output is saved alongside the compute code — it's part of
the audit trail, just like parameter provenance in experiment JSONs.

## Module index

| Module | Status | Extracted from | Key computations |
|--------|--------|--------------|------------------|
| `arena_geometry.py` | Complete | `ezm_geometry.py` | Kasa circle fit, ellipse fitting, wedge angle computation, zone construction |
| `ezm_zones_model.py` | Complete | `ezm_open_closed_zones.py` | ZoneDefinition, classify_points, angle math, zone I/O |
| `ezm_zones.py` | Complete | `ezm_compute_bridge.py` | 6-phase EZM pipeline (context fill, transitions, latency, ghost rejection, consensus, gated entries) |
| `nor_nof_interaction.py` | Complete | `compute_nor_nof_object_interactions.py` | ObjectROI, distance thresholding, Otsu buffer, bout detection, novelty index |
| `tracking.py` | Complete | Consolidated from 3 duplicates | DLC CSV reading, bodypart track extraction, likelihood filtering, interpolation |
| `overlay.py` | Complete | `ezm_trajectory_overlay.py` | Temporal trajectory, zone sector shading, transition dots, corrected-head overlay |
| `ezm_masks.py` | Complete | `ezm_masks.py` | Semantic segmentation masks (open/closed), annotation-based masks, blend overlays |
| `harness.py` | Complete | New | ComputeHarness: determinism, sweep, snapshot, benchmark, human-readable reports |
