"""Tests for ``mus1.arena_profiles`` + ``mus1.compute.scaling`` cascade.

Covers:
  - builtin profiles registered with correct dimensions/states
  - geometry mm_per_pixel arithmetic
  - YAML loader registers external profiles + supports state list
  - compute_px_to_mm cascade: per-experiment override > task default >
    missing_arena_boundary > missing
  - resolve_arena_state: explicit state, default state, override,
    unknown state passthrough
  - back-compat: TaskDefinition.arena_physical_dimensions still
    returns the dict shape downstream code expects
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from mus1.arena_profiles import (
    AnnularGeometry,
    ArenaProfile,
    ArenaProfileRegistry,
    ArenaState,
    CircularGeometry,
)
from mus1.compute.scaling import (
    SOURCE_MISSING,
    SOURCE_PER_EXPERIMENT_OVERRIDE,
    SOURCE_TASK_DEFAULT,
    compute_px_to_mm,
    resolve_arena_state,
)


# ---------------------------------------------------------------------------
# Builtins
# ---------------------------------------------------------------------------

def test_builtins_registered_with_expected_dimensions():
    reg = ArenaProfileRegistry()
    tamco = reg.get("tamco_black_bucket")
    assert isinstance(tamco.geometry, CircularGeometry)
    assert tamco.geometry.diameter_mm == pytest.approx(441.325)
    # Two states; default = original
    assert tamco.state_ids() == ["original", "resanded"]
    assert tamco.default_state_id == "original"

    hd = reg.get("home_depot_5gal_orange")
    assert isinstance(hd.geometry, CircularGeometry)
    assert hd.geometry.diameter_mm == 292.0
    assert hd.state_ids() == []

    ezm = reg.get("ezm_460mm")
    assert isinstance(ezm.geometry, AnnularGeometry)
    assert ezm.geometry.outer_diameter_mm == 460.0
    assert ezm.geometry.inner_ratio == pytest.approx(0.761)


def test_circular_mm_per_pixel():
    g = CircularGeometry(diameter_mm=441.325)
    assert g.mm_per_pixel(700.0) == pytest.approx(441.325 / 700.0)
    assert g.mm_per_pixel(0.0) is None


def test_annular_mm_per_pixel_uses_outer_diameter():
    g = AnnularGeometry(outer_diameter_mm=460.0, inner_ratio=0.761)
    assert g.mm_per_pixel(800.0) == pytest.approx(460.0 / 800.0)


def test_state_lookup_and_resolution():
    reg = ArenaProfileRegistry()
    tamco = reg.get("tamco_black_bucket")
    assert tamco.get_state("resanded").description.startswith("Surface re-sanded")
    assert tamco.get_state("nonexistent") is None
    # Explicit request honored even if known
    assert tamco.resolve_state_id("resanded") == "resanded"
    # Unknown request: returned as-is (we don't silently rewrite operator input)
    assert tamco.resolve_state_id("unknown") == "unknown"
    # Unset: falls back to default
    assert tamco.resolve_state_id(None) == "original"
    assert tamco.resolve_state_id("") == "original"


# ---------------------------------------------------------------------------
# YAML loader
# ---------------------------------------------------------------------------

def test_yaml_loader_registers_profile(tmp_path: Path):
    yaml_path = tmp_path / "extra_profiles.yaml"
    yaml_path.write_text(yaml.safe_dump({
        "arena_profiles": [
            {
                "id": "lab42_box",
                "description": "60x40 cm rectangular open field (Lab 42).",
                "geometry": {
                    "shape": "circular",  # treat as effective circular for scaling
                    "diameter_mm": 600.0,
                },
                "states": [
                    {"id": "v1", "description": "v1 box"},
                    {"id": "v2", "description": "v2 box"},
                ],
                "default_state_id": "v1",
            },
        ],
    }))
    reg = ArenaProfileRegistry()
    n = reg.load_from_yaml(yaml_path)
    assert n == 1
    profile = reg.get("lab42_box")
    assert profile.geometry.diameter_mm == 600.0
    assert profile.state_ids() == ["v1", "v2"]
    assert profile.default_state_id == "v1"


def test_yaml_loader_missing_file_is_noop(tmp_path: Path):
    reg = ArenaProfileRegistry()
    assert reg.load_from_yaml(tmp_path / "no_such_file.yaml") == 0


# ---------------------------------------------------------------------------
# compute_px_to_mm cascade
# ---------------------------------------------------------------------------

class _FakeTask:
    """Minimal stand-in for TaskDefinition used in cascade tests."""
    def __init__(self, profile_id):
        self._pid = profile_id

    @property
    def arena_profile_id(self):
        return self._pid


def _experiment(boundary_axes, *, override=None):
    am = {}
    if boundary_axes is not None:
        am["arena_boundary"] = {"ellipse": {"axes": boundary_axes}}
    if override is not None:
        am["arena_profile"] = override
    return {"arena_markings": am}


def test_cascade_uses_task_default_when_no_override():
    exp = _experiment([700.0, 700.0])
    task = _FakeTask("tamco_black_bucket")
    value, source = compute_px_to_mm(exp, task)
    assert value == pytest.approx(441.325 / 700.0)
    assert source == SOURCE_TASK_DEFAULT


def test_cascade_per_experiment_override_wins():
    exp = _experiment(
        [700.0, 700.0],
        override={"profile_id": "home_depot_5gal_orange"},
    )
    task = _FakeTask("tamco_black_bucket")
    value, source = compute_px_to_mm(exp, task)
    # 292 / 700, not 441.325 / 700
    assert value == pytest.approx(292.0 / 700.0)
    assert source == SOURCE_PER_EXPERIMENT_OVERRIDE


def test_cascade_missing_boundary_returns_none():
    exp = _experiment(None)
    task = _FakeTask("tamco_black_bucket")
    value, source = compute_px_to_mm(exp, task)
    assert value is None
    assert source == "missing_arena_boundary"


def test_cascade_no_profile_at_all_returns_missing():
    exp = _experiment([700.0, 700.0])
    task = _FakeTask(None)  # task with no default profile (rotarod-like)
    value, source = compute_px_to_mm(exp, task)
    assert value is None
    assert source == SOURCE_MISSING


def test_cascade_unknown_profile_id_returns_missing_profile():
    exp = _experiment(
        [700.0, 700.0],
        override={"profile_id": "this_profile_does_not_exist"},
    )
    task = _FakeTask("tamco_black_bucket")
    value, source = compute_px_to_mm(exp, task)
    assert value is None
    assert source == "missing_arena_profile"


# ---------------------------------------------------------------------------
# resolve_arena_state
# ---------------------------------------------------------------------------

def test_resolve_state_picks_default_when_unset():
    exp = _experiment([700.0, 700.0])
    task = _FakeTask("tamco_black_bucket")
    state, profile = resolve_arena_state(exp, task)
    assert profile.id == "tamco_black_bucket"
    assert state == "original"


def test_resolve_state_explicit_request_honored():
    exp = _experiment(
        [700.0, 700.0],
        override={"profile_id": "tamco_black_bucket", "state_id": "resanded"},
    )
    task = _FakeTask("tamco_black_bucket")
    state, profile = resolve_arena_state(exp, task)
    assert state == "resanded"
    assert profile.id == "tamco_black_bucket"


def test_resolve_state_no_states_returns_none():
    exp = _experiment([700.0, 700.0])
    task = _FakeTask("home_depot_5gal_orange")
    state, profile = resolve_arena_state(exp, task)
    assert profile.id == "home_depot_5gal_orange"
    assert state is None


# ---------------------------------------------------------------------------
# Back-compat: TaskDefinition.arena_physical_dimensions
# ---------------------------------------------------------------------------

def test_task_arena_physical_dimensions_reads_through_profile():
    from mus1.tasks.builtins.nor import NORTask
    task = NORTask()
    dims = task.arena_physical_dimensions
    assert dims.get("diameter_mm") == pytest.approx(441.325)


def test_p_no_task_uses_home_depot_profile():
    from mus1.tasks.builtins.p_no import PNOTask
    task = PNOTask()
    assert task.arena_profile_id == "home_depot_5gal_orange"
    dims = task.arena_physical_dimensions
    assert dims.get("diameter_mm") == 292.0
