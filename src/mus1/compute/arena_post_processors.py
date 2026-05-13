"""Mask -> marking-shape post-processors.

A U-Net produces a class mask at 256x256 letterboxed coords. Each
arena profile interprets that mask differently — EZM extracts 4 wedge
points from the open-arm sectors; a circular bucket extracts an
ellipse boundary; a future rectangular arena would extract corners.

This module is the dispatch registry. Post-processors are registered
by string key; the active model entry in ``arena_models.yaml`` names
the key it expects. Adding a new arena type means: (1) train the
U-Net, (2) write a post-processor, (3) register it here, (4) point
``mask_to_marking`` in ``arena_models.yaml`` at the new key.

The post-processor signature is intentionally loose — each takes the
256x256 mask + letterbox metadata + an optional kwargs dict, and
returns whatever marking-shape dict the relevant pane consumes. Pure
Python; lazily imports cv2 inside individual processors when needed.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, Optional

import numpy as np


# Signature: (mask_256, letterbox_meta, **kwargs) -> Optional[dict]
PostProcessor = Callable[..., Optional[Dict[str, Any]]]


_REGISTRY: Dict[str, PostProcessor] = {}


def register(name: str, fn: PostProcessor) -> None:
    """Register a post-processor under *name*. Re-registration overwrites."""
    if not name:
        raise ValueError("post-processor name must be non-empty")
    _REGISTRY[name] = fn


def get(name: str) -> Optional[PostProcessor]:
    """Return the post-processor for *name* or ``None`` if unregistered."""
    if not name:
        return None
    return _REGISTRY.get(name)


def list_names() -> list[str]:
    """Return registered post-processor names in sorted order."""
    return sorted(_REGISTRY.keys())


# ---------------------------------------------------------------------------
# Built-in post-processors registered on module import
# ---------------------------------------------------------------------------

def _ezm_wedge_points(mask_256: np.ndarray, letterbox_meta, **kwargs) -> Optional[Dict[str, Any]]:
    """EZM open-arm → 4 wedge points. Wraps the existing implementation
    in :mod:`mus1.compute.arena_unet` so the registry stays the single
    dispatch point."""
    from mus1.compute.arena_unet import ezm_mask_to_wedge_points
    return ezm_mask_to_wedge_points(mask_256, letterbox_meta, **kwargs)


register("ezm_wedge_points", _ezm_wedge_points)


def _circular_arena_boundary(mask_256: np.ndarray, letterbox_meta, **kwargs) -> Optional[Dict[str, Any]]:
    """Circular arena → fitted ellipse boundary in original-image coords.

    Suitable for the Tamco bucket / Home Depot bucket / any
    :class:`mus1.arena_profiles.CircularGeometry` profile. Returns
    ``{"ellipse": {center_xy, axes_xy, angle_deg}, "quality": {...}}``
    or ``None`` if no foreground was found. The ``arena_class`` kwarg
    selects which class index represents the arena (default 1).
    """
    import cv2
    from mus1.compute.arena_unet import (
        _largest_cc_keep,
        _fit_outer_ellipse,
        model_xy_to_orig,
    )
    arena_class = int(kwargs.get("arena_class", 1))
    binary = (mask_256 == arena_class).astype(np.uint8)
    binary = _largest_cc_keep(binary)
    if binary.sum() == 0:
        return None
    fitted = _fit_outer_ellipse(binary)
    if fitted is None:
        return None
    (cx256, cy256), (ax256, ay256), ang_deg = fitted
    cx_orig, cy_orig = model_xy_to_orig(cx256, cy256, letterbox_meta)
    scale = letterbox_meta.pad_size / letterbox_meta.out_size
    return {
        "ellipse": {
            "center_xy": [float(cx_orig), float(cy_orig)],
            "axes_xy": [float(ax256 * scale), float(ay256 * scale)],
            "angle_deg": float(ang_deg),
        },
        "quality": {
            "arena_pixel_fraction": float(binary.mean()),
            "n_pixels": int(binary.sum()),
        },
    }


register("circular_arena_boundary", _circular_arena_boundary)
