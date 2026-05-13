"""Tests for the arena U-Net active-model registry (T8).

Covers:
  - ArenaModelRegistry.load with no file / empty / populated YAML
  - active: null entries map to "no active model"
  - missing project path returns empty registry
  - malformed YAML raises ValueError
  - relative checkpoint paths resolve against the project directory
  - post-processor registry: builtin keys present, lookup, missing key
"""
from __future__ import annotations

from pathlib import Path

import pytest

from mus1.compute.arena_models import (
    ActiveArenaModel,
    ArenaModelRegistry,
    PROJECT_MODELS_FILENAME,
)


def _write_yaml(project_path: Path, body: str) -> Path:
    p = project_path / PROJECT_MODELS_FILENAME
    p.write_text(body)
    return p


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

def test_load_with_no_yaml_returns_empty(tmp_path: Path):
    registry = ArenaModelRegistry.load(tmp_path)
    assert registry.list_profiles() == []
    assert registry.get("ezm_460mm") is None
    assert registry.is_active("ezm_460mm") is False
    assert registry.source_path is None


def test_load_with_no_project_path_returns_empty():
    registry = ArenaModelRegistry.load(None)
    assert registry.list_profiles() == []


def test_load_active_null_means_inactive(tmp_path: Path):
    _write_yaml(
        tmp_path,
        "arena_models:\n"
        "  ezm_460mm:\n"
        "    active: null\n"
        "  tamco_black_bucket:\n"
        "    active: null\n",
    )
    registry = ArenaModelRegistry.load(tmp_path)
    assert registry.list_profiles() == []


def test_load_populates_active_entry(tmp_path: Path):
    ckpt = tmp_path / "model.pt"
    ckpt.write_bytes(b"fake")
    _write_yaml(
        tmp_path,
        "arena_models:\n"
        "  ezm_460mm:\n"
        "    active:\n"
        "      run_id: r20260120\n"
        f"      checkpoint: {ckpt}\n"
        "      n_classes: 3\n"
        "      mask_to_marking: ezm_wedge_points\n"
        "      activated_at: 2026-04-15T12:00:00Z\n"
        "      notes: 'best so far'\n",
    )
    registry = ArenaModelRegistry.load(tmp_path)
    assert registry.list_profiles() == ["ezm_460mm"]
    entry = registry.get("ezm_460mm")
    assert isinstance(entry, ActiveArenaModel)
    assert entry.profile_id == "ezm_460mm"
    assert entry.run_id == "r20260120"
    assert entry.n_classes == 3
    assert entry.mask_to_marking == "ezm_wedge_points"
    assert entry.checkpoint == ckpt


def test_load_relative_checkpoint_resolves_against_workspace_root(tmp_path: Path):
    workspace = tmp_path / "ws"
    proj = workspace / "data"
    proj.mkdir(parents=True)
    ckpt_dir = workspace / "ml_workspace" / "ezm" / "active"
    ckpt_dir.mkdir(parents=True)
    ckpt = ckpt_dir / "model.pt"
    ckpt.write_bytes(b"fake")
    _write_yaml(
        proj,
        "arena_models:\n"
        "  ezm_460mm:\n"
        "    active:\n"
        "      run_id: r1\n"
        "      checkpoint: ml_workspace/ezm/active/model.pt\n"
        "      n_classes: 3\n",
    )
    registry = ArenaModelRegistry.load(proj)
    entry = registry.get("ezm_460mm")
    assert entry is not None
    assert entry.checkpoint.resolve() == ckpt.resolve()


def test_load_malformed_yaml_raises(tmp_path: Path):
    _write_yaml(tmp_path, "arena_models:\n  ezm_460mm: [not a mapping\n")
    with pytest.raises(ValueError, match="not valid YAML"):
        ArenaModelRegistry.load(tmp_path)


