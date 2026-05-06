"""P_NO — Pilot Novel Object pre-publication cohort.

Reuses NOR's annotation fields, objects, variants, and QC vocabulary —
the only differences are the physical artifact (Home Depot 5-gallon
orange bucket, ~292 mm inner diameter, profile id
``home_depot_5gal_orange``) and the older recording rig
(720x480 .MOD interlaced, 29.97 fps, hand-scored era).

53 experiments under ``data/experiment_data/P_NO/``; cohort
``data/cohorts/p_no_pilot.json``. See
``reports_workspace/pilot_novel_object/pilot_nor_methods_results.md``
for protocol differences relative to the publication NOR/NOF cohort.
"""
from __future__ import annotations

from typing import Optional

from mus1.tasks.builtins.nor import NORTask


class PNOTask(NORTask):

    @property
    def task_id(self) -> str:
        return "P_NO"

    @property
    def display_name(self) -> str:
        return "Pilot Novel Object"

    @property
    def description(self) -> str:
        return (
            "Pre-publication NOR pilot collected with a different protocol "
            "(Home Depot bucket arena, everyday objects, hand-scored "
            "exploration times, .MOD source video). Re-processed through "
            "the automated DLC pipeline as a methodological validation "
            "of the publication d2 results."
        )

    @property
    def arena_profile_id(self) -> Optional[str]:
        return "home_depot_5gal_orange"

    @property
    def paired_task_id(self) -> Optional[str]:
        # P_NO is not paired — pilot ran NOR-style sessions only,
        # without a matching NOF familiarization day.
        return None
