"""Cohort management API."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from mus1.server.deps import get_cohort_service
from mus1.server.services.cohort_service import CohortService

router = APIRouter()


class CreateCohortRequest(BaseModel):
    name: str
    task_types: Optional[List[str]] = None
    description: str = ""


class MemberRequest(BaseModel):
    experiment_id: str
    notes: str = ""


@router.get("/", summary="List all cohorts")
def list_cohorts(
    task_type: Optional[str] = None,
    svc: CohortService = Depends(get_cohort_service),
) -> List[Dict[str, Any]]:
    return svc.list_cohorts(task_type=task_type)


@router.get("/{name}", summary="Get a cohort by name")
def get_cohort(
    name: str,
    svc: CohortService = Depends(get_cohort_service),
) -> Dict[str, Any]:
    cohort = svc.get_cohort(name)
    if not cohort:
        raise HTTPException(404, f"Cohort not found: {name}")
    return cohort


@router.get("/{name}/members", summary="Get cohort member IDs")
def get_members(
    name: str,
    svc: CohortService = Depends(get_cohort_service),
) -> List[str]:
    ids = svc.get_cohort_member_ids(name)
    if not ids:
        cohort = svc.get_cohort(name)
        if not cohort:
            raise HTTPException(404, f"Cohort not found: {name}")
    return sorted(ids)


@router.post("/", summary="Create a new cohort")
def create_cohort(
    req: CreateCohortRequest,
    svc: CohortService = Depends(get_cohort_service),
) -> Dict[str, Any]:
    return svc.create_cohort(req.name, task_types=req.task_types, description=req.description)


@router.post("/{name}/members", summary="Add a member to a cohort")
def add_member(
    name: str,
    req: MemberRequest,
    svc: CohortService = Depends(get_cohort_service),
) -> Dict[str, Any]:
    try:
        return svc.add_member(name, req.experiment_id, notes=req.notes)
    except KeyError as e:
        raise HTTPException(404, str(e))


@router.delete("/{name}/members/{experiment_id}", summary="Remove a member from a cohort")
def remove_member(
    name: str,
    experiment_id: str,
    svc: CohortService = Depends(get_cohort_service),
) -> Dict[str, Any]:
    try:
        return svc.remove_member(name, experiment_id)
    except KeyError as e:
        raise HTTPException(404, str(e))


@router.post("/{name}/refresh", summary="Recompute cohort summary")
def refresh_summary(
    name: str,
    svc: CohortService = Depends(get_cohort_service),
) -> Dict[str, Any]:
    try:
        return svc.refresh_summary(name)
    except KeyError as e:
        raise HTTPException(404, str(e))
