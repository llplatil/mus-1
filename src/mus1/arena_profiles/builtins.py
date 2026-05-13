"""Built-in arena profiles for this project.

External labs can add more via YAML — see
``mus1.arena_profiles.registry.ArenaProfileRegistry.load_from_yaml``.
"""
from __future__ import annotations

from mus1.arena_profiles.base import (
    AnnularGeometry,
    ArenaProfile,
    ArenaState,
    CircularGeometry,
)


# ---------------------------------------------------------------------------
# Tamco black bucket — used by NOR / NOF / OF (publication + validation cohorts)
# ---------------------------------------------------------------------------
# 17 3/8" inside diameter = 441.325 mm. Same artifact across publication and
# validation_2026 cohorts; surface was sanded mid-program. Dimensions are
# unchanged — surface state is a separate axis.

TAMCO_BLACK_BUCKET = ArenaProfile(
    id="tamco_black_bucket",
    description="Tamco cylindrical bucket, 17 3/8 inch inside diameter. "
                "Used for NOR / NOF / OF publication + validation_2026.",
    geometry=CircularGeometry(diameter_mm=441.325),
    states=(
        ArenaState(
            id="new",
            description="NEW: bucket recently introduced; surface unworn.",
        ),
        ArenaState(
            id="old",
            description="OLD: bucket worn from extended use prior to resanding.",
        ),
        ArenaState(
            id="unk",
            description="UNK: condition unknown / not recorded.",
        ),
        ArenaState(
            id="resanded",
            description="RESANDED: surface re-sanded (validation_2026 era "
                        "onwards). Dimensions unchanged; brightness profile differs.",
        ),
    ),
    default_state_id="unk",
)


# ---------------------------------------------------------------------------
# Home Depot 5-gallon orange bucket — used by the pilot_publication cohort
# ---------------------------------------------------------------------------
# Encore #34000-90; ~292 mm inside diameter. Older recording rig
# (720x480 .MOD interlaced, hand-scored era). One state. Per-experiment
# selection via arena_markings.arena_profile.profile_id; cohort-level
# default lives in data/cohorts/pilot_publication.json.

HOME_DEPOT_5GAL_ORANGE = ArenaProfile(
    id="home_depot_5gal_orange",
    description="Home Depot 5-gallon orange bucket, Encore #34000-90; "
                "~292 mm inside diameter. Used for the pilot_publication cohort.",
    geometry=CircularGeometry(diameter_mm=292.0),
    states=(),
    default_state_id="",
)


# ---------------------------------------------------------------------------
# EZM annular maze
# ---------------------------------------------------------------------------
# Outer diameter 460 mm; track width gives inner_ratio 0.761.

EZM_460MM = ArenaProfile(
    id="ezm_460mm",
    description="Elevated Zero Maze, 460 mm outer diameter, "
                "0.761 inner-to-outer ratio.",
    geometry=AnnularGeometry(outer_diameter_mm=460.0, inner_ratio=0.761),
    states=(),
    default_state_id="",
)


# Public registry — order is presentation order in any UI listing
ALL_BUILTINS = (
    TAMCO_BLACK_BUCKET,
    HOME_DEPOT_5GAL_ORANGE,
    EZM_460MM,
)