def test_load_arena_models_must_be_mapping(tmp_path: Path):
    _write_yaml(tmp_path, "arena_models:\n  - foo\n")
    with pytest.raises(ValueError, match="must be a mapping"):
        ArenaModelRegistry.load(tmp_path)


def test_load_active_must_be_mapping_or_null(tmp_path: Path):
    _write_yaml(
        tmp_path,
        "arena_models:\n  ezm_460mm:\n    active: yes\n",
    )
    with pytest.raises(ValueError, match="must be a mapping or null"):
        ArenaModelRegistry.load(tmp_path)


def test_load_requires_run_id_and_checkpoint(tmp_path: Path):
    _write_yaml(
        tmp_path,
        "arena_models:\n"
        "  ezm_460mm:\n"
        "    active:\n"
        "      run_id: r1\n",  # checkpoint missing
    )
    with pytest.raises(ValueError, match="run_id and checkpoint"):
        ArenaModelRegistry.load(tmp_path)


# ---------------------------------------------------------------------------
# Post-processor registry
# ---------------------------------------------------------------------------

def test_post_processor_registry_has_builtins():
    from mus1.compute.arena_post_processors import list_names, get

    names = list_names()
    assert "ezm_wedge_points" in names
    assert "circular_arena_boundary" in names

    assert get("ezm_wedge_points") is not None
    assert get("circular_arena_boundary") is not None


def test_post_processor_unknown_returns_none():
    from mus1.compute.arena_post_processors import get
    assert get("does_not_exist") is None
    assert get("") is None


def test_post_processor_register_overwrites():
    from mus1.compute.arena_post_processors import register, get

    sentinel = lambda mask, meta, **kw: {"sentinel": True}
    register("test_overwrite_processor", sentinel)
    assert get("test_overwrite_processor") is sentinel


def test_post_processor_register_rejects_empty_name():
    from mus1.compute.arena_post_processors import register
    with pytest.raises(ValueError):
        register("", lambda *_a, **_kw: None)


def test_run_post_processor_dispatches():
    """The arena_unet.run_post_processor dispatcher hits the registry."""
    import numpy as np
    from mus1.compute import arena_post_processors
    from mus1.compute.arena_unet import LetterboxMeta, run_post_processor

    arena_post_processors.register(
        "test_dispatch_processor",
        lambda mask, meta, **kw: {"hit": True, "kwargs": kw},
    )
    meta = LetterboxMeta(src_h=10, src_w=10, pad_top=0, pad_left=0, pad_size=10)
    result = run_post_processor(
        "test_dispatch_processor",
        np.zeros((4, 4), dtype=np.uint8),
        meta,
        my_kwarg="ok",
    )
    assert result == {"hit": True, "kwargs": {"my_kwarg": "ok"}}


def test_run_post_processor_unknown_raises():
    import numpy as np
    from mus1.compute.arena_unet import LetterboxMeta, run_post_processor
    meta = LetterboxMeta(src_h=10, src_w=10, pad_top=0, pad_left=0, pad_size=10)
    with pytest.raises(KeyError, match="unknown arena post-processor"):
        run_post_processor("does_not_exist", np.zeros((4, 4), dtype=np.uint8), meta)


# ---------------------------------------------------------------------------
# load_arena_unet error paths (don't need actual torch/checkpoint to test these)
# ---------------------------------------------------------------------------

def test_load_arena_unet_unknown_profile_raises(tmp_path: Path):
    from mus1.compute.arena_unet import load_arena_unet
    # No arena_models.yaml at all
    with pytest.raises(LookupError, match="no active arena U-Net"):
        load_arena_unet("ezm_460mm", tmp_path)


def test_load_arena_unet_missing_checkpoint_raises(tmp_path: Path):
    from mus1.compute.arena_unet import load_arena_unet

    _write_yaml(
        tmp_path,
        "arena_models:\n"
        "  ezm_460mm:\n"
        "    active:\n"
        "      run_id: r1\n"
        "      checkpoint: /nonexistent/model.pt\n"
        "      n_classes: 3\n",
    )
    with pytest.raises(FileNotFoundError, match="checkpoint missing"):
        load_arena_unet("ezm_460mm", tmp_path)


