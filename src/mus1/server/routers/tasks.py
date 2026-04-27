"""Task definition API."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends

from mus1.server.deps import get_task_registry
from mus1.tasks.registry import TaskRegistry

router = APIRouter()


@router.get("/", summary="List all registered tasks")
def list_tasks(
    registry: TaskRegistry = Depends(get_task_registry),
) -> List[Dict[str, Any]]:
    return [
        {
            "task_id": t.task_id,
            "display_name": t.display_name,
            "description": t.description,
            "arena_type": t.arena_type,
            "computed_metrics_key": t.computed_metrics_key,
            "annotation_fields": [
                {"name": f.name, "type": f.field_type, "required": f.required}
                for f in t.annotation_fields
            ],
            "variant_count": len(t.variants),
        }
        for t in registry.list_all()
    ]


@router.get("/{task_id}", summary="Get a single task definition")
def get_task(
    task_id: str,
    registry: TaskRegistry = Depends(get_task_registry),
) -> Dict[str, Any]:
    task = registry.get(task_id)
    return {
        "task_id": task.task_id,
        "display_name": task.display_name,
        "description": task.description,
        "arena_type": task.arena_type,
        "computed_metrics_key": task.computed_metrics_key,
        "annotation_fields": [
            {"name": f.name, "type": f.field_type, "required": f.required, "description": f.description}
            for f in task.annotation_fields
        ],
        "qc_flag_vocabulary": task.qc_flag_vocabulary,
        "variants": [
            {"name": v.name, "description": v.description, "parameters": v.parameters}
            for v in task.variants
        ],
        "physical_dimensions": task.arena_physical_dimensions,
    }
