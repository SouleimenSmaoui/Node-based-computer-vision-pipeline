"""Node base class, declarative spec collection, and the @node decorator
(docs/04 §1). Built-in nodes and plugins use exactly this API (principle A5).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Sequence

from cvflow.core.params import ParamSpec
from cvflow.core.ports import PortDecl

if TYPE_CHECKING:  # pragma: no cover
    from cvflow.engine.context import ExecutionContext


@dataclass(frozen=True)
class Issue:
    """Validation finding surfaced before execution (amber badge in the GUI)."""

    message: str
    level: str = "warning"  # warning | error


@dataclass
class NodeSpec:
    type_id: str
    version: str
    category: str
    label: str
    doc: str
    inputs: list[PortDecl]
    outputs: list[PortDecl]
    params: list[ParamSpec]
    node_class: type["Node"]
    keywords: tuple[str, ...] = ()

    def input(self, name: str) -> PortDecl:
        for p in self.inputs:
            if p.name == name:
                return p
        raise KeyError(f"{self.type_id} has no input port {name!r}")

    def output(self, name: str) -> PortDecl:
        for p in self.outputs:
            if p.name == name:
                return p
        raise KeyError(f"{self.type_id} has no output port {name!r}")


class Node:
    """Base class for every block. Subclasses declare ports/params as class
    attributes and implement ``process``. Lifecycle: setup → process×N → teardown.
    """

    # ---- behavior flags (docs/04 §1.2) ----
    side_effect: bool = False      # writes to the world → runs only when armed
    stateful: bool = False         # per-frame state → sequential, uncached
    cacheable: bool = True         # set False for nondeterministic nodes
    parallel_unsafe: bool = False  # wraps a non-thread-safe library

    # Filled by the @node decorator.
    __cvflow_spec__: NodeSpec | None = None

    # Declaration-order port/param collection.
    _decl_inputs: list[PortDecl] = []
    _decl_outputs: list[PortDecl] = []
    _decl_params: list[ParamSpec] = []

    def __init_subclass__(cls, **kw: Any) -> None:
        super().__init_subclass__(**kw)
        inputs: list[PortDecl] = list(cls.__mro__[1]._decl_inputs) if hasattr(
            cls.__mro__[1], "_decl_inputs") else []
        outputs: list[PortDecl] = list(cls.__mro__[1]._decl_outputs) if hasattr(
            cls.__mro__[1], "_decl_outputs") else []
        params: list[ParamSpec] = list(cls.__mro__[1]._decl_params) if hasattr(
            cls.__mro__[1], "_decl_params") else []
        for value in vars(cls).values():
            if isinstance(value, PortDecl):
                (inputs if value.direction == "in" else outputs).append(value)
            elif isinstance(value, ParamSpec):
                params.append(value)
        cls._decl_inputs, cls._decl_outputs, cls._decl_params = inputs, outputs, params

    # ---- lifecycle (override as needed) ----
    def setup(self, ctx: "ExecutionContext") -> None:  # heavy imports/models go here
        return None

    def process(self, ctx: "ExecutionContext") -> None:
        raise NotImplementedError(f"{type(self).__name__} must implement process()")

    def teardown(self, ctx: "ExecutionContext") -> None:
        return None

    # ---- hooks ----
    def validate(self, params: dict[str, Any]) -> list[Issue]:
        """Cross-parameter checks; runs before execution."""
        return []

    @classmethod
    def migrate_params(cls, old_version: str, params: dict[str, Any]) -> dict[str, Any]:
        """Map params saved by an older node version onto the current spec.
        Default: keep matching names (unknowns are dropped by validation)."""
        return params

    @classmethod
    def external_state(cls, params: dict[str, Any], base_dir: str | None) -> Any:
        """JSON-able identity of external inputs (file mtime/size, frame index).

        Folded into the fingerprint so on-disk changes invalidate the cache
        (docs/02 §3.1). Default: no external state."""
        return None


def node(
    *,
    id: str,
    version: str = "1.0",
    category: str = "Misc",
    label: str | None = None,
    doc: str = "",
    keywords: Sequence[str] = (),
):
    """Class decorator that builds the NodeSpec from declarations.

    Registration happens separately (plugins.loader scans modules for decorated
    classes), so importing a node module never mutates global state.
    """

    def wrap(cls: type[Node]) -> type[Node]:
        if not issubclass(cls, Node):
            raise TypeError(f"@node target must subclass Node, got {cls!r}")
        spec = NodeSpec(
            type_id=id,
            version=version,
            category=category,
            label=label or cls.__name__,
            doc=doc or (cls.__doc__ or "").strip(),
            inputs=list(cls._decl_inputs),
            outputs=list(cls._decl_outputs),
            params=list(cls._decl_params),
            node_class=cls,
            keywords=tuple(keywords),
        )
        cls.__cvflow_spec__ = spec
        return cls

    return wrap
