"""Annotation API."""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel

from mus1.server.deps import get_annotation_service
from mus1.server.services.annotation_service import AnnotationService

router = APIRouter()


class SaveAnnotationRequest(BaseModel):
    annotation: Dict[str, Any]
    by: str = "api"


@router.get("/{experiment_id}", summary="Get arena annotation")
def get_annotation(
    experiment_id: str,
    svc: AnnotationService = Depends(get_annotation_service),
) -> Dict[str, Any]:
    ann = svc.get_annotation(experiment_id)
    if ann is None:
        raise HTTPException(404, f"Experiment not found: {experiment_id}")
    return ann


@router.put("/{experiment_id}", summary="Save arena annotation")
def save_annotation(
    experiment_id: str,
    req: SaveAnnotationRequest,
    svc: AnnotationService = Depends(get_annotation_service),
) -> Dict[str, Any]:
    try:
        return svc.save_annotation(experiment_id, req.annotation, by=req.by)
    except KeyError as e:
        raise HTTPException(404, str(e))


@router.get("/{experiment_id}/provenance-frame", summary="Export annotated frame as PNG")
def provenance_frame(
    experiment_id: str,
    frame_index: Optional[int] = None,
    svc: AnnotationService = Depends(get_annotation_service),
) -> Response:
    frame = svc.export_annotated_frame(experiment_id, frame_index)
    if not frame:
        raise HTTPException(404, "Frame unavailable")
    return Response(content=frame, media_type="image/png")
