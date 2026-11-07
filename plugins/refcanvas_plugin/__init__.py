"""RefCanvas bootstrap: load the plugin from the Python modules here."""
from __future__ import annotations

import importlib
import os
import sys

__version__ = "0.1.0"


def _package_dir():
    """Make submodules importable when Painter loaded this file as a plain module."""
    here = os.path.dirname(os.path.abspath(__file__))
    if "__path__" not in globals():
        globals()["__path__"] = [here]
    self_module = sys.modules.get(__name__)
    if self_module is not None and not hasattr(self_module, "__path__"):
        self_module.__path__ = [here]
    return here


def _purge(package, leaves):
    """Delete cached submodules and package attributes before importing main."""
    prefix = package + "."
    for name in list(sys.modules):
        if name.startswith(prefix) and name[len(prefix):] in leaves:
            del sys.modules[name]
    holders = [globals()]
    self_module = sys.modules.get(package)
    if self_module is not None and self_module is not globals():
        holders.append(vars(self_module))
    for holder in holders:
        for leaf in leaves:
            holder.pop(leaf, None)


def _local_leaves(here):
    """Runtime module names stored beside this bootstrap."""
    try:
        return {name[:-3] for name in os.listdir(here)
                if name.endswith(".py") and name != "__init__.py"}
    except Exception:
        return set()


def _install():
    """Import main from the Python modules beside this bootstrap."""
    package = __name__
    here = _package_dir()
    leaves = _local_leaves(here)
    if "main" not in leaves:
        raise ImportError("RefCanvas: main.py missing in %s" % here)
    _purge(package, leaves)
    return importlib.import_module(package + ".main")


_main = _install()
__version__ = getattr(_main, "__version__", __version__)
start_plugin = _main.start_plugin
close_plugin = _main.close_plugin
