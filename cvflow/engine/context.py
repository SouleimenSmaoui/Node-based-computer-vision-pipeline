"""ExecutionContext — the entire world a node sees while running (docs/02 §5).

Nodes never touch the engine, the graph, or other nodes; that boundary is what
makes them trivially testable and lets the engine evolve underneath.
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Mapping

from cvflow.core.errors import NodeExecutionError
from cvflow.core.node import NodeSpec
from cvflow.core.ports import PortDecl
from cvflow.core.types.base import KIND_IMAGE, runtime_check
from cvflow.core.types.image import ImageBuffer


class CancellationToken:
    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()


class Namespace:
    """Read-only attribute/item access over a dict (inputs, params)."""

    def __init__(self, data: Mapping[str, Any]):
        object.__setattr__(self, "_data", dict(data))

    def __getattr__(self, name: str) -> Any:
        try:
            return self._data[name]
        except KeyError:
            raise AttributeError(
                f"no such entry {name!r} (available: {sorted(self._data)})"
            ) from None

    def __getitem__(self, name: str) -> Any:
        return self._data[name]

    def __setattr__(self, name: str, value: Any) -> None:
        raise AttributeError("namespace is read-only")

    def get(self, name: str, default: Any = None) -> Any:
        return self._data.get(name, default)

    def keys(self):
        return self._data.keys()


class Outputs:
    """Validating output collector: ``ctx.outputs.<port> = value``."""

    def __init__(self, declared: list[PortDecl]):
        object.__setattr__(self, "_declared", {p.name: p for p in declared})
        object.__setattr__(self, "_values", {})

    def __setattr__(self, name: str, value: Any) -> None:
        declared: dict[str, PortDecl] = self._declared
        decl = declared.get(name)
        if decl is None:
            raise NodeExecutionError(
                f"node has no output port {name!r} (declared: {sorted(declared)})"
            )
        if decl.dtype.kind == KIND_IMAGE and not isinstance(value, ImageBuffer):
            raise NodeExecutionError(
                f"output {name!r} must be an ImageBuffer (wrap arrays with "
                f"ImageBuffer(...) or input.derive(...)), got {type(value).__name__}"
            )
        problem = runtime_check(value, decl.dtype)
        if problem:
            raise NodeExecutionError(f"output {name!r}: {problem}")
        self._values[name] = value

    __setitem__ = __setattr__

    def collect(self) -> dict[str, Any]:
        missing = [n for n in self._declared if n not in self._values]
        if missing:
            raise NodeExecutionError(
                f"process() finished without setting output(s): {missing}"
            )
        return dict(self._values)


class Resources:
    """Shared handles the engine grants nodes (base dir today; models later)."""

    def __init__(self, base_dir: str | None = None, **extra: Any):
        self.base_dir = base_dir
        self._extra = extra

    def get(self, name: str, default: Any = None) -> Any:
        return self._extra.get(name, default)


class ExecutionContext:
    def __init__(
        self,
        *,
        node_id: str,
        spec: NodeSpec,
        inputs: Mapping[str, Any] | None = None,
        params: Mapping[str, Any] | None = None,
        resources: Resources | None = None,
        state: dict[str, Any] | None = None,
        token: CancellationToken | None = None,
        scale: float | None = None,
    ):
        self.node_id = node_id
        self.inputs = Namespace(inputs or {})
        self.params = Namespace(params or {})
        self.outputs = Outputs(spec.outputs)
        self.resources = resources or Resources()
        self.state = state if state is not None else {}
        self.scale = scale
        self.frame = None
        self.log = logging.getLogger(f"cvflow.node.{spec.type_id}")
        self._token = token

    def is_cancelled(self) -> bool:
        return self._token.cancelled if self._token else False

    def ensure(self, condition: bool, message: str) -> None:
        """Assert a runtime precondition; failure becomes a node error."""
        if not condition:
            raise NodeExecutionError(message)

    def progress(self, fraction: float) -> None:
        """Long-running nodes may report 0..1 progress. No-op in Phase 0;
        the GUI subscribes to this in Phase 1."""
