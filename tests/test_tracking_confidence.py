"""Tests for ``mus1.compute.tracking_confidence``.

Covers:
  - all-high-likelihood synthetic CSV produces no flags
  - one-bad-bodypart triggers BODYPART_FAILURE
  - all-low-likelihood triggers LOW_LIKELIHOOD_OVERALL
  - long all-low run triggers LIKELIHOOD_DROPOUT_RUN
  - empty / malformed CSV returns valid dict with error
  - threshold overrides take effect
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from mus1.compute.tracking_confidence import (
    DEFAULT_PCUTOFF,
    compute_tracking_confidence,
)


# ---------------------------------------------------------------------------
# Synthetic CSV helpers
# ---------------------------------------------------------------------------

def _write_dlc_csv(
    path: Path,
    *,
    n_frames: int,
    bodyparts: list[str],
    likelihoods: dict[str, np.ndarray],
) -> None:
    """Write a 3-row-header DLC-style CSV with the given likelihood arrays.

    Coordinates are filled with arbitrary finite values; only likelihoods
    matter for tracking-confidence tests.
    """
    cols = []
    data = {}
    scorer = "DLC_test"
    for bp in bodyparts:
        for coord in ("x", "y", "likelihood"):
            cols.append((scorer, bp, coord))
            if coord == "likelihood":
                data[(scorer, bp, coord)] = likelihoods[bp]
            else:
                data[(scorer, bp, coord)] = np.linspace(100.0, 200.0, n_frames)
    df = pd.DataFrame(data, columns=pd.MultiIndex.from_tuples(cols))
    df.index.name = "scorer"
    df.to_csv(path)


def _all_lh(n: int, value: float) -> np.ndarray:
    return np.full(n, value, dtype=float)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_all_high_likelihood_no_flags(tmp_path: Path):
    n = 1000
    bps = ["head", "nose", "neck_base"]
    csv = tmp_path / "synthetic_high.csv"
    _write_dlc_csv(csv, n_frames=n, bodyparts=bps,
                   likelihoods={bp: _all_lh(n, 0.95) for bp in bps})

    res = compute_tracking_confidence(csv)
    assert res["error"] is None
    assert res["overall"]["n_frames"] == n
    assert res["overall"]["median_frac_above_pcutoff"] == 1.0
    assert res["overall"]["min_bodypart_frac_above_pcutoff"] == 1.0
    assert res["overall"]["longest_any_dropout_run_frames"] == 0
    assert res["flags"] == []
    for bp in bps:
        st = res["per_bodypart"][bp]
        assert st["frac_above_pcutoff"] == 1.0
        assert st["longest_dropout_run_frames"] == 0


def test_one_bad_bodypart_triggers_bodypart_failure(tmp_path: Path):
    n = 1000
    bps = ["head", "nose", "neck_base"]
    csv = tmp_path / "synthetic_bp_fail.csv"
    lhs = {bp: _all_lh(n, 0.9) for bp in bps}
    lhs["nose"] = _all_lh(n, 0.2)  # below default 0.5 bp_frac threshold
    _write_dlc_csv(csv, n_frames=n, bodyparts=bps, likelihoods=lhs)

    res = compute_tracking_confidence(csv)
    assert res["error"] is None
    assert "BODYPART_FAILURE" in res["flags"]
    # The other bodyparts should be fine and the overall median should
    # be high enough that LOW_LIKELIHOOD_OVERALL does NOT fire (median
    # of [1.0, 0.0, 1.0] = 1.0 >= 0.80)
    assert "LOW_LIKELIHOOD_OVERALL" not in res["flags"]


def test_all_low_likelihood_triggers_overall_flag(tmp_path: Path):
    n = 1000
    bps = ["head", "nose", "neck_base"]
    csv = tmp_path / "synthetic_low.csv"
    _write_dlc_csv(csv, n_frames=n, bodyparts=bps,
                   likelihoods={bp: _all_lh(n, 0.4) for bp in bps})

    res = compute_tracking_confidence(csv)
    assert "LOW_LIKELIHOOD_OVERALL" in res["flags"]
    assert "BODYPART_FAILURE" in res["flags"]      # all bodyparts below 0.5
    # Every frame is below pcutoff for every bodypart → all-low-mask is
    # all True → longest run == n; ≥ default dropout_min_frames (30).
    assert "LIKELIHOOD_DROPOUT_RUN" in res["flags"]


def test_long_all_low_run_triggers_dropout_flag(tmp_path: Path):
    """Most of the session is fine; one 100-frame stretch is all-low."""
    n = 1000
    bps = ["head", "nose"]
    head = _all_lh(n, 0.9)
    nose = _all_lh(n, 0.9)
    head[300:400] = 0.2
    nose[300:400] = 0.2
    csv = tmp_path / "synthetic_dropout.csv"
    _write_dlc_csv(csv, n_frames=n, bodyparts=bps,
                   likelihoods={"head": head, "nose": nose})

    res = compute_tracking_confidence(csv)
    assert "LIKELIHOOD_DROPOUT_RUN" in res["flags"]
    assert res["overall"]["longest_any_dropout_run_frames"] == 100
    # Only 100/1000 = 10% below cutoff in either bodypart → median frac
    # above is 0.9 → no LOW_LIKELIHOOD_OVERALL
    assert "LOW_LIKELIHOOD_OVERALL" not in res["flags"]
    # 90% above pcutoff per bodypart → ≥ 0.5 → no BODYPART_FAILURE
    assert "BODYPART_FAILURE" not in res["flags"]


def test_threshold_overrides_take_effect(tmp_path: Path):
    """Same CSV, two threshold sets, different flag outcomes."""
    n = 500
    bps = ["head", "nose"]
    csv = tmp_path / "synthetic_75.csv"
    lhs = {bp: np.where(np.arange(n) < 375, 0.9, 0.2) for bp in bps}
    _write_dlc_csv(csv, n_frames=n, bodyparts=bps, likelihoods=lhs)

    # Default 80% threshold: 75% above pcutoff → fires
    res_default = compute_tracking_confidence(csv)
    assert "LOW_LIKELIHOOD_OVERALL" in res_default["flags"]

    # Lower the threshold to 0.7 → 75% > 70% → does NOT fire
    res_loose = compute_tracking_confidence(csv, overall_frac_threshold=0.7)
    assert "LOW_LIKELIHOOD_OVERALL" not in res_loose["flags"]


def test_missing_file_returns_error(tmp_path: Path):
    res = compute_tracking_confidence(tmp_path / "does_not_exist.csv")
    assert res["error"] is not None
    assert res["overall"]["n_frames"] == 0
    assert res["flags"] == []


def test_malformed_csv_returns_error(tmp_path: Path):
    bad = tmp_path / "bad.csv"
    bad.write_text("not,a,real,dlc,csv\n1,2,3,4,5\n")
    res = compute_tracking_confidence(bad)
    assert res["error"] is not None


def test_pcutoff_passed_through(tmp_path: Path):
    """The chosen pcutoff is recorded in both top-level and thresholds."""
    n = 100
    csv = tmp_path / "synthetic_pcutoff.csv"
    _write_dlc_csv(csv, n_frames=n, bodyparts=["head"],
                   likelihoods={"head": _all_lh(n, 0.95)})
    res = compute_tracking_confidence(csv, pcutoff=0.9)
    assert res["pcutoff"] == 0.9
    assert res["thresholds"]["pcutoff"] == 0.9


def test_default_pcutoff_matches_dlc_convention():
    """Sanity: the default value matches what's documented in DLC."""
    assert DEFAULT_PCUTOFF == 0.6
