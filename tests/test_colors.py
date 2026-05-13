"""Tests for the canonical color palette in ``mus1.compute.colors``.

T12: Canonical EZM/arena overlay palette. These tests pin the contract so
every overlay code path (web/ezm_masks, compute/overlay, future arena
inference panes) sees the same green/blue identity.
"""
from __future__ import annotations

import numpy as np
import pytest

from mus1.compute import colors


def test_canonical_palette_pinned_values():
    """The published palette is a public contract — pin every constant."""
    assert colors.OPEN == (0, 200, 0)
    assert colors.CLOSED == (80, 80, 255)
    assert colors.WEDGE_POINT == (0, 255, 0)
    assert colors.DELTA_TINT == (255, 80, 255)
    assert colors.CORRECTED == colors.DELTA_TINT
    assert colors.HIGHLIGHT_DOT == (255, 60, 60)


def test_predicted_overlays_are_alpha_aware():
    assert colors.PREDICTED_OPEN[:3] == colors.OPEN
    assert colors.PREDICTED_CLOSED[:3] == colors.CLOSED
    assert 0.0 < colors.PREDICTED_OPEN[3] <= 1.0
    assert 0.0 < colors.PREDICTED_CLOSED[3] <= 1.0


def test_default_alphas_in_unit_range():
    for alpha in (
        colors.GT_OVERLAY_ALPHA,
        colors.PREDICTED_OVERLAY_ALPHA,
        colors.ZONE_SECTOR_ALPHA,
    ):
        assert 0.0 < alpha <= 1.0


def test_open_and_closed_distinguishable_under_visualization():
    """Sanity: green and blue should be perceptually distinct.

    Trivial check that the two channels with peak intensity differ — guards
    against accidental future "make them both green" regressions.
    """
    open_rgb = np.array(colors.OPEN, dtype=int)
    closed_rgb = np.array(colors.CLOSED, dtype=int)
    assert int(np.argmax(open_rgb)) != int(np.argmax(closed_rgb))


def test_blend_mask_overlay_uses_canonical_palette():
    """``blend_mask_overlay`` must paint open=green, closed=blue (T12)."""
    cv2 = pytest.importorskip("cv2")
    from mus1.web.ezm_masks import blend_mask_overlay

    h, w = 4, 4
    frame = np.zeros((h, w, 3), dtype=np.uint8)
    mask = np.zeros((h, w), dtype=np.uint8)
    mask[0, 0] = 1  # open
    mask[0, 1] = 2  # closed

    out = blend_mask_overlay(frame, mask)

    # Open pixel should be more green than red or blue
    open_pix = out[0, 0]
    assert open_pix[1] > open_pix[0]
    assert open_pix[1] > open_pix[2]
    # Closed pixel should be more blue than red or green
    closed_pix = out[0, 1]
    assert closed_pix[2] > closed_pix[0]
    assert closed_pix[2] > closed_pix[1]
    # Background untouched (still zeros)
    assert tuple(out[3, 3]) == (0, 0, 0)


def test_no_yellow_in_ezm_mask_overlay():
    """Regression guard for T12: the old yellow open tint is gone."""
    cv2 = pytest.importorskip("cv2")
    from mus1.web.ezm_masks import blend_mask_overlay

    frame = np.zeros((2, 2, 3), dtype=np.uint8)
    mask = np.array([[1, 1], [1, 1]], dtype=np.uint8)  # all-open
    out = blend_mask_overlay(frame, mask)
    # Yellow would be (R high, G high, B low). Canonical green has R=0.
    for px in out.reshape(-1, 3):
        assert not (px[0] > 100 and px[1] > 100 and px[2] < 50), \
            f"yellow-like pixel detected: {tuple(px)}"
