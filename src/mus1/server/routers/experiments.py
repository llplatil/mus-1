"""Experiment API."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from mus1.server.deps import get_experiment_service
from mus1.server.services.experiment_service import ExperimentService, ExperimentSummary

router = APIRouter()


def _summary_to_dict(s: ExperimentSummary) -> Dict[str, Any]:
    return {
        "experiment_id": s.experiment_id,
        "task_id": s.task_id,
        "subject_id": s.subject_id,
        "date_recorded": s.date_recorded,
        "genotype": s.genotype,
        "sex": s.sex,
        "video_path": s.video_path,
        "frame_count": s.frame_count,
        "duration_seconds": s.duration_seconds,
        "qc_status": s.qc_status,
        "auto_flags": s.auto_flags,
        "has_annotation": s.has_annotation,
        "has_tracking": s.has_tracking,
        "has_computed_metrics": s.has_computed_metrics,
        "paired_experiment_id": s.paired_experiment_id,
    }


@router.get("/", summary="List experiments with optional filtering")
def list_experiments(
    task_id: Optional[str] = None,
    subject_id: Optional[str] = None,
    genotype: Optional[str] = None,
    sex: Optional[str] = None,
    qc_status: Optional[str] = None,
    has_annotation: Optional[bool] = None,
    has_tracking: Optional[bool] = None,
    svc: ExperimentService = Depends(get_experiment_service),
) -> List[Dict[str, Any]]:
    results = svc.list_experiments(
        task_id=task_id,
        subject_id=subject_id,
        genotype=genotype,
        sex=sex,
        qc_status=qc_status,
        has_annotation=has_annotation,
        has_tracking=has_tracking,
    )
    return [_summary_to_dict(e) for e in results]


@router.get("/counts", summary="Experiment counts by task")
def counts_by_task(
    svc: ExperimentService = Depends(get_experiment_service),
) -> Dict[str, int]:
    return svc.count_by_task()


@router.get("/subjects", summary="List unique subjects")
def list_subjects(
    svc: ExperimentService = Depends(get_experiment_service),
) -> List[Dict[str, Any]]:
    return svc.list_subjects()


@router.get("/{experiment_id}", summary="Get experiment summary")
def get_experiment(
    experiment_id: str,
    svc: ExperimentService = Depends(get_experiment_service),
) -> Dict[str, Any]:
    exp = svc.get_experiment(experiment_id)
    if not exp:
        raise HTTPException(404, f"Experiment not found: {experiment_id}")
    return _summary_to_dict(exp)


@router.get("/{experiment_id}/json", summary="Get full experiment JSON")
def get_experiment_json(
    experiment_id: str,
    svc: ExperimentService = Depends(get_experiment_service),
) -> Dict[str, Any]:
    data = svc.get_experiment_json(experiment_id)
    if not data:
        raise HTTPException(404, f"Experiment not found: {experiment_id}")
    return data


@router.get("/{experiment_id}/frame", summary="Extract a video frame as JPEG")
def get_frame(
    experiment_id: str,
    frame_index: Optional[int] = None,
    svc: ExperimentService = Depends(get_experiment_service),
) -> Response:
    frame_bytes = svc.extract_frame(experiment_id, frame_index)
    if not frame_bytes:
        raise HTTPException(404, "Frame unavailable (no video or experiment not found)")
    return Response(content=frame_bytes, media_type="image/jpeg")


@router.post("/{experiment_id}/refresh", summary="Refresh a single experiment from disk")
def refresh_experiment(
    experiment_id: str,
    svc: ExperimentService = Depends(get_experiment_service),
) -> Dict[str, Any]:
    exp = svc.refresh_experiment(experiment_id)
    if not exp:
        raise HTTPException(404, f"Experiment not found: {experiment_id}")
    return _summary_to_dict(exp)


@router.post("/invalidate-cache", summary="Clear the experiment cache")
def invalidate_cache(
    svc: ExperimentService = Depends(get_experiment_service),
) -> Dict[str, str]:
    svc.invalidate_cache()
    return {"status": "cache_cleared"}
