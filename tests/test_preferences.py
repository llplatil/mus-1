"""Tests for ``mus1.preferences``.

Covers:
  - default_preferences match documented project convention (bio → t1small)
  - load_preferences() with no files returns defaults
  - user-level YAML overrides defaults
  - project-level YAML overrides user-level
  - malformed YAML raises ValueError (does not silently fall back)
  - write_default_user_preferences() seeds a file but does not clobber existing
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from mus1.preferences import (
    DEFAULT_USER_PREFS_PATH,
    PROJECT_PREFS_FILENAME,
    Preferences,
    default_preferences,
    load_preferences,
    write_default_user_preferences,
)


def test_default_preferences_match_project_convention():
    p = default_preferences()
    parts = p.cluster.partitions
    assert [x.name for x in parts] == ["bio", "t1small"]
    assert parts[0].role == "primary"
    assert parts[0].prefer_idle_nodes is True
    assert parts[0].max_jobs_per_node == 1
    assert parts[1].role == "overflow"
    primary = p.cluster.primary()
    assert primary is not None and primary.name == "bio"
    overflow = p.cluster.overflow()
    assert [x.name for x in overflow] == ["t1small"]


def test_load_with_no_files_returns_defaults(tmp_path: Path):
    # No user or project file exists in tmp_path → defaults
    prefs = load_preferences(
        project_path=tmp_path,
        user_path=tmp_path / "no_such_file.yaml",
    )
    assert isinstance(prefs, Preferences)
    assert prefs.cluster.primary().name == "bio"
    assert prefs.compute.tracking_confidence.pcutoff == 0.6


def test_user_level_override_applied(tmp_path: Path):
    user_file = tmp_path / "preferences.yaml"
    user_file.write_text(yaml.safe_dump({
        "compute": {
            "tracking_confidence": {
                "pcutoff": 0.7,
                "overall_frac_threshold": 0.85,
            },
        },
    }))
    prefs = load_preferences(project_path=tmp_path, user_path=user_file)
    tc = prefs.compute.tracking_confidence
    assert tc.pcutoff == 0.7
    assert tc.overall_frac_threshold == 0.85
    # Unchanged keys stay at default
    assert tc.bodypart_frac_threshold == 0.5


def test_project_level_overrides_user_level(tmp_path: Path):
    user_file = tmp_path / "user_prefs.yaml"
    user_file.write_text(yaml.safe_dump({
        "compute": {"tracking_confidence": {"pcutoff": 0.7}},
    }))
    proj_dir = tmp_path / "data"
    proj_dir.mkdir()
    proj_file = proj_dir / PROJECT_PREFS_FILENAME
    proj_file.write_text(yaml.safe_dump({
        "compute": {"tracking_confidence": {"pcutoff": 0.9}},
    }))
    prefs = load_preferences(project_path=tmp_path, user_path=user_file)
    assert prefs.compute.tracking_confidence.pcutoff == 0.9


def test_cluster_override_replaces_partition_list(tmp_path: Path):
    user_file = tmp_path / "preferences.yaml"
    user_file.write_text(yaml.safe_dump({
        "cluster": {
            "partitions": [
                {"name": "gpu", "max_jobs_per_node": 1, "role": "primary"},
            ],
        },
    }))
    prefs = load_preferences(project_path=tmp_path, user_path=user_file)
    assert [x.name for x in prefs.cluster.partitions] == ["gpu"]
    assert prefs.cluster.primary().name == "gpu"
    assert prefs.cluster.overflow() == []


def test_malformed_yaml_raises(tmp_path: Path):
    user_file = tmp_path / "bad.yaml"
    user_file.write_text("cluster: [unterminated")
    with pytest.raises(ValueError, match="not valid YAML"):
        load_preferences(project_path=tmp_path, user_path=user_file)


def test_non_mapping_yaml_raises(tmp_path: Path):
    user_file = tmp_path / "list.yaml"
    user_file.write_text("- just\n- a\n- list\n")
    with pytest.raises(ValueError, match="must contain a mapping"):
        load_preferences(project_path=tmp_path, user_path=user_file)


def test_write_default_seeds_when_missing(tmp_path: Path):
    target = tmp_path / "config" / "preferences.yaml"
    written = write_default_user_preferences(target)
    assert written == target
    assert target.is_file()
    content = yaml.safe_load(target.read_text())
    assert "cluster" in content
    assert content["cluster"]["partitions"][0]["name"] == "bio"


def test_write_default_does_not_clobber_existing(tmp_path: Path):
    target = tmp_path / "preferences.yaml"
    target.write_text("# existing content\ncluster: {partitions: []}\n")
    write_default_user_preferences(target)
    # File still has the original content
    assert target.read_text().startswith("# existing content")
