"""Node discovery: builtin packs + pip entry points (docs/04 §2).

Failure isolation: a module that raises on import is recorded as a
PluginFailure and never prevents the app/CLI from starting (requirement N8).
The user plugins folder (~/.cvflow/plugins) is a Phase 2 item — STATUS.md.
"""

from __future__ import annotations

import importlib
import importlib.metadata
import pkgutil
import traceback
from dataclasses import dataclass
from types import ModuleType

from cvflow.core.node import Node
from cvflow.core.registry import NodeRegistry

ENTRY_POINT_GROUP = "cvflow.nodes"


@dataclass
class PluginFailure:
    source: str
    error: str
    traceback: str


def _register_module(registry: NodeRegistry, module: ModuleType) -> None:
    for value in vars(module).values():
        if (
            isinstance(value, type)
            and issubclass(value, Node)
            and value.__cvflow_spec__ is not None
            and value.__cvflow_spec__.node_class is value
        ):
            registry.register(value)


def load_package(registry: NodeRegistry, package: ModuleType) -> list[PluginFailure]:
    failures: list[PluginFailure] = []
    prefix = package.__name__ + "."
    for info in pkgutil.walk_packages(package.__path__, prefix):
        try:
            module = importlib.import_module(info.name)
            _register_module(registry, module)
        except Exception as exc:
            failures.append(PluginFailure(info.name, str(exc), traceback.format_exc()))
    return failures


def load_builtin(registry: NodeRegistry) -> list[PluginFailure]:
    import cvflow.nodes

    return load_package(registry, cvflow.nodes)


def load_entry_points(registry: NodeRegistry) -> list[PluginFailure]:
    failures: list[PluginFailure] = []
    try:
        eps = importlib.metadata.entry_points(group=ENTRY_POINT_GROUP)
    except Exception as exc:  # metadata backend hiccup — degrade gracefully
        return [PluginFailure("entry-points", str(exc), traceback.format_exc())]
    for ep in eps:
        if ep.value == "cvflow.nodes":
            continue  # builtin pack, loaded directly
        try:
            module = ep.load()
            _register_module(registry, module)
            if hasattr(module, "__path__"):
                failures.extend(load_package(registry, module))
        except Exception as exc:
            failures.append(PluginFailure(f"{ep.name} ({ep.value})",
                                          str(exc), traceback.format_exc()))
    return failures


_default: tuple[NodeRegistry, list[PluginFailure]] | None = None


def builtin_registry(refresh: bool = False) -> tuple[NodeRegistry, list[PluginFailure]]:
    """Registry with builtin packs + installed plugin packages. Cached."""
    global _default
    if _default is None or refresh:
        registry = NodeRegistry()
        failures = load_builtin(registry)
        failures += load_entry_points(registry)
        _default = (registry, failures)
    return _default