def test_model_run_id_empty_for_legacy_loaded_model():
    """Legacy load_ezm_unet doesn't tag the model — model_run_id returns ''."""
    from mus1.compute.arena_unet import model_run_id

    class FakeModel:
        pass

    assert model_run_id(FakeModel()) == ""


# ---------------------------------------------------------------------------
# write_active / clear_active (T11)
# ---------------------------------------------------------------------------

def test_write_active_creates_yaml_when_absent(tmp_path: Path):
    ckpt = tmp_path / "model.pt"
    ckpt.write_bytes(b"fake")
    yaml_path = ArenaModelRegistry.write_active(
        tmp_path,
        profile_id="ezm_460mm",
        run_id="r20260601",
        checkpoint=ckpt,
        mask_to_marking="ezm_wedge_points",
        notes="first run",
    )
    assert yaml_path.is_file()
    reg = ArenaModelRegistry.load(tmp_path)
    entry = reg.get("ezm_460mm")
    assert entry is not None
    assert entry.run_id == "r20260601"
    assert entry.mask_to_marking == "ezm_wedge_points"
    assert entry.notes == "first run"


def test_write_active_preserves_other_profiles(tmp_path: Path):
    ckpt1 = tmp_path / "m1.pt"; ckpt1.write_bytes(b"a")
    ckpt2 = tmp_path / "m2.pt"; ckpt2.write_bytes(b"b")
    ArenaModelRegistry.write_active(
        tmp_path, profile_id="ezm_460mm", run_id="ezm-r1", checkpoint=ckpt1,
    )
    ArenaModelRegistry.write_active(
        tmp_path, profile_id="tamco_black_bucket", run_id="tamco-r1", checkpoint=ckpt2,
    )
    reg = ArenaModelRegistry.load(tmp_path)
    assert reg.get("ezm_460mm").run_id == "ezm-r1"
    assert reg.get("tamco_black_bucket").run_id == "tamco-r1"


def test_write_active_overwrites_same_profile(tmp_path: Path):
    ckpt1 = tmp_path / "m1.pt"; ckpt1.write_bytes(b"a")
    ckpt2 = tmp_path / "m2.pt"; ckpt2.write_bytes(b"b")
    ArenaModelRegistry.write_active(
        tmp_path, profile_id="ezm_460mm", run_id="r1", checkpoint=ckpt1,
    )
    ArenaModelRegistry.write_active(
        tmp_path, profile_id="ezm_460mm", run_id="r2", checkpoint=ckpt2,
    )
    reg = ArenaModelRegistry.load(tmp_path)
    entry = reg.get("ezm_460mm")
    assert entry.run_id == "r2"
    assert str(entry.checkpoint).endswith("m2.pt")


def test_write_active_rejects_missing_checkpoint(tmp_path: Path):
    with pytest.raises(FileNotFoundError, match="checkpoint not found"):
        ArenaModelRegistry.write_active(
            tmp_path,
            profile_id="ezm_460mm",
            run_id="r1",
            checkpoint=tmp_path / "does_not_exist.pt",
        )


def test_clear_active_sets_null(tmp_path: Path):
    ckpt = tmp_path / "model.pt"
    ckpt.write_bytes(b"x")
    ArenaModelRegistry.write_active(
        tmp_path, profile_id="ezm_460mm", run_id="r1", checkpoint=ckpt,
    )
    ArenaModelRegistry.clear_active(tmp_path, profile_id="ezm_460mm")
    reg = ArenaModelRegistry.load(tmp_path)
    assert reg.get("ezm_460mm") is None


def test_clear_active_is_noop_when_no_yaml(tmp_path: Path):
    # Should not raise and should not create the file
    result = ArenaModelRegistry.clear_active(tmp_path, profile_id="ezm_460mm")
    assert result is None
