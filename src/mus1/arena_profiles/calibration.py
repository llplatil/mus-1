"""Rig calibration — the pixel half of pixel-to-mm scaling.

``ArenaProfile`` answers "how big is this arena in mm". That is a property of
the *artifact* and never changes. This module answers "how big does it appear,
in pixels, on this particular setup" — which is a property of the *rig*: the
arena plus the camera, its mounting, and the encoded frame geometry. The same
bucket filmed on two rigs has two different pixel radii, so pixel priors cannot
live on the profile.

A **rig** is identified by ``(profile_id, frame_shape)`` plus an optional
*epoch* for when the physical setup changes underneath an otherwise identical
rig — e.g. validation_2026's camera was moved between 2026-04-07 and
2026-04-30, changing the arena radius from ~350 px to ~433 px in the same
1080x1080 frame.

Why this exists
---------------
``compute_arena_boundary_geometric.py`` searched for the arena edge using
constants hardcoded to the publication rig (``PRIOR_RADIUS = 352.0``,
``RADIUS_MIN/MAX = 338/368``). Those constants are correct for one rig and
reject every frame from any other: the pilot's Home Depot bucket images at
~201 px, so a 338-368 px clamp discards all of it. Making the priors data
rather than code is what lets the same fitter serve any arena.

Ground truth
------------
The sole source of truth is the operator's hand-marked boundaries in the
experiment JSONs (``arena_markings.arena_boundary``). A ``RigCalibration`` is
*derived* from those marks and is always regenerable; it is a cache, never a
measurement. It records every source experiment and that mark's ``marked_at``
so staleness is detectable rather than merely possible — see
:meth:`RigCalibration.is_stale_against`.

Anisotropic pixels
------------------
Scaling is only isotropic when the stored pixel grid is square. The pilot's
video is anamorphic (``sample_aspect_ratio`` 32:27), so a physically circular
arena is *stored* as an ellipse with x/y semi-axis ratio 27/32 = 0.84375 —
measured 0.826 across 13 marks. Tracking coordinates live in that stored grid,
so one millimetre of real displacement costs a different number of pixels in x
than in y, and a single isotropic mm/px is wrong in both axes at once. This
module therefore carries per-axis scales; ``mm_per_px_isotropic`` is offered
only for square-pixel rigs and refuses otherwise.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple


# Ratio beyond which a rig's stored pixels are treated as non-square and an
# isotropic scale is refused. 1% covers hand-marking noise on square rigs
# (publication measures 0.99) without admitting the pilot's 0.826.
SQUARE_PIXEL_TOLERANCE = 0.01

# Multiples of MAD beyond which a ground-truth mark is rejected as an outlier.
# MAD (not sd) so a single bad mark cannot inflate the threshold that would
# have caught it.
OUTLIER_MAD_MULTIPLE = 5.0

# A stratum whose marks separate into clusters further apart than this fraction
# of the pooled median is refused rather than averaged: it is two rigs wearing
# one name.
MULTIMODAL_SEPARATION = 0.05


class MultimodalRigError(ValueError):
    """Raised when one rig's marks describe two physically different setups.

    Averaging across a camera move produces a calibration correct for neither
    epoch, so the calibrator refuses and reports the clusters. Resolution is an
    explicit rig split, which is a human decision about what physically
    happened — not something to infer from pixels.
    """

    def __init__(self, rig_id: str, clusters: Sequence[Dict[str, Any]]):
        self.rig_id = rig_id
        self.clusters = list(clusters)
        summary = "; ".join(
            f"{c['n']} marks near {c['median_radius_px']:.1f}px "
            f"({c['first_date']}..{c['last_date']})"
            for c in self.clusters
        )
        super().__init__(
            f"Rig {rig_id!r} is multimodal and cannot be calibrated as one rig: "
            f"{summary}. Split it into epochs (rig_id#<epoch>) and re-derive."
        )


def rig_id(profile_id: str, frame_shape: Sequence[int], epoch: Optional[str] = None) -> str:
    """Stable identifier for a rig. ``frame_shape`` is ``(height, width)``."""
    h, w = int(frame_shape[0]), int(frame_shape[1])
    base = f"{profile_id}@{h}x{w}"
    return f"{base}#{epoch}" if epoch else base


@dataclass(frozen=True)
class GroundTruthMark:
    """One operator-marked arena boundary, as consumed by the calibrator."""
    experiment_id: str
    semi_axis_x_px: float
    semi_axis_y_px: float
    marked_at: str
    n_clicks: int
    date_recorded: str = ""
    center_xy: Optional[Tuple[float, float]] = None
    object_midpoint_xy: Optional[Tuple[float, float]] = None

    @property
    def mean_radius_px(self) -> float:
        return (self.semi_axis_x_px + self.semi_axis_y_px) / 2.0

    @property
    def axis_ratio(self) -> float:
        return self.semi_axis_x_px / self.semi_axis_y_px if self.semi_axis_y_px else 0.0


@dataclass(frozen=True)
class RigCalibration:
    """Derived pixel priors for one rig. Regenerable; never a measurement."""

    rig_id: str
    profile_id: str
    frame_shape: Tuple[int, int]                  # (height, width)
    sample_aspect_ratio: Tuple[int, int]          # (num, den); (1, 1) = square

    radius_x_px: float
    radius_y_px: float
    radius_tolerance_px: float
    center_offset_from_object_midpoint: Tuple[float, float]
    center_max_shift_px: float

    n_ground_truth: int
    #: Declared epoch name and its inclusive date range, when this rig is one
    #: epoch of a setup that changed (e.g. a camera move). Stored rather than
    #: inferred from the source marks: which sessions belong to which epoch is a
    #: human statement about what physically happened, and inferring it from the
    #: marks that happen to exist gets it wrong as soon as marking is uneven.
    epoch: Optional[str] = None
    epoch_from: str = ""
    epoch_to: str = ""
    derived_from: List[Dict[str, Any]] = field(default_factory=list)
    excluded: List[Dict[str, Any]] = field(default_factory=list)
    derived_at: str = ""
    notes: str = ""

    # -- geometry -----------------------------------------------------------

    @property
    def stored_pixels_are_square(self) -> bool:
        num, den = self.sample_aspect_ratio
        return abs(num / den - 1.0) <= SQUARE_PIXEL_TOLERANCE if den else True

    def mm_per_px_axes(self, diameter_mm: float) -> Tuple[float, float]:
        """Return ``(mm_per_px_x, mm_per_px_y)`` for this rig.

        Always correct, square pixels or not. On an anamorphic rig the two
        differ by the sample aspect ratio, so callers measuring distances in
        raw stored-pixel coordinates must scale each axis separately (or
        resample to square pixels first) rather than applying one factor.
        """
        return (
            diameter_mm / (2.0 * self.radius_x_px),
            diameter_mm / (2.0 * self.radius_y_px),
        )

    def mm_per_px_isotropic(self, diameter_mm: float) -> Optional[float]:
        """Single scale — only for square-pixel rigs; ``None`` otherwise.

        Refusing is deliberate. Averaging the two axes on the pilot rig yields
        a value ~9% low in x and ~7% high in y simultaneously, and the error in
        a Euclidean distance then depends on the direction of travel, which is
        not a bias any downstream correction can remove.
        """
        if not self.stored_pixels_are_square:
            return None
        mx, my = self.mm_per_px_axes(diameter_mm)
        return (mx + my) / 2.0

    def covers_date(self, date: str) -> bool:
        """Does this rig's declared epoch cover *date* (YYYY-MM-DD)?

        A rig with no epoch covers any date, and is only selected when no
        epoch-qualified sibling matches.
        """
        if not self.epoch:
            return True
        if not date:
            return False
        return (self.epoch_from or "0000-00-00") <= date[:10] <= (self.epoch_to or "9999-99-99")

    def radius_bounds_px(self) -> Tuple[float, float]:
        """Accept/reject window for a fitted radius, in mean-radius terms."""
        r = (self.radius_x_px + self.radius_y_px) / 2.0
        return (r - self.radius_tolerance_px, r + self.radius_tolerance_px)

    # -- integrity ----------------------------------------------------------

    def is_stale_against(self, current_marks: Sequence[GroundTruthMark]) -> Tuple[bool, str]:
        """Is this calibration out of date w.r.t. the marks on disk?

        Stale when a source mark has been re-marked since derivation, when a
        source mark has disappeared, or when new marks exist for the rig that
        were not used. Returns ``(stale, reason)``. This is why
        ``derived_from`` stores ``marked_at`` per experiment rather than a
        count: a count cannot distinguish "re-marked" from "unchanged".
        """
        used = {d["experiment_id"]: d.get("marked_at") for d in self.derived_from}
        excluded = {e["experiment_id"] for e in self.excluded}
        current = {m.experiment_id: m.marked_at for m in current_marks}

        for eid, marked_at in used.items():
            if eid not in current:
                return True, f"source mark {eid} is no longer on disk"
            if current[eid] != marked_at:
                return True, f"source mark {eid} was re-marked ({marked_at} -> {current[eid]})"
        new = set(current) - set(used) - excluded
        if new:
            return True, f"{len(new)} new mark(s) not used: {sorted(new)[:5]}"
        return False, "current"

    # -- serialisation ------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rig_id": self.rig_id,
            "profile_id": self.profile_id,
            "frame_shape": list(self.frame_shape),
            "sample_aspect_ratio": list(self.sample_aspect_ratio),
            "stored_pixels_are_square": self.stored_pixels_are_square,
            "radius_x_px": round(self.radius_x_px, 3),
            "radius_y_px": round(self.radius_y_px, 3),
            "radius_tolerance_px": round(self.radius_tolerance_px, 3),
            "center_offset_from_object_midpoint": [
                round(self.center_offset_from_object_midpoint[0], 3),
                round(self.center_offset_from_object_midpoint[1], 3),
            ],
            "center_max_shift_px": round(self.center_max_shift_px, 3),
            "n_ground_truth": self.n_ground_truth,
            "epoch": self.epoch,
            "epoch_from": self.epoch_from,
            "epoch_to": self.epoch_to,
            "derived_from": self.derived_from,
            "excluded": self.excluded,
            "derived_at": self.derived_at,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "RigCalibration":
        return cls(
            rig_id=d["rig_id"],
            profile_id=d["profile_id"],
            frame_shape=(int(d["frame_shape"][0]), int(d["frame_shape"][1])),
            sample_aspect_ratio=(int(d["sample_aspect_ratio"][0]), int(d["sample_aspect_ratio"][1])),
            radius_x_px=float(d["radius_x_px"]),
            radius_y_px=float(d["radius_y_px"]),
            radius_tolerance_px=float(d["radius_tolerance_px"]),
            center_offset_from_object_midpoint=(
                float(d["center_offset_from_object_midpoint"][0]),
                float(d["center_offset_from_object_midpoint"][1]),
            ),
            center_max_shift_px=float(d["center_max_shift_px"]),
            n_ground_truth=int(d["n_ground_truth"]),
            epoch=d.get("epoch"),
            epoch_from=d.get("epoch_from", ""),
            epoch_to=d.get("epoch_to", ""),
            derived_from=list(d.get("derived_from") or []),
            excluded=list(d.get("excluded") or []),
            derived_at=d.get("derived_at", ""),
            notes=d.get("notes", ""),
        )


# ---------------------------------------------------------------------------
# Derivation
# ---------------------------------------------------------------------------

def _median(xs: Sequence[float]) -> float:
    s = sorted(xs)
    n = len(s)
    if n == 0:
        raise ValueError("median of empty sequence")
    mid = n // 2
    return s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2.0


def _mad(xs: Sequence[float], med: Optional[float] = None) -> float:
    m = _median(xs) if med is None else med
    return _median([abs(x - m) for x in xs])


def find_clusters(marks: Sequence[GroundTruthMark]) -> List[Dict[str, Any]]:
    """Split marks into radius clusters separated by more than a set fraction.

    A deliberately simple 1-D gap split rather than a mixture model or dip
    test: at the n available per rig (11-14) no distributional test has the
    power to be trusted, and a gap rule is auditable by a human reading the
    numbers. It is a *tripwire*, not a classifier — its job is to refuse, and
    a human decides what the split means.
    """
    if not marks:
        return []
    ordered = sorted(marks, key=lambda m: m.mean_radius_px)
    pooled_median = _median([m.mean_radius_px for m in ordered])
    threshold = MULTIMODAL_SEPARATION * pooled_median

    groups: List[List[GroundTruthMark]] = [[ordered[0]]]
    for prev, cur in zip(ordered, ordered[1:]):
        if cur.mean_radius_px - prev.mean_radius_px > threshold:
            groups.append([cur])
        else:
            groups[-1].append(cur)

    out = []
    for g in groups:
        dates = sorted(m.date_recorded for m in g if m.date_recorded)
        out.append({
            "n": len(g),
            "median_radius_px": _median([m.mean_radius_px for m in g]),
            "experiment_ids": [m.experiment_id for m in g],
            "first_date": dates[0] if dates else "",
            "last_date": dates[-1] if dates else "",
        })
    return out


def derive_calibration(
    *,
    profile_id: str,
    frame_shape: Sequence[int],
    sample_aspect_ratio: Sequence[int],
    marks: Sequence[GroundTruthMark],
    epoch: Optional[str] = None,
    epoch_from: str = "",
    epoch_to: str = "",
    derived_at: str = "",
    min_marks: int = 3,
    min_clicks: int = 8,
) -> RigCalibration:
    """Derive a rig calibration from operator ground truth.

    Raises :class:`MultimodalRigError` when the marks describe more than one
    physical setup, and ``ValueError`` when too few usable marks survive.

    Marks with fewer than *min_clicks* points are excluded before estimation,
    not after: a sparse ellipse fit is unreliable in a way that is knowable up
    front, independent of whether its radius happens to look reasonable.
    """
    rid = rig_id(profile_id, frame_shape, epoch)
    if not marks:
        raise ValueError(f"Rig {rid!r}: no ground-truth marks")

    excluded: List[Dict[str, Any]] = []
    usable: List[GroundTruthMark] = []
    for m in marks:
        if m.n_clicks < min_clicks:
            excluded.append({
                "experiment_id": m.experiment_id,
                "reason": f"only {m.n_clicks} click points (minimum {min_clicks})",
                "mean_radius_px": round(m.mean_radius_px, 2),
            })
        else:
            usable.append(m)

    if not usable:
        raise ValueError(f"Rig {rid!r}: every mark was excluded for low click count")

    clusters = find_clusters(usable)
    if len(clusters) > 1:
        raise MultimodalRigError(rid, clusters)

    radii = [m.mean_radius_px for m in usable]
    med = _median(radii)
    mad = _mad(radii, med)
    # MAD of zero (all marks identical) must not reject everything.
    cutoff = OUTLIER_MAD_MULTIPLE * mad if mad > 0 else float("inf")

    kept = []
    for m in usable:
        if abs(m.mean_radius_px - med) > cutoff:
            excluded.append({
                "experiment_id": m.experiment_id,
                "reason": (f"radius {m.mean_radius_px:.1f}px is "
                           f"{abs(m.mean_radius_px - med) / mad:.1f} MAD from the "
                           f"rig median {med:.1f}px"),
                "mean_radius_px": round(m.mean_radius_px, 2),
            })
        else:
            kept.append(m)

    if len(kept) < min_marks:
        raise ValueError(
            f"Rig {rid!r}: only {len(kept)} usable marks after exclusions "
            f"(minimum {min_marks}). Mark more boundaries before calibrating."
        )

    rx = _median([m.semi_axis_x_px for m in kept])
    ry = _median([m.semi_axis_y_px for m in kept])
    # Tolerance from observed spread, floored so a rig that happens to have
    # very consistent marks does not get a window too tight to fit anything.
    spread = _mad([m.mean_radius_px for m in kept]) * 1.4826  # -> sd-equivalent
    tolerance = max(4.0 * spread, 0.04 * ((rx + ry) / 2.0))

    offsets = [
        (m.center_xy[0] - m.object_midpoint_xy[0], m.center_xy[1] - m.object_midpoint_xy[1])
        for m in kept
        if m.center_xy and m.object_midpoint_xy
    ]
    if offsets:
        off = (_median([o[0] for o in offsets]), _median([o[1] for o in offsets]))
        off_spread = max(_mad([o[0] for o in offsets]), _mad([o[1] for o in offsets])) * 1.4826
        center_max_shift = max(6.0 * off_spread, 0.05 * ((rx + ry) / 2.0))
    else:
        off = (0.0, 0.0)
        center_max_shift = 0.1 * ((rx + ry) / 2.0)

    return RigCalibration(
        rig_id=rid,
        profile_id=profile_id,
        frame_shape=(int(frame_shape[0]), int(frame_shape[1])),
        sample_aspect_ratio=(int(sample_aspect_ratio[0]), int(sample_aspect_ratio[1])),
        radius_x_px=rx,
        radius_y_px=ry,
        radius_tolerance_px=tolerance,
        center_offset_from_object_midpoint=off,
        center_max_shift_px=center_max_shift,
        n_ground_truth=len(kept),
        epoch=epoch,
        epoch_from=epoch_from,
        epoch_to=epoch_to,
        derived_from=[
            {"experiment_id": m.experiment_id, "marked_at": m.marked_at,
             "n_clicks": m.n_clicks, "mean_radius_px": round(m.mean_radius_px, 2)}
            for m in sorted(kept, key=lambda z: z.experiment_id)
        ],
        excluded=sorted(excluded, key=lambda e: e["experiment_id"]),
        derived_at=derived_at,
        notes="",
    )
