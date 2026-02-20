from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ExperimentRow:
    experiment_id: str
    experiment_type: str
    date_recorded: str
    processing_stage: str
    subject_id: str
    sex: str
    genotype: Optional[str]
    treatment: Optional[str]
    artifacts_count: int
    qc_count: int
    has_ezm_zone: bool
    has_nor_nof_roi: bool

