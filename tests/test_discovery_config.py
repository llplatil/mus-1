"""Tests for config-driven discovery roots (T1).

Exercises the ``[paths] data_roots`` override in ``mus1.toml`` plus the
default-list fallback when the file is absent or the key unset.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from mus1.web.discovery import (
    DEFAULT_DATA_ROOTS,
    PROJECT_CONFIG_FILENAME,
    get_configured_data_root_names,
    get_data_roots,
)


def _write_toml(project_path: Path, body: str) -> None:
    (project_path / PROJECT_CONFIG_FILENAME).write_text(body)


# ---------------------------------------------------------------------------
# get_configured_data_root_names
# ---------------------------------------------------------------------------

def test_returns_defaults_when_no_config(tmp_path: Path):
    names, source = get_configured_data_root_names(tmp_path)
    assert names == DEFAULT_DATA_ROOTS
    assert source == "default"


def test_returns_defaults_when_paths_section_absent(tmp_path: Path):
    _write_toml(tmp_path, '[unrelated]\nfoo = "bar"\n')
    names, source = get_configured_data_root_names(tmp_path)
    assert names == DEFAULT_DATA_ROOTS
    assert source == "default"


def test_returns_defaults_when_data_roots_key_absent(tmp_path: Path):
    _write_toml(tmp_path, '[paths]\nother = "x"\n')
    names, source = get_configured_data_root_names(tmp_path)
    assert names == DEFAULT_DATA_ROOTS
    assert source == "default"


def test_reads_data_roots_from_config(tmp_path: Path):
    _write_toml(
        tmp_path,
        '[paths]\ndata_roots = ["experiment_data", "external_lab_data"]\n',
    )
    names, source = get_configured_data_root_names(tmp_path)
    assert names == ("experiment_data", "external_lab_data")
    assert source == "config"


def test_config_override_preserves_caller_order(tmp_path: Path):
    """Order matters: first root containing an experiment id wins."""
    _write_toml(
        tmp_path,
        '[paths]\ndata_roots = ["pilot_data", "experiment_data", "validation_data"]\n',
    )
    names, _ = get_configured_data_root_names(tmp_path)
    assert names == ("pilot_data", "experiment_data", "validation_data")


def test_malformed_toml_raises(tmp_path: Path):
    _write_toml(tmp_path, "this is = not [valid\n")
    with pytest.raises(ValueError, match="not valid TOML"):
        get_configured_data_root_names(tmp_path)


def test_data_roots_must_be_list_of_nonempty_strings(tmp_path: Path):
    _write_toml(tmp_path, '[paths]\ndata_roots = "experiment_data"\n')
    with pytest.raises(ValueError, match="must be a list"):
        get_configured_data_root_names(tmp_path)

    _write_toml(tmp_path, '[paths]\ndata_roots = ["", "experiment_data"]\n')
    with pytest.raises(ValueError, match="must be a list"):
        get_configured_data_root_names(tmp_path)


# ---------------------------------------------------------------------------
# get_data_roots — filesystem filter
# ---------------------------------------------------------------------------

def test_get_data_roots_filters_to_existing_dirs(tmp_path: Path):
    (tmp_path / "experiment_data").mkdir()
    # validation_data and pilot_data don't exist
    out = get_data_roots(tmp_path)
    assert out == [(tmp_path / "experiment_data").resolve()]


def test_get_data_roots_picks_up_configured_extra_root(tmp_path: Path):
    (tmp_path / "experiment_data").mkdir()
    (tmp_path / "external_lab_data").mkdir()
    _write_toml(
        tmp_path,
        '[paths]\ndata_roots = ["experiment_data", "external_lab_data"]\n',
    )
    out = get_data_roots(tmp_path)
    assert out == [
        (tmp_path / "experiment_data").resolve(),
        (tmp_path / "external_lab_data").resolve(),
    ]


def test_get_data_roots_preserves_config_order(tmp_path: Path):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    _write_toml(tmp_path, '[paths]\ndata_roots = ["b", "a"]\n')
    out = get_data_roots(tmp_path)
    assert [p.name for p in out] == ["b", "a"]


def test_get_data_roots_dedupes(tmp_path: Path):
    (tmp_path / "experiment_data").mkdir()
    _write_toml(
        tmp_path,
        '[paths]\ndata_roots = ["experiment_data", "experiment_data"]\n',
    )
    out = get_data_roots(tmp_path)
    assert len(out) == 1


# ---------------------------------------------------------------------------
# DEFAULT_DATA_ROOTS contract
# ---------------------------------------------------------------------------

def test_pilot_data_in_default_roots():
    """T6 (pilot restructure) depends on pilot_data being a default root."""
    assert "pilot_data" in DEFAULT_DATA_ROOTS


def test_publication_validation_pilot_default_order():
    """Publication > validation > pilot — first root with an id wins."""
    idx = {n: i for i, n in enumerate(DEFAULT_DATA_ROOTS)}
    assert idx["experiment_data"] < idx["validation_data"] < idx["pilot_data"]
