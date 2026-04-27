#!/usr/bin/env python3
"""
Reusable EZM geometry helpers (no UI).

This module is backend-agnostic: it can be used by Streamlit, notebooks, or CLI tools.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

import numpy as np


TAU = 2.0 * math.pi


@dataclass(frozen=True)
class EllipseParams:
    """OpenCV-style ellipse parameters."""

    center_xy: Tuple[float, float]  # (cx, cy)
    axes_xy: Tuple[float, float]  # (major_diameter, minor_diameter)
    angle_deg: float

    @property
    def a(self) -> float:
        return float(self.axes_xy[0]) / 2.0

    @property
    def b(self) -> float:
        return float(self.axes_xy[1]) / 2.0

    @property
    def angle_rad(self) -> float:
        return math.radians(float(self.angle_deg))


@dataclass(frozen=True)
class EZMZones:
    """
    Elliptical annulus + open-arm angular ranges (2 out of 4 sectors).

    Angles are radians in [0, 2π).
    """

    outer_ellipse: EllipseParams
    r_inner: float
    open_angle_ranges: Tuple[Tuple[float, float], Tuple[float, float]]
    boundary_angles: Tuple[float, float, float, float]  # sorted
    version: str = "ezm_open_closed_v2"


def wrap_angle(theta: np.ndarray) -> np.ndarray:
    return np.mod(theta, TAU)


def _rotation_matrix(angle_rad: float) -> np.ndarray:
    c = math.cos(angle_rad)
    s = math.sin(angle_rad)
    return np.array([[c, -s], [s, c]], dtype=float)


def normalize_xy_to_unit_circle(x: np.ndarray, y: np.ndarray, outer: EllipseParams) -> Tuple[np.ndarray, np.ndarray]:
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)

    cx, cy = outer.center_xy
    pts = np.stack([x - cx, y - cy], axis=0)
    R = _rotation_matrix(-outer.angle_rad)
    rot = R @ pts

    a = outer.a if outer.a > 0 else np.nan
    b = outer.b if outer.b > 0 else np.nan
    return rot[0, :] / a, rot[1, :] / b


def compute_r_theta(x: np.ndarray, y: np.ndarray, outer: EllipseParams) -> Tuple[np.ndarray, np.ndarray]:
    xn, yn = normalize_xy_to_unit_circle(x, y, outer)
    r = np.sqrt(xn * xn + yn * yn)
    theta = wrap_angle(np.arctan2(yn, xn))
    return r, theta


def open_ranges_from_boundary_angles(
    boundary_angles_sorted: Sequence[float], open_sectors: Sequence[int]
) -> Tuple[Tuple[float, float], Tuple[float, float]]:
    angles = [float(a) % TAU for a in boundary_angles_sorted]
    if len(angles) != 4:
        raise ValueError("Expected 4 boundary angles")
    open_sectors = list(open_sectors)
    if len(open_sectors) != 2:
        raise ValueError("Expected exactly 2 open sectors (indices 0-3)")
    ranges = []
    for sidx in open_sectors:
        sidx = int(sidx)
        start = angles[sidx]
        end = angles[(sidx + 1) % 4]
        ranges.append((start, end))
    return (ranges[0], ranges[1])


def _shorter_arc_midpoint(a: float, b: float) -> float:
    """Midpoint angle of the shorter arc between two angles in [0, TAU)."""
    a = float(a) % TAU
    b = float(b) % TAU
    diff = (b - a) % TAU
    if diff <= math.pi:
        return (a + diff / 2.0) % TAU
    return (b + (TAU - diff) / 2.0) % TAU


def ellipse_point_from_theta(
    theta: float, outer: EllipseParams, scale: float = 1.0
) -> Tuple[float, float]:
    """Map a normalized-space angle to image coordinates on the ellipse boundary.

    *scale* multiplies the semi-axes (e.g. ``r_inner`` for the inner boundary).
    """
    a = outer.a * scale
    b = outer.b * scale
    ang = outer.angle_rad
    x0 = a * math.cos(float(theta))
    y0 = b * math.sin(float(theta))
    xr = x0 * math.cos(ang) - y0 * math.sin(ang)
    yr = x0 * math.sin(ang) + y0 * math.cos(ang)
    cx, cy = outer.center_xy
    return float(xr + cx), float(yr + cy)


def _scalar_angle_in_sector(theta: float, start: float, end: float) -> bool:
    """Check if scalar angle is within the sector [start, end) going counter-clockwise."""
    theta = float(theta) % TAU
    start = float(start) % TAU
    end = float(end) % TAU
    if start <= end:
        return start <= theta < end
    return theta >= start or theta < end


def boundary_angles_from_wedge_points(
    wedge1_pts: List[Tuple[float, float]],
    wedge2_pts: List[Tuple[float, float]],
    center_xy: Tuple[float, float],
    outer: EllipseParams,
) -> Tuple[List[float], List[int], str]:
    """
    Compute boundary angles and open sector indices from wedge border points.

    For each open wedge, the user clicks 2 points on the outer track (left and
    right borders of the open arm).  A radial center is provided (typically the
    ellipse center, optionally adjusted).  Each border point is projected to an
    angle using the supplied ``center_xy`` as the origin for angle computation,
    while preserving the ellipse's axis scaling for proper normalisation.

    The 4 resulting angles are sorted.  The two *open* sectors are identified by
    checking which of the 4 sectors contains the midpoint angle of each wedge's
    border pair (shorter arc bisector).  If detection is ambiguous, the function
    falls back to an opposite-sector heuristic (EZM arms are always ~180deg apart).

    Parameters
    ----------
    wedge1_pts : list of 2 (x, y) tuples
        Border points for open wedge 1 (image pixel coords).
    wedge2_pts : list of 2 (x, y) tuples
        Border points for open wedge 2 (image pixel coords).
    center_xy : (cx, cy)
        Radial center used for angle computation (image pixel coords).
        Usually the outer ellipse centre but may be user-adjusted.
    outer : EllipseParams
        The fitted outer ellipse (used for axis scaling and rotation).

    Returns
    -------
    boundary_angles : list of 4 floats
        Sorted boundary angles in [0, TAU).
    open_sectors : list of 2 ints
        Indices (0-3) of the sectors that are open arms.
    warning : str
        Empty string if detection was clean, otherwise a warning message.
    """
    # Use center_xy for angle computation by creating a shifted ellipse
    eff_outer = EllipseParams(
        center_xy=center_xy,
        axes_xy=outer.axes_xy,
        angle_deg=outer.angle_deg,
    )

    all_pts_x = np.array([p[0] for p in wedge1_pts] + [p[0] for p in wedge2_pts], dtype=float)
    all_pts_y = np.array([p[1] for p in wedge1_pts] + [p[1] for p in wedge2_pts], dtype=float)
    _, thetas = compute_r_theta(all_pts_x, all_pts_y, eff_outer)

    w1_thetas = (float(thetas[0]), float(thetas[1]))
    w2_thetas = (float(thetas[2]), float(thetas[3]))

    sorted_angles = sorted(float(t) % TAU for t in thetas)

    w1_mid = _shorter_arc_midpoint(w1_thetas[0], w1_thetas[1])
    w2_mid = _shorter_arc_midpoint(w2_thetas[0], w2_thetas[1])

    open_sectors: List[int] = []
    for sidx in range(4):
        s_start = sorted_angles[sidx]
        s_end = sorted_angles[(sidx + 1) % 4]
        if _scalar_angle_in_sector(w1_mid, s_start, s_end) or _scalar_angle_in_sector(w2_mid, s_start, s_end):
            open_sectors.append(sidx)

    warning = ""

    if len(open_sectors) != 2:
        # Fallback: opposite-sector heuristic (EZM open arms are ~180deg apart)
        # Find the pair of opposite sectors (0,2) or (1,3) whose midpoint angles
        # are closest to 180deg apart
        best_pair = [0, 2]
        best_score = float("inf")
        for pair in ([0, 2], [1, 3]):
            mid0 = _shorter_arc_midpoint(sorted_angles[pair[0]], sorted_angles[(pair[0] + 1) % 4])
            mid1 = _shorter_arc_midpoint(sorted_angles[pair[1]], sorted_angles[(pair[1] + 1) % 4])
            sep = abs(((mid1 - mid0) % TAU) - math.pi)
            if sep < best_score:
                best_score = sep
                best_pair = pair
        open_sectors = best_pair
        warning = (
            f"Could not unambiguously detect open sectors from wedge midpoints. "
            f"Using opposite-sector heuristic: sectors {open_sectors}. "
            f"Verify the preview overlay is correct."
        )
    else:
        # Validate: open sectors should be approximately opposite (~180deg apart)
        mid0 = _shorter_arc_midpoint(sorted_angles[open_sectors[0]], sorted_angles[(open_sectors[0] + 1) % 4])
        mid1 = _shorter_arc_midpoint(sorted_angles[open_sectors[1]], sorted_angles[(open_sectors[1] + 1) % 4])
        separation = abs(((mid1 - mid0) % TAU) - math.pi)
        if separation > math.radians(45):
            warning = (
                f"Detected open sectors {open_sectors} are not opposite "
                f"(angular separation {math.degrees(math.pi - separation + math.pi):.0f}° "
                f"instead of ~180°). EZM open arms should be roughly opposite. "
                f"Check your border point placement."
            )

    return sorted_angles, open_sectors, warning


def fit_circle_from_points(
    points: List[Tuple[float, float]],
) -> Tuple[float, float, float]:
    """Algebraic circle fit (Kasa method) from 3+ points.

    Solves  x² + y² + Dx + Ey + F = 0  via least-squares.
    Returns (cx, cy, radius).
    """
    pts = np.array(points, dtype=float)
    x, y = pts[:, 0], pts[:, 1]
    A = np.column_stack([x, y, np.ones(len(x))])
    b = -(x ** 2 + y ** 2)
    result, *_ = np.linalg.lstsq(A, b, rcond=None)
    D, E, F = result
    cx = -D / 2.0
    cy = -E / 2.0
    r = math.sqrt(cx * cx + cy * cy - F)
    return cx, cy, r


def zones_from_wedge_points(
    points: List[Tuple[float, float]],
    inner_ratio: float = 0.761,
) -> Tuple[EZMZones, str]:
    """Build EZMZones from 4 wedge border points using circle fit.

    Open sectors determined by hardcoded orientation:
    top/bottom = open (vertical), left/right = closed (horizontal).

    Returns (zones, warning_str).
    """
    cx, cy, r = fit_circle_from_points(points)
    diameter = 2.0 * r
    outer = EllipseParams(
        center_xy=(cx, cy),
        axes_xy=(diameter, diameter),
        angle_deg=0.0,
    )

    # Compute boundary angles of the 4 points in normalized space
    pts_x = np.array([p[0] for p in points], dtype=float)
    pts_y = np.array([p[1] for p in points], dtype=float)
    _, thetas = compute_r_theta(pts_x, pts_y, outer)
    sorted_angles = sorted(float(t) % TAU for t in thetas)

    # Determine open sectors: midpoint direction more vertical = open
    open_sectors: List[int] = []
    for sidx in range(4):
        mid = _shorter_arc_midpoint(sorted_angles[sidx], sorted_angles[(sidx + 1) % 4])
        # For a circle with angle_deg=0, normalized θ maps directly to image direction.
        # |sin(θ)| > |cos(θ)| means the sector points up or down (vertical = open).
        if abs(math.sin(mid)) > abs(math.cos(mid)):
            open_sectors.append(sidx)

    warning = ""
    if len(open_sectors) != 2:
        # Fallback: pick opposite pair whose midpoints are most vertical
        best_pair = [0, 2]
        best_vert = -1.0
        for pair in ([0, 2], [1, 3]):
            mid0 = _shorter_arc_midpoint(sorted_angles[pair[0]], sorted_angles[(pair[0] + 1) % 4])
            mid1 = _shorter_arc_midpoint(sorted_angles[pair[1]], sorted_angles[(pair[1] + 1) % 4])
            vert = abs(math.sin(mid0)) + abs(math.sin(mid1))
            if vert > best_vert:
                best_vert = vert
                best_pair = pair
        open_sectors = best_pair
        warning = (
            f"Ambiguous sector orientation. Using most-vertical pair: sectors {open_sectors}. "
            f"Verify the overlay is correct."
        )

    open_ranges = open_ranges_from_boundary_angles(sorted_angles, open_sectors)

    zones = EZMZones(
        outer_ellipse=outer,
        r_inner=inner_ratio,
        open_angle_ranges=open_ranges,
        boundary_angles=tuple(sorted_angles),  # type: ignore[arg-type]
    )
    return zones, warning


def zones_to_json(z: EZMZones, image_wh: Tuple[int, int], params: Dict[str, Any], notes: str = "") -> Dict[str, Any]:
    w, h = int(image_wh[0]), int(image_wh[1])
    return {
        "version": z.version,
        "image": {"width": w, "height": h},
        "outer_ellipse": {
            "center": [float(z.outer_ellipse.center_xy[0]), float(z.outer_ellipse.center_xy[1])],
            "axes": [float(z.outer_ellipse.axes_xy[0]), float(z.outer_ellipse.axes_xy[1])],
            "angle_deg": float(z.outer_ellipse.angle_deg),
        },
        "r_inner": float(z.r_inner),
        "boundary_angles": [float(a) for a in z.boundary_angles],
        "open_angle_ranges": [
            [float(z.open_angle_ranges[0][0]), float(z.open_angle_ranges[0][1])],
            [float(z.open_angle_ranges[1][0]), float(z.open_angle_ranges[1][1])],
        ],
        "params": params,
        "notes": notes,
    }


def save_zones_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")

