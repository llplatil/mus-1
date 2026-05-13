"""Canonical color palette for arena/zone overlays (RGB).

Single source of truth for any pane that renders ground-truth, predicted, or
delta overlays on EZM, NOR/NOF, or future arena types. Adopted from the
EZM Wedge Marking palette so a reviewer comparing GT vs. prediction sees the
same green/blue regardless of pane.

All values are RGB; cv2 callers that expect BGR must convert at the boundary.

Adopted in T12 (ROADMAP Iteration 6a). Yellow is intentionally absent from
EZM mask overlays — yellow is reserved for the *temporal* trajectory gradient
(cyan → green → yellow), which is unrelated to zone classification.
"""
from __future__ import annotations

from typing import Tuple

# RGB triples
RGB = Tuple[int, int, int]
RGBA = Tuple[int, int, int, float]


# ---------------------------------------------------------------------------
# Zone classification (ground truth)
# ---------------------------------------------------------------------------

OPEN: RGB = (0, 200, 0)            # green — open arm / open region
CLOSED: RGB = (80, 80, 255)        # blue  — closed arm / closed region
WEDGE_POINT: RGB = (0, 255, 0)     # bright green — wedge marker on canvas


# ---------------------------------------------------------------------------
# Predicted overlays (U-Net inference)
# ---------------------------------------------------------------------------
# Same hues as GT, with an alpha component so they overlay distinctly.

PREDICTED_OPEN: RGBA = (0, 200, 0, 0.45)
PREDICTED_CLOSED: RGBA = (80, 80, 255, 0.45)


# ---------------------------------------------------------------------------
# Special-purpose
# ---------------------------------------------------------------------------

DELTA_TINT: RGB = (255, 80, 255)   # magenta — predicted ≠ GT, "look here"
CORRECTED: RGB = (255, 80, 255)    # alias: same magenta marks corrected frames

HIGHLIGHT_DOT: RGB = (255, 60, 60)  # red — current-frame marker (non-corrected)


# ---------------------------------------------------------------------------
# Default blend alphas
# ---------------------------------------------------------------------------

GT_OVERLAY_ALPHA: float = 0.30
PREDICTED_OVERLAY_ALPHA: float = 0.45
ZONE_SECTOR_ALPHA: float = 0.18
