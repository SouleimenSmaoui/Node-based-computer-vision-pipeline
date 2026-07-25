"""Exception taxonomy for CVFlow (docs/01 §8).

Engine code converts node exceptions into per-node failure states; these types
are how every layer talks about what went wrong.
"""

from __future__ import annotations


class CVFlowError(Exception):
    """Base class for all CVFlow errors."""


class GraphError(CVFlowError):
    """Structural problem in a graph (unknown node, bad port, ...)."""


class CycleError(GraphError):
    """Connecting this edge would create a cycle."""


class ConnectionTypeError(GraphError):
    """Port types are incompatible. Carries a human fix hint."""

    def __init__(self, reason: str, hint: str | None = None):
        self.reason = reason
        self.hint = hint
        super().__init__(reason if not hint else f"{reason} — {hint}")


class UnknownNodeTypeError(GraphError):
    """Workflow references a node type that is not registered."""


class ParamError(CVFlowError):
    """Invalid parameter value or unknown parameter name."""


class NodeExecutionError(CVFlowError):
    """A node raised during setup/process/teardown.

    The engine catches and wraps node exceptions into NodeError records inside
    the RunReport; this exception type is raised only by the testing harness
    and by ``ExecutionContext.ensure``.
    """


class WorkflowFormatError(CVFlowError):
    """Workflow JSON is malformed or has an unsupported schema version."""


class PluginLoadError(CVFlowError):
    """A plugin module failed to import or register."""
