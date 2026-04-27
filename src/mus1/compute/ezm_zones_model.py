#!/usr/bin/env python3
"""
EZM open vs closed arm zone model.

We represent the EZM track as an elliptical annulus in image space and define the
two open arms as angular sectors in a normalized coordinate system where the
outer ellipse maps to the unit circle.

This matches the "2D rainbow" (arc) geometry better than polygons.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Sequence, Tuple

import numpy as np


TAU = 2.0 * math.pi


def wrap_angle(theta: np.ndarray) -> np.ndarray:
    return np.mod(theta, TAU)


@dataclass(frozen=True)
class EllipseParams:
    """OpenCV-style ellipse parameters."""

    center_xy: Tuple[float, float]  # (cx, cy)
    axes_xy: Tuple[float, float]  # (major_diameter, minor_diameter)
    angle_deg: float  # rotation of major axis, degrees

    @property
    def a(self) -> float:
        """Semi-major axis length."""
        return float(self.axes_xy[0]) / 2.0

    @property
    def b(self) -> float:
        """Semi-minor axis length."""
        return float(self.axes_xy[1]) / 2.0

    @property
    def angle_rad(self) -> float:
        return math.radians(float(self.angle_deg))


@dataclass(frozen=True)
class ZoneDefinition:
    """
    Elliptical annulus + two open-arm angular ranges.

    Angles are in radians in [0, 2π).
    A range is stored as (start, end). If start <= end: theta in [start, end].
    If start > end: wraps around 2π and theta in [start, 2π) ∪ [0, end].
    """

    outer_ellipse: EllipseParams
    r_inner: float
    open_angle_ranges: Tuple[Tuple[float, float], Tuple[float, float]]
    version: str = "ezm_open_closed_v1"


def angle_in_range(theta: np.ndarray, start: float, end: float) -> np.ndarray:
    theta = wrap_angle(theta)
    start = float(start) % TAU
    end = float(end) % TAU
    if start <= end:
        return (theta >= start) & (theta <= end)
    # wrap
    return (theta >= start) | (theta <= end)


def angle_in_any_open_range(theta: np.ndarray, open_ranges: Sequence[Tuple[float, float]]) -> np.ndarray:
    mask = np.zeros_like(theta, dtype=bool)
    for start, end in open_ranges:
        mask |= angle_in_range(theta, start, end)
    return mask


def _rotation_matrix(angle_rad: float) -> np.ndarray:
    c = math.cos(angle_rad)
    s = math.sin(angle_rad)
    return np.array([[c, -s], [s, c]], dtype=float)


def normalize_xy_to_unit_circle(
    x: np.ndarray,
    y: np.ndarray,
    outer: EllipseParams,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Map image coordinates -> normalized coordinates where the outer ellipse is r=1.

    Steps:
    - subtract center
    - rotate by -angle to align ellipse axes
    - scale by (1/a, 1/b)
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)

    cx, cy = outer.center_xy
    pts = np.stack([x - cx, y - cy], axis=0)  # 2 x N

    R = _rotation_matrix(-outer.angle_rad)
    rot = R @ pts

    a = outer.a if outer.a > 0 else np.nan
    b = outer.b if outer.b > 0 else np.nan

    xn = rot[0, :] / a
    yn = rot[1, :] / b
    return xn, yn


def compute_r_theta(
    x: np.ndarray,
    y: np.ndarray,
    outer: EllipseParams,
) -> Tuple[np.ndarray, np.ndarray]:
    xn, yn = normalize_xy_to_unit_circle(x, y, outer)
    r = np.sqrt(xn * xn + yn * yn)
    theta = wrap_angle(np.arctan2(yn, xn))
    return r, theta


def classify_points(
    x: np.ndarray,
    y: np.ndarray,
    zones: ZoneDefinition,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """
    Returns:
    - in_track: r in [r_inner, 1]
    - in_open: in_track and theta in open ranges
    - in_closed: in_track and not in_open
    - r, theta: normalized polar coords
    """
    r, theta = compute_r_theta(x, y, zones.outer_ellipse)
    in_track = (r >= float(zones.r_inner)) & (r <= 1.0)
    in_open = in_track & angle_in_any_open_range(theta, zones.open_angle_ranges)
    in_closed = in_track & (~in_open)
    return in_track, in_open, in_closed, r, theta


def choose_minor_arc_range(theta_a: float, theta_b: float) -> Tuple[float, float]:
    """
    Given two angles, return a (start,end) range representing the shorter arc between them.
    The range may wrap around 2π.
    """
    a = float(theta_a) % TAU
    b = float(theta_b) % TAU
    # forward distance a->b
    d_ab = (b - a) % TAU
    d_ba = (a - b) % TAU
    if d_ab <= d_ba:
        return a, b
    return b, a


def load_zone_definition(path: Path) -> ZoneDefinition:
    data = json.loads(Path(path).read_text())
    outer = data["outer_ellipse"]
    zones = ZoneDefinition(
        outer_ellipse=EllipseParams(
            center_xy=(float(outer["center"][0]), float(outer["center"][1])),
            axes_xy=(float(outer["axes"][0]), float(outer["axes"][1])),
            angle_deg=float(outer["angle_deg"]),
        ),
        r_inner=float(data["r_inner"]),
        open_angle_ranges=(
            (float(data["open_angle_ranges"][0][0]), float(data["open_angle_ranges"][0][1])),
            (float(data["open_angle_ranges"][1][0]), float(data["open_angle_ranges"][1][1])),
        ),
        version=str(data.get("version", "ezm_open_closed_v1")),
    )
    return zones


def save_zone_definition(
    path: Path,
    zones: ZoneDefinition,
    image_width: int,
    image_height: int,
    params: dict,
    notes: str = "",
) -> None:
    payload = {
        "version": zones.version,
        "image": {"width": int(image_width), "height": int(image_height)},
        "outer_ellipse": {
            "center": [float(zones.outer_ellipse.center_xy[0]), float(zones.outer_ellipse.center_xy[1])],
            "axes": [float(zones.outer_ellipse.axes_xy[0]), float(zones.outer_ellipse.axes_xy[1])],
            "angle_deg": float(zones.outer_ellipse.angle_deg),
        },
        "r_inner": float(zones.r_inner),
        "open_angle_ranges": [
            [float(zones.open_angle_ranges[0][0]), float(zones.open_angle_ranges[0][1])],
            [float(zones.open_angle_ranges[1][0]), float(zones.open_angle_ranges[1][1])],
        ],
        "params": params,
        "notes": notes,
    }
    Path(path).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")

