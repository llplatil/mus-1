"""Tests for the tracking-comparison verdict store + comparison overlay drawer."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from mus1.web.tracking_comparison_store import (
    list_comparisons,
    read_comparison,
    write_comparison,
)
from mus1.web.ezm_trajectory_overlay import draw_ezm_comparison_overlay


def _exp_json(tmp_path: Path) -> Path:
    p = tmp_path / "EZM_001.json"
    p.write_text(json.dumps({"experiment_id": "EZM_001", "extraction": {"dlc_runs": []}}))
    return p


def test_write_and_read_roundtrip(tmp_path):
    jp = _exp_json(tmp_path)
    write_comparison(jp, run_a_id="v1", run_b_id="v2", verdict="B_better",
                     notes="tail_base fixed", reviewed_by="test")
    ext = json.loads(jp.read_text())["extraction"]
    got = read_comparison(ext, "v1", "v2")
    assert got["verdict"] == "B_better"
    assert got["notes"] == "tail_base fixed"
    # Order-agnostic lookup.
    assert read_comparison(ext, "v2", "v1")["verdict"] == "B_better"


def test_pair_normalized_and_deduped(tmp_path):
    jp = _exp_json(tmp_path)
    # Write with one order, then overwrite with the reversed order.
    write_comparison(jp, run_a_id="zzz", run_b_id="aaa", verdict="A_better")
    write_comparison(jp, run_a_id="aaa", run_b_id="zzz", verdict="tie")
    ext = json.loads(jp.read_text())["extraction"]
    comps = list_comparisons(ext)
    assert len(comps) == 1  # same pair collapsed
    # Stored in sorted order.
    assert comps[0]["run_a_id"] == "aaa" and comps[0]["run_b_id"] == "zzz"
    assert comps[0]["verdict"] == "tie"  # last write wins


def test_invalid_verdict_rejected(tmp_path):
    jp = _exp_json(tmp_path)
    with pytest.raises(ValueError):
        write_comparison(jp, run_a_id="v1", run_b_id="v2", verdict="nonsense")


def test_read_missing_returns_none(tmp_path):
    jp = _exp_json(tmp_path)
    ext = json.loads(jp.read_text())["extraction"]
    assert read_comparison(ext, "v1", "v2") is None
    assert list_comparisons(None) == []


def test_two_pairs_coexist(tmp_path):
    jp = _exp_json(tmp_path)
    write_comparison(jp, run_a_id="v1", run_b_id="v2", verdict="B_better")
    write_comparison(jp, run_a_id="v2", run_b_id="v3", verdict="A_better")
    ext = json.loads(jp.read_text())["extraction"]
    assert len(list_comparisons(ext)) == 2


# ---------------------------------------------------------------------------
# Overlay drawer
# ---------------------------------------------------------------------------

def _track(n: int, shift: float = 0.0) -> dict:
    return {
        "x": np.linspace(100, 400, n) + shift,
        "y": np.full(n, 300.0),
        "ok": np.ones(n, dtype=bool),
    }


def test_comparison_overlay_returns_rgb_frame():
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    out = draw_ezm_comparison_overlay(
        frame, None, _track(100), _track(100, shift=20.0),
        label_a="A", label_b="B", highlight_frame=50, window=30, show_zones=False,
    )
    assert out.shape == (480, 640, 3)
    assert out.dtype == np.uint8
    # Something was drawn (frame no longer all zeros).
    assert out.sum() > 0


def test_comparison_overlay_handles_missing_track():
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    out = draw_ezm_comparison_overlay(
        frame, None, _track(100), None,
        highlight_frame=50, window=30, show_zones=False,
    )
    assert out.shape == (480, 640, 3)
