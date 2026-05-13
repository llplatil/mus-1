"""Tests for cohort canonical_arena helpers (T3).

Covers:
  - create_cohort with/without canonical_arena
  - cohort_canonical_arena returns ``{}`` when unset, normalized otherwise
  - set_cohort_canonical_arena sets / clears the field
  - empty profile_id clears the field (not stored as ``{}``)
  - ArenaProfileRegistry.from_config reads project + user YAML layers
"""
from __future__ import annotations

from pathlib import Path

import pytest

from mus1.arena_profiles import ArenaProfileRegistry
from mus1.web.cohorts import (
    cohort_canonical_arena,
    create_cohort,
    set_cohort_canonical_arena,
)


# ---------------------------------------------------------------------------
# create_cohort
# ---------------------------------------------------------------------------

def test_create_cohort_without_canonical_arena_omits_field():
    coh = create_cohort("foo", task_types=["EZM"])
    assert "canonical_arena" not in coh


def test_create_cohort_with_canonical_arena_persists_it():
    coh = create_cohort(
        "foo",
        task_types=["NOR", "NOF"],
        canonical_arena={"profile_id": "tamco_black_bucket", "state_id": "resanded"},
    )
    assert coh["canonical_arena"] == {
        "profile_id": "tamco_black_bucket",
        "state_id": "resanded",
    }


def test_create_cohort_drops_empty_state_id():
    coh = create_cohort(
        "foo",
        canonical_arena={"profile_id": "ezm_460mm", "state_id": ""},
    )
    assert coh["canonical_arena"] == {"profile_id": "ezm_460mm"}
    assert "state_id" not in coh["canonical_arena"]


def test_create_cohort_with_only_state_id_drops_field_entirely():
    """No profile_id → no canonical_arena. State alone is meaningless."""
    coh = create_cohort(
        "foo",
        canonical_arena={"profile_id": "", "state_id": "resanded"},
    )
    assert "canonical_arena" not in coh


# ---------------------------------------------------------------------------
# cohort_canonical_arena reader
# ---------------------------------------------------------------------------

def test_reader_returns_empty_dict_when_unset():
    coh = create_cohort("foo")
    assert cohort_canonical_arena(coh) == {}


def test_reader_normalizes_legacy_payloads():
    coh = {"canonical_arena": {"profile_id": "  ezm_460mm  ", "state_id": "  "}}
    assert cohort_canonical_arena(coh) == {"profile_id": "ezm_460mm"}


def test_reader_tolerates_non_dict():
    coh = {"canonical_arena": "ezm_460mm"}  # malformed legacy
    assert cohort_canonical_arena(coh) == {}


# ---------------------------------------------------------------------------
# set_cohort_canonical_arena mutator
# ---------------------------------------------------------------------------

def test_setter_sets_field():
    coh = create_cohort("foo")
    set_cohort_canonical_arena(coh, "tamco_black_bucket", "old")
    assert coh["canonical_arena"] == {
        "profile_id": "tamco_black_bucket",
        "state_id": "old",
    }


def test_setter_clears_when_profile_id_empty():
    coh = create_cohort(
        "foo",
        canonical_arena={"profile_id": "ezm_460mm"},
    )
    assert "canonical_arena" in coh
    set_cohort_canonical_arena(coh, "")
    assert "canonical_arena" not in coh


def test_setter_clears_when_profile_id_none():
    coh = create_cohort(
        "foo",
        canonical_arena={"profile_id": "ezm_460mm"},
    )
    set_cohort_canonical_arena(coh, None)
    assert "canonical_arena" not in coh


# ---------------------------------------------------------------------------
# ArenaProfileRegistry.from_config — layered YAML
# ---------------------------------------------------------------------------

def test_from_config_with_no_yaml_layers_returns_builtins(tmp_path: Path):
    # Point user YAML to a non-existent path so we don't read the real one
    fake_user = tmp_path / "no_user.yaml"
    registry = ArenaProfileRegistry.from_config(tmp_path, user_yaml_path=fake_user)
    # Builtins are always loaded
    assert "tamco_black_bucket" in registry.list_ids()
    assert "ezm_460mm" in registry.list_ids()
    assert "home_depot_5gal_orange" in registry.list_ids()


def test_from_config_loads_project_yaml(tmp_path: Path):
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "arena_profiles.yaml").write_text(
        "arena_profiles:\n"
        "  - id: example_lab_box\n"
        "    description: Imaginary lab box\n"
        "    geometry:\n"
        "      shape: circular\n"
        "      diameter_mm: 600\n"
    )
    fake_user = tmp_path / "no_user.yaml"
    registry = ArenaProfileRegistry.from_config(proj, user_yaml_path=fake_user)
    assert "example_lab_box" in registry.list_ids()


def test_from_config_user_layer_can_be_overridden_by_project(tmp_path: Path):
    user_yaml = tmp_path / "user.yaml"
    user_yaml.write_text(
        "arena_profiles:\n"
        "  - id: shared_id\n"
        "    description: User-layer description\n"
        "    geometry:\n"
        "      shape: circular\n"
        "      diameter_mm: 500\n"
    )
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "arena_profiles.yaml").write_text(
        "arena_profiles:\n"
        "  - id: shared_id\n"
        "    description: Project-layer description\n"
        "    geometry:\n"
        "      shape: circular\n"
        "      diameter_mm: 700\n"
    )
    registry = ArenaProfileRegistry.from_config(proj, user_yaml_path=user_yaml)
    profile = registry.get("shared_id")
    assert profile.description == "Project-layer description"
    assert profile.geometry.diameter_mm == 700.0


def test_from_config_no_project_path_returns_builtins_plus_user(tmp_path: Path):
    fake_user = tmp_path / "no_user.yaml"
    registry = ArenaProfileRegistry.from_config(None, user_yaml_path=fake_user)
    assert "tamco_black_bucket" in registry.list_ids()
