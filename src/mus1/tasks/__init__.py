"""Task definition system for mus1.

Provides configurable behavioral task types. Each task defines its arena
geometry, annotation schema, QC flag vocabulary, and metric computation.
"""
from mus1.tasks.base import TaskDefinition
from mus1.tasks.registry import TaskRegistry

__all__ = ["TaskDefinition", "TaskRegistry"]
