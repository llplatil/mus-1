"""Compute harness — validate agent-generated compute functions.

When an AI agent generates a new compute function (e.g., "write me a
zone classifier for a Y-maze"), the harness provides a structured way to
test, visualize, and compare its outputs before the researcher approves
it for production use.

The harness does NOT judge whether the compute is "correct" — that's the
researcher's job. It provides the evidence needed to make that judgment:
snapshot comparisons, sensitivity analysis, visual overlays, and
determinism checks.

Usage (by an agent implementing a new compute function)::

    from mus1.compute.harness import ComputeHarness

    harness = ComputeHarness(
        name="ymaze_zone_classifier",
        version="0.1.0",
        output_dir=Path("harness_output/ymaze_v0.1"),
    )

    # Register the function under test
    harness.register(my_classify_function, input_schema={...}, output_schema={...})

    # Run determinism check (same inputs twice → identical outputs)
    harness.check_determinism(sample_inputs)

    # Run sensitivity analysis (vary one parameter at a time)
    harness.sweep_parameter("threshold", [0.3, 0.5, 0.7, 0.9], base_inputs)

    # Snapshot test (compare against saved baseline)
    harness.compare_snapshot("baseline_v1", current_outputs)

    # Generate human-readable report
    harness.write_report()
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class HarnessResult:
    """Result of a single harness check."""
    check_name: str
    passed: bool
    detail: str
    data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ParameterSweepRow:
    """One row in a parameter sweep table."""
    param_name: str
    param_value: Any
    outputs: Dict[str, Any]


def _stable_hash(obj: Any) -> str:
    """Deterministic hash of a nested dict/list/scalar structure."""
    s = json.dumps(obj, sort_keys=True, default=_json_default)
    return hashlib.sha256(s.encode()).hexdigest()[:16]


def _json_default(obj: Any) -> Any:
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        if np.isnan(obj):
            return "NaN"
        return float(obj)
    if isinstance(obj, np.bool_):
        return bool(obj)
    return str(obj)


def _sanitize_for_json(obj: Any) -> Any:
    """Recursively convert numpy types to JSON-serializable Python types."""
    if isinstance(obj, dict):
        return {k: _sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize_for_json(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return None if np.isnan(obj) else float(obj)
    if isinstance(obj, np.bool_):
        return bool(obj)
    if isinstance(obj, float) and np.isnan(obj):
        return None
    return obj


class ComputeHarness:
    """Validation harness for compute functions.

    Provides structured testing for both built-in and agent-generated
    compute functions. The harness itself is deterministic — it only
    calls the function under test and records the results.
    """

    def __init__(
        self,
        name: str,
        version: str = "0.1.0",
        output_dir: Optional[Path] = None,
    ):
        self.name = name
        self.version = version
        self._output_dir = Path(output_dir) if output_dir else None
        self._func: Optional[Callable] = None
        self._func_name: str = ""
        self._input_schema: Dict[str, Any] = {}
        self._output_schema: Dict[str, Any] = {}
        self._results: List[HarnessResult] = []
        self._sweeps: List[ParameterSweepRow] = []

    def register(
        self,
        func: Callable,
        input_schema: Optional[Dict[str, Any]] = None,
        output_schema: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Register the compute function under test."""
        self._func = func
        self._func_name = getattr(func, "__name__", str(func))
        self._input_schema = input_schema or {}
        self._output_schema = output_schema or {}

    # ── Determinism check ───────────────────────────────────────────────────

    def check_determinism(
        self,
        inputs: Dict[str, Any],
        n_runs: int = 3,
    ) -> HarnessResult:
        """Call the function N times with identical inputs. All outputs must match.

        This is the most basic test: if a function claims to be deterministic,
        calling it twice with the same inputs must produce identical outputs.
        Catches: uninitialized memory, global state mutation, accidental RNG use.
        """
        if not self._func:
            raise ValueError("No function registered. Call register() first.")

        outputs = []
        hashes = []
        for i in range(n_runs):
            out = self._func(**inputs)
            h = _stable_hash(out)
            outputs.append(out)
            hashes.append(h)

        all_match = len(set(hashes)) == 1
        result = HarnessResult(
            check_name="determinism",
            passed=all_match,
            detail=(
                f"{n_runs} runs, hash={hashes[0]}"
                if all_match
                else f"{n_runs} runs, {len(set(hashes))} distinct hashes: {hashes}"
            ),
            data={"hashes": hashes, "n_runs": n_runs},
        )
        self._results.append(result)
        return result

    # ── Parameter sweep ─────────────────────────────────────────────────────

    def sweep_parameter(
        self,
        param_name: str,
        values: Sequence[Any],
        base_inputs: Dict[str, Any],
        output_keys: Optional[List[str]] = None,
    ) -> List[ParameterSweepRow]:
        """Vary one parameter while holding others fixed.

        Returns a list of (param_value, outputs) rows for the researcher
        to inspect. If output_keys is provided, only those keys are recorded.
        """
        if not self._func:
            raise ValueError("No function registered. Call register() first.")

        rows: List[ParameterSweepRow] = []
        for val in values:
            inputs = {**base_inputs, param_name: val}
            out = self._func(**inputs)
            if output_keys:
                out = {k: out[k] for k in output_keys if k in out}
            row = ParameterSweepRow(param_name=param_name, param_value=val, outputs=out)
            rows.append(row)
            self._sweeps.append(row)

        # Record result
        self._results.append(HarnessResult(
            check_name=f"sweep:{param_name}",
            passed=True,  # Sweep always "passes" — researcher judges the values
            detail=f"{len(values)} values for {param_name}",
            data={"param_name": param_name, "values": list(values)},
        ))
        return rows

    # ── Snapshot comparison ─────────────────────────────────────────────────

    def save_snapshot(
        self,
        snapshot_name: str,
        outputs: Dict[str, Any],
    ) -> Path:
        """Save current outputs as a named snapshot for future comparison."""
        if not self._output_dir:
            raise ValueError("output_dir not set")
        snap_dir = self._output_dir / "snapshots"
        snap_dir.mkdir(parents=True, exist_ok=True)
        snap_path = snap_dir / f"{snapshot_name}.json"
        snap_path.write_text(
            json.dumps(_sanitize_for_json(outputs), indent=2, default=_json_default) + "\n"
        )
        logger.info("Saved snapshot: %s", snap_path)
        return snap_path

    def compare_snapshot(
        self,
        snapshot_name: str,
        current_outputs: Dict[str, Any],
        rtol: float = 1e-9,
        atol: float = 1e-12,
    ) -> HarnessResult:
        """Compare current outputs against a saved snapshot.

        Numeric values are compared with tolerance (rtol, atol).
        Non-numeric values must match exactly.
        """
        if not self._output_dir:
            raise ValueError("output_dir not set")
        snap_path = self._output_dir / "snapshots" / f"{snapshot_name}.json"
        if not snap_path.exists():
            result = HarnessResult(
                check_name=f"snapshot:{snapshot_name}",
                passed=False,
                detail=f"Snapshot not found: {snap_path}. Save it first with save_snapshot().",
            )
            self._results.append(result)
            return result

        baseline = json.loads(snap_path.read_text())
        current = _sanitize_for_json(current_outputs)
        diffs = self._compare_dicts(baseline, current, rtol=rtol, atol=atol)

        result = HarnessResult(
            check_name=f"snapshot:{snapshot_name}",
            passed=len(diffs) == 0,
            detail=(
                "Matches baseline"
                if not diffs
                else f"{len(diffs)} differences: {diffs[:5]}"
            ),
            data={"diffs": diffs, "snapshot": snapshot_name},
        )
        self._results.append(result)
        return result

    @staticmethod
    def _compare_dicts(
        baseline: Any,
        current: Any,
        rtol: float,
        atol: float,
        path: str = "",
    ) -> List[str]:
        """Recursively compare two nested structures, reporting differences."""
        diffs: List[str] = []
        if isinstance(baseline, dict) and isinstance(current, dict):
            all_keys = set(baseline) | set(current)
            for k in sorted(all_keys):
                p = f"{path}.{k}" if path else k
                if k not in baseline:
                    diffs.append(f"{p}: NEW (not in baseline)")
                elif k not in current:
                    diffs.append(f"{p}: MISSING (in baseline but not current)")
                else:
                    diffs.extend(
                        ComputeHarness._compare_dicts(baseline[k], current[k], rtol, atol, p)
                    )
        elif isinstance(baseline, list) and isinstance(current, list):
            if len(baseline) != len(current):
                diffs.append(f"{path}: length {len(baseline)} → {len(current)}")
            for i, (b, c) in enumerate(zip(baseline, current)):
                diffs.extend(
                    ComputeHarness._compare_dicts(b, c, rtol, atol, f"{path}[{i}]")
                )
        elif isinstance(baseline, (int, float)) and isinstance(current, (int, float)):
            if baseline is None and current is None:
                pass
            elif baseline is None or current is None:
                diffs.append(f"{path}: {baseline} → {current}")
            elif not np.isclose(baseline, current, rtol=rtol, atol=atol, equal_nan=True):
                diffs.append(f"{path}: {baseline} → {current}")
        elif baseline != current:
            diffs.append(f"{path}: {baseline!r} → {current!r}")
        return diffs

    # ── Timing ──────────────────────────────────────────────────────────────

    def benchmark(
        self,
        inputs: Dict[str, Any],
        n_runs: int = 5,
    ) -> HarnessResult:
        """Time the function over N runs. Reports median wall-clock time."""
        if not self._func:
            raise ValueError("No function registered.")
        times = []
        for _ in range(n_runs):
            t0 = time.perf_counter()
            self._func(**inputs)
            times.append(time.perf_counter() - t0)
        median_ms = float(np.median(times)) * 1000
        result = HarnessResult(
            check_name="benchmark",
            passed=True,
            detail=f"median={median_ms:.1f}ms over {n_runs} runs",
            data={"times_ms": [t * 1000 for t in times], "median_ms": median_ms},
        )
        self._results.append(result)
        return result

    # ── Report ──────────────────────────────────────────────────────────────

    def write_report(self) -> str:
        """Generate a human-readable validation report.

        Returns the report text. Also writes to output_dir if set.
        """
        lines = [
            f"# Compute Harness Report: {self.name} v{self.version}",
            f"Function: {self._func_name}",
            "",
            "## Check Results",
            "",
        ]

        all_pass = True
        for r in self._results:
            status = "PASS" if r.passed else "FAIL"
            if not r.passed:
                all_pass = False
            lines.append(f"- [{status}] {r.check_name}: {r.detail}")

        if self._sweeps:
            lines.extend(["", "## Parameter Sweeps", ""])
            # Group by param_name
            by_param: Dict[str, List[ParameterSweepRow]] = {}
            for row in self._sweeps:
                by_param.setdefault(row.param_name, []).append(row)

            for param, rows in by_param.items():
                lines.append(f"### {param}")
                # Build a table
                if rows:
                    out_keys = sorted(rows[0].outputs.keys())
                    header = f"| {param} | " + " | ".join(out_keys) + " |"
                    sep = "|" + "---|" * (len(out_keys) + 1)
                    lines.extend([header, sep])
                    for row in rows:
                        vals = [str(row.param_value)] + [
                            f"{row.outputs.get(k, '')}" for k in out_keys
                        ]
                        lines.append("| " + " | ".join(vals) + " |")
                lines.append("")

        lines.extend([
            "",
            "## Verdict",
            "",
            f"{'ALL CHECKS PASSED' if all_pass else 'SOME CHECKS FAILED — review before production use'}",
            "",
            "---",
            f"Generated by mus1 compute harness v{self.version}",
        ])

        report = "\n".join(lines)

        if self._output_dir:
            self._output_dir.mkdir(parents=True, exist_ok=True)
            report_path = self._output_dir / "harness_report.md"
            report_path.write_text(report + "\n")
            logger.info("Report written to %s", report_path)

            # Also save structured results as JSON
            results_path = self._output_dir / "harness_results.json"
            results_path.write_text(json.dumps(
                _sanitize_for_json({
                    "name": self.name,
                    "version": self.version,
                    "function": self._func_name,
                    "checks": [
                        {
                            "name": r.check_name,
                            "passed": r.passed,
                            "detail": r.detail,
                            "data": r.data,
                        }
                        for r in self._results
                    ],
                }),
                indent=2,
                default=_json_default,
            ) + "\n")

        return report
