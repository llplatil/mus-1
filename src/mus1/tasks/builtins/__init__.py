"""Built-in task definitions shipped with mus1.

The ``P_NO`` task was retired on 2026-05-07 — pilot subjects ran NOR/NOF/OF
and have been restructured into ``data/pilot_data/`` accordingly. The
home_depot_5gal_orange arena profile is still registered for any future
pilot work that wants to reuse it.
"""
from mus1.tasks.builtins.ezm import EZMTask
from mus1.tasks.builtins.nor import NORTask
from mus1.tasks.builtins.nof import NOFTask
from mus1.tasks.builtins.open_field import OpenFieldTask
from mus1.tasks.builtins.rotarod import RotarodTask

ALL_BUILTINS = [EZMTask, NORTask, NOFTask, OpenFieldTask, RotarodTask]

__all__ = [
    "ALL_BUILTINS", "EZMTask", "NORTask", "NOFTask", "OpenFieldTask",
    "RotarodTask",
]
