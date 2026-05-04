"""Compute API — run deterministic computations on experiment data."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from mus1.server.deps import get_experiment_service
from mus1.server.services.experiment_service import ExperimentService

router = APIRouter()


class InteractionRequest(BaseModel):
    """Run NOR/NOF interaction metrics on an experiment."""
    experiment_id: str
    bodypart: str = "nose"
    likelihood_threshold: float = 0.6
    max_interp_gap: int = 10
    buffer_mode: str = "fixed"
    buffer_px: float = 20.0
    fps: float = 30.0
    min_bout_frames: int = 3


@router.post("/nor-nof-interaction", summary="Compute NOR/NOF interaction metrics")
def compute_interaction(
    req: InteractionRequest,
    svc: ExperimentService = Depends(get_experiment_service),
) -> Dict[str, Any]:
    from mus1.compute.tracking import try_read_dlc_csv, bp_track
    from mus1.compute.nor_nof_interaction import ObjectROI, compute_interaction_metrics

    data = svc.get_experiment_json(req.experiment_id)
    if not data:
        raise HTTPException(404, f"Experiment not found: {req.experiment_id}")

    from mus1.compute.tracking import resolve_dlc_csv_path
    dlc_path = resolve_dlc_csv_path(data.get("extraction"))
    if not dlc_path:
        raise HTTPException(422, "No tracking file linked to this experiment")

    df = try_read_dlc_csv(Path(dlc_path))
    if df is None:
        raise HTTPException(422, f"Cannot read DLC CSV: {dlc_path}")

    try:
        x, y, ok = bp_track(df, req.bodypart, req.likelihood_threshold, req.max_interp_gap)
    except KeyError:
        raise HTTPException(422, f"Bodypart '{req.bodypart}' not found in tracking CSV")

    am = data.get("arena_markings") or {}
    obj_a_xy = am.get("object_a_xy") or am.get("object_left_xy")
    obj_b_xy = am.get("object_b_xy") or am.get("object_right_xy")
    if not obj_a_xy or not obj_b_xy:
        raise HTTPException(422, "Experiment has no object markings")

    # Get roles from experiment-level metadata
    md_exp = (data.get("metadata") or {}).get("experiment_level") or {}
    role_a = ""
    role_b = ""
    novel_side = str(md_exp.get("novel_side", "")).strip().lower()
    if novel_side == "left":
        role_a, role_b = "novel", "familiar"
    elif novel_side == "right":
        role_a, role_b = "familiar", "novel"

    objects = [
        ObjectROI(name="object_a", cx=obj_a_xy[0], cy=obj_a_xy[1], radius_px=30, role=role_a),
        ObjectROI(name="object_b", cx=obj_b_xy[0], cy=obj_b_xy[1], radius_px=30, role=role_b),
    ]

    arena_cx = (obj_a_xy[0] + obj_b_xy[0]) / 2.0
    boundary = am.get("arena_boundary") or {}
    ellipse = boundary.get("ellipse") or {}
    center = ellipse.get("center_xy") or ellipse.get("center")
    if center:
        arena_cx = center[0]

    return compute_interaction_metrics(
        x=x, y=y, ok=ok,
        objects=objects,
        arena_center_x=arena_cx,
        fps=req.fps,
        buffer_mode=req.buffer_mode,
        buffer_px=req.buffer_px,
        min_bout_frames=req.min_bout_frames,
    )


@router.get("/tracking-bodyparts/{experiment_id}", summary="List available bodyparts")
def list_bodyparts(
    experiment_id: str,
    svc: ExperimentService = Depends(get_experiment_service),
) -> List[str]:
    from mus1.compute.tracking import try_read_dlc_csv, list_bodyparts

    data = svc.get_experiment_json(experiment_id)
    if not data:
        raise HTTPException(404, f"Experiment not found: {experiment_id}")

    from mus1.compute.tracking import resolve_dlc_csv_path
    dlc_path = resolve_dlc_csv_path(data.get("extraction"))
    if not dlc_path:
        raise HTTPException(422, "No tracking file linked")

    df = try_read_dlc_csv(Path(dlc_path))
    if df is None:
        raise HTTPException(422, "Cannot read DLC CSV")

    return list_bodyparts(df)
