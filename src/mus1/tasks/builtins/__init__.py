"""Built-in task definitions shipped with mus1."""
from mus1.tasks.builtins.ezm import EZMTask
from mus1.tasks.builtins.nor import NORTask
from mus1.tasks.builtins.nof import NOFTask
from mus1.tasks.builtins.open_field import OpenFieldTask
from mus1.tasks.builtins.rotarod import RotarodTask

ALL_BUILTINS = [EZMTask, NORTask, NOFTask, OpenFieldTask, RotarodTask]

__all__ = ["ALL_BUILTINS", "EZMTask", "NORTask", "NOFTask", "OpenFieldTask", "RotarodTask"]
