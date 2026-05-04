"""Tests for ``mus1.paths`` mount-alias normalization."""
from __future__ import annotations

from pathlib import Path

import pytest

from mus1.paths import mount_alias_variants, resolve_with_mount_aliases


def test_variants_swap_center1_to_import_c1():
    out = mount_alias_variants("/center1/WDMOSEQ2/llplatil/WDMOSEQ2/data/foo.mp4")
    assert out == [
        "/center1/WDMOSEQ2/llplatil/WDMOSEQ2/data/foo.mp4",
        "/import/c1/WDMOSEQ2/llplatil/WDMOSEQ2/data/foo.mp4",
    ]


def test_variants_swap_import_c1_to_center1():
    out = mount_alias_variants("/import/c1/WDMOSEQ2/llplatil/WDMOSEQ2/data/foo.mp4")
    assert out == [
        "/import/c1/WDMOSEQ2/llplatil/WDMOSEQ2/data/foo.mp4",
        "/center1/WDMOSEQ2/llplatil/WDMOSEQ2/data/foo.mp4",
    ]


def test_variants_no_alias_for_unrelated_path():
    out = mount_alias_variants("/tmp/something/else.mp4")
    assert out == ["/tmp/something/else.mp4"]


def test_resolve_returns_existing_primary(tmp_path: Path):
    real = tmp_path / "exists.txt"
    real.write_text("hi")
    res = resolve_with_mount_aliases(str(real))
    assert res == real


def test_resolve_returns_none_when_no_variant_exists():
    assert resolve_with_mount_aliases("/center1/definitely/not/here.mp4") is None


def test_resolve_handles_none_and_empty():
    assert resolve_with_mount_aliases(None) is None
    assert resolve_with_mount_aliases("") is None
    assert resolve_with_mount_aliases("   ") is None


def test_resolve_finds_alias_when_primary_missing():
    """If a /center1 path doesn't exist but /import/c1 does (real on this
    cluster), the resolver returns the working form. Skip if neither
    mount is present in the test environment.
    """
    real_center = Path("/center1/WDMOSEQ2/llplatil/WDMOSEQ2/CLAUDE.md")
    real_import = Path("/import/c1/WDMOSEQ2/llplatil/WDMOSEQ2/CLAUDE.md")
    if not (real_center.exists() or real_import.exists()):
        pytest.skip("neither cluster mount present")
    # Try the form that's *less* likely to be primary on this node:
    resolved = resolve_with_mount_aliases(
        "/center1/WDMOSEQ2/llplatil/WDMOSEQ2/CLAUDE.md")
    assert resolved is not None
    assert resolved.exists()
    assert resolved.name == "CLAUDE.md"


def test_variants_dedupes_when_no_swap_applies():
    # Path that doesn't match either prefix should return single entry
    out = mount_alias_variants("./relative/path.mp4")
    assert out == ["./relative/path.mp4"]


def test_pathlib_input_accepted():
    out = mount_alias_variants(Path("/center1/foo"))
    assert "/import/c1/foo" in out
