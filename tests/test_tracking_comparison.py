"""Tests for ``mus1.compute.tracking_comparison.compare_tracks``.

Covers:
  - identical trackings -> zero distance, full agreement, zero coverage delta
  - constant shift -> constant distance, agreement gated by radius
  - coverage delta when B drops a bodypart
  - frame-count mismatch -> truncation + warning
  - bodypart-set mismatch -> unmatched reported
  - unreadable CSV -> None
  - JSON serialization sanitizes NaN
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from mus1.compute.tracking_comparison import (
    compare_tracks,
    comparison_to_jsonable,
)

BPS = ["nose", "head", "tail_base"]


def _write_csv(
    path: Path,
    *,
    n: int,
    bodyparts: list[str],
    xy: dict[str, tuple[np.ndarray, np.ndarray]],
    lh: dict[str, np.ndarray],
) -> None:
    cols, data = [], {}
    scorer = "DLC_test"
    for bp in bodyparts:
        x, y = xy[bp]
        cols += [(scorer, bp, "x"), (scorer, bp, "y"), (scorer, bp, "likelihood")]
        data[(scorer, bp, "x")] = x
        data[(scorer, bp, "y")] = y
        data[(scorer, bp, "likelihood")] = lh[bp]
    df = pd.DataFrame(data, columns=pd.MultiIndex.from_tuples(cols))
    df.index.name = "scorer"
    df.to_csv(path)


def _ramp(n: int) -> np.ndarray:
    return np.linspace(100.0, 200.0, n)


def test_identical_tracks(tmp_path):
    n = 50
    xy = {bp: (_ramp(n), _ramp(n)) for bp in BPS}
    lh = {bp: np.full(n, 0.9) for bp in BPS}
    a, b = tmp_path / "a.csv", tmp_path / "b.csv"
    _write_csv(a, n=n, bodyparts=BPS, xy=xy, lh=lh)
    _write_csv(b, n=n, bodyparts=BPS, xy=xy, lh=lh)

    comp = compare_tracks(a, b, run_a_id="A", run_b_id="B")
    assert comp is not None
    assert comp.n_frames == n
    for bp in BPS:
        pbc = comp.per_bodypart[bp]
        assert pbc.median_distance_px == pytest.approx(0.0)
        assert pbc.agreement_frac == pytest.approx(1.0)
        assert pbc.coverage_delta == pytest.approx(0.0)
        assert pbc.n_both_ok == n
    # No disagreement -> timeline all ~0, max 0.
    assert comp.overall["max_disagreement_px"] == pytest.approx(0.0)


def test_constant_shift(tmp_path):
    n = 40
    xy_a = {bp: (_ramp(n), _ramp(n)) for bp in BPS}
    xy_b = {bp: (_ramp(n) + 5.0, _ramp(n)) for bp in BPS}  # shift +5 in x
    lh = {bp: np.full(n, 0.9) for bp in BPS}
    a, b = tmp_path / "a.csv", tmp_path / "b.csv"
    _write_csv(a, n=n, bodyparts=BPS, xy=xy_a, lh=lh)
    _write_csv(b, n=n, bodyparts=BPS, xy=xy_b, lh=lh)

    comp = compare_tracks(a, b, run_a_id="A", run_b_id="B", agreement_radius_px=10.0)
    for bp in BPS:
        pbc = comp.per_bodypart[bp]
        assert pbc.median_distance_px == pytest.approx(5.0)
        assert pbc.agreement_frac == pytest.approx(1.0)  # 5 <= 10

    # Tighten radius below the shift -> zero agreement.
    comp2 = compare_tracks(a, b, run_a_id="A", run_b_id="B", agreement_radius_px=3.0)
    for bp in BPS:
        assert comp2.per_bodypart[bp].agreement_frac == pytest.approx(0.0)


def test_coverage_delta_when_b_drops_bodypart(tmp_path):
    n = 100
    xy = {bp: (_ramp(n), _ramp(n)) for bp in BPS}
    lh_a = {bp: np.full(n, 0.9) for bp in BPS}
    lh_b = {bp: np.full(n, 0.9) for bp in BPS}
    # B: tail_base below threshold for the second half.
    lh_b["tail_base"] = np.concatenate([np.full(n // 2, 0.9), np.full(n // 2, 0.1)])
    a, b = tmp_path / "a.csv", tmp_path / "b.csv"
    _write_csv(a, n=n, bodyparts=BPS, xy=xy, lh=lh_a)
    _write_csv(b, n=n, bodyparts=BPS, xy=xy, lh=lh_b)

    comp = compare_tracks(a, b, run_a_id="A", run_b_id="B")
    tb = comp.per_bodypart["tail_base"]
    assert tb.coverage_a == pytest.approx(1.0)
    assert tb.coverage_b == pytest.approx(0.5)
    assert tb.coverage_delta == pytest.approx(-0.5)  # B worse
    assert tb.n_only_a_ok == 50
    # nose unaffected.
    assert comp.per_bodypart["nose"].coverage_delta == pytest.approx(0.0)


def test_frame_count_mismatch(tmp_path):
    xy20 = {bp: (_ramp(20), _ramp(20)) for bp in BPS}
    xy30 = {bp: (_ramp(30), _ramp(30)) for bp in BPS}
    lh20 = {bp: np.full(20, 0.9) for bp in BPS}
    lh30 = {bp: np.full(30, 0.9) for bp in BPS}
    a, b = tmp_path / "a.csv", tmp_path / "b.csv"
    _write_csv(a, n=20, bodyparts=BPS, xy=xy20, lh=lh20)
    _write_csv(b, n=30, bodyparts=BPS, xy=xy30, lh=lh30)

    comp = compare_tracks(a, b, run_a_id="A", run_b_id="B")
    assert comp.n_frames == 20
    assert any("frame-count mismatch" in w for w in comp.warnings)


def test_bodypart_set_mismatch(tmp_path):
    n = 10
    bps_a = ["nose", "head", "tail_base"]
    bps_b = ["nose", "head", "left_ear"]  # tail_base vs left_ear differ
    xy_a = {bp: (_ramp(n), _ramp(n)) for bp in bps_a}
    xy_b = {bp: (_ramp(n), _ramp(n)) for bp in bps_b}
    lh_a = {bp: np.full(n, 0.9) for bp in bps_a}
    lh_b = {bp: np.full(n, 0.9) for bp in bps_b}
    a, b = tmp_path / "a.csv", tmp_path / "b.csv"
    _write_csv(a, n=n, bodyparts=bps_a, xy=xy_a, lh=lh_a)
    _write_csv(b, n=n, bodyparts=bps_b, xy=xy_b, lh=lh_b)

    comp = compare_tracks(a, b, run_a_id="A", run_b_id="B")
    assert comp.bodyparts == ["head", "nose"]
    assert set(comp.unmatched_bodyparts) == {"tail_base", "left_ear"}


def test_top_disagreements_ranked(tmp_path):
    n = 20
    xy_a = {bp: (_ramp(n), _ramp(n)) for bp in BPS}
    # B identical except a big spike on tail_base at frame 7.
    xb = _ramp(n).copy()
    xb[7] += 99.0
    xy_b = {
        "nose": (_ramp(n), _ramp(n)),
        "head": (_ramp(n), _ramp(n)),
        "tail_base": (xb, _ramp(n)),
    }
    lh = {bp: np.full(n, 0.9) for bp in BPS}
    a, b = tmp_path / "a.csv", tmp_path / "b.csv"
    _write_csv(a, n=n, bodyparts=BPS, xy=xy_a, lh=lh)
    _write_csv(b, n=n, bodyparts=BPS, xy=xy_b, lh=lh)

    comp = compare_tracks(a, b, run_a_id="A", run_b_id="B", top_n=5)
    assert comp.top_disagreements[0].frame == 7
    assert comp.top_disagreements[0].bodypart == "tail_base"
    assert comp.top_disagreements[0].distance_px == pytest.approx(99.0)


def test_unreadable_csv_returns_none(tmp_path):
    a = tmp_path / "a.csv"
    a.write_text("not,a,dlc,csv\n1,2,3,4\n")
    b = tmp_path / "missing.csv"
    assert compare_tracks(a, b, run_a_id="A", run_b_id="B") is None


def test_jsonable_sanitizes_nan(tmp_path):
    # tail_base never both-ok -> NaN distance stats; must serialize to None.
    n = 10
    xy = {bp: (_ramp(n), _ramp(n)) for bp in BPS}
    lh_a = {bp: np.full(n, 0.9) for bp in BPS}
    lh_b = {bp: np.full(n, 0.9) for bp in BPS}
    lh_a["tail_base"] = np.full(n, 0.1)  # A never ok -> no both-ok frames
    a, b = tmp_path / "a.csv", tmp_path / "b.csv"
    _write_csv(a, n=n, bodyparts=BPS, xy=xy, lh=lh_a)
    _write_csv(b, n=n, bodyparts=BPS, xy=xy, lh=lh_b)

    comp = compare_tracks(a, b, run_a_id="A", run_b_id="B")
    js = comparison_to_jsonable(comp)
    import json
    json.dumps(js)  # must not raise (no NaN)
    assert js["per_bodypart"]["tail_base"]["median_distance_px"] is None
    assert js["per_bodypart"]["tail_base"]["agreement_frac"] is None
