"""QC flags API."""
from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from mus1.server.deps import get_qc_service
from mus1.server.services.qc_service import QCService

router = APIRouter()


class SetStatusRequest(BaseModel):
    status: str
    by: str = "api"
    detail: str = ""


class SetNotesRequest(BaseModel):
    notes: str
    by: str = "api"


@router.get("/{experiment_id}", summary="Get QC flags for an experiment")
def get_qc_flags(
    experiment_id: str,
    svc: QCService = Depends(get_qc_service),
) -> Dict[str, Any]:
    try:
        return svc.get_qc_flags(experiment_id)
    except KeyError as e:
        raise HTTPException(404, str(e))


@router.put("/{experiment_id}/status", summary="Set QC review status")
def set_status(
    experiment_id: str,
    req: SetStatusRequest,
    svc: QCService = Depends(get_qc_service),
) -> Dict[str, Any]:
    try:
        return svc.set_status(experiment_id, req.status, by=req.by, detail=req.detail)
    except KeyError as e:
        raise HTTPException(404, str(e))


@router.put("/{experiment_id}/notes", summary="Set QC notes")
def set_notes(
    experiment_id: str,
    req: SetNotesRequest,
    svc: QCService = Depends(get_qc_service),
) -> Dict[str, Any]:
    try:
        return svc.set_notes(experiment_id, req.notes, by=req.by)
    except KeyError as e:
        raise HTTPException(404, str(e))


@router.post("/{experiment_id}/auto-flags", summary="Recompute auto-flags")
def recompute_auto_flags(
    experiment_id: str,
    svc: QCService = Depends(get_qc_service),
) -> Dict[str, Any]:
    try:
        return svc.recompute_and_save_auto_flags(experiment_id)
    except KeyError as e:
        raise HTTPException(404, str(e))


@router.get("/{experiment_id}/auto-flags/preview", summary="Preview auto-flags without saving")
def preview_auto_flags(
    experiment_id: str,
    svc: QCService = Depends(get_qc_service),
) -> List[str]:
    try:
        return svc.compute_auto_flags(experiment_id)
    except KeyError as e:
        raise HTTPException(404, str(e))
