"""Graph document: nodes, edges, structural validation (docs/01 §4).

Edit-time guarantees:
  - connecting an edge that would create a cycle raises CycleError,
  - type-incompatible connections raise ConnectionTypeError (with fix hint),
  - an input port holds at most one edge; reconnecting replaces it
    (matches node-editor UX; documented behavior).

Change notification is plain callbacks (GraphListener) — the GUI adapts them
onto Qt signals later; the core stays framework-free.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

from cvflow.core.errors import ConnectionTypeError, CycleError, GraphError
from cvflow.core.node import NodeSpec
from cvflow.core.params import default_params, validate_params
from cvflow.core.types.base import Coerce, Reject, check_connection


@dataclass(frozen=True)
class Edge:
    src: tuple[str, str]  # (node_id, output port name)
    dst: tuple[str, str]  # (node_id, input port name)
    coercion: Coerce | None = None


@dataclass
class NodeInstance:
    id: str
    spec: NodeSpec
    params: dict[str, Any]
    pos: tuple[float, float] = (0.0, 0.0)
    label: str = ""
    disabled: bool = False  # honored by the GUI/engine in Phase 1 (STATUS.md)

    def __post_init__(self) -> None:
        if not self.label:
            self.label = self.spec.label


@dataclass
class GraphListener:
    on_topology: Callable[[], None] | None = None
    on_param: Callable[[str, str], None] | None = None  # (node_id, param_name)


class Graph:
    def __init__(self) -> None:
        self.nodes: dict[str, NodeInstance] = {}
        self.edges: list[Edge] = []
        self._listeners: list[GraphListener] = []
        # adjacency caches, rebuilt on topology change
        self._out: dict[str, set[str]] = {}
        self._in: dict[str, set[str]] = {}

    # ---- listeners -------------------------------------------------------
    def add_listener(self, listener: GraphListener) -> None:
        self._listeners.append(listener)

    def _notify_topology(self) -> None:
        self._rebuild_adjacency()
        for listener in self._listeners:
            if listener.on_topology:
                listener.on_topology()

    def _notify_param(self, node_id: str, name: str) -> None:
        for listener in self._listeners:
            if listener.on_param:
                listener.on_param(node_id, name)

    # ---- node operations ---------------------------------------------------
    def add_node(
        self,
        spec: NodeSpec,
        *,
        params: dict[str, Any] | None = None,
        pos: tuple[float, float] = (0.0, 0.0),
        node_id: str | None = None,
        label: str = "",
    ) -> NodeInstance:
        nid = node_id or uuid.uuid4().hex[:8]
        if nid in self.nodes:
            raise GraphError(f"duplicate node id {nid!r}")
        values = validate_params(spec.params, params or {})
        inst = NodeInstance(id=nid, spec=spec, params=values, pos=pos, label=label)
        self.nodes[nid] = inst
        self._notify_topology()
        return inst

    def remove_node(self, node_id: str) -> None:
        self._require(node_id)
        self.edges = [e for e in self.edges
                      if e.src[0] != node_id and e.dst[0] != node_id]
        del self.nodes[node_id]
        self._notify_topology()

    def set_param(self, node_id: str, name: str, value: Any) -> Any:
        inst = self._require(node_id)
        spec = next((p for p in inst.spec.params if p.name == name), None)
        if spec is None:
            raise GraphError(f"{inst.spec.type_id} has no parameter {name!r}")
        validated = spec.validate(value)
        inst.params[name] = validated
        self._notify_param(node_id, name)
        return validated

    # ---- edge operations -----------------------------------------------
    def connect(self, src_id: str, src_port: str, dst_id: str, dst_port: str) -> Edge:
        src_node, dst_node = self._require(src_id), self._require(dst_id)
        out_decl = src_node.spec.output(src_port)
        in_decl = dst_node.spec.input(dst_port)

        if src_id == dst_id:
            raise CycleError("cannot connect a node to itself")
        if dst_id in self.ancestors({src_id}):
            raise CycleError(
                f"connecting {src_id}.{src_port} → {dst_id}.{dst_port} would create a cycle"
            )

        result = check_connection(out_decl.dtype, in_decl.dtype)
        if isinstance(result, Reject):
            raise ConnectionTypeError(
                f"{dst_node.label}.{dst_port} {result.reason}", result.hint
            )
        coercion = result if isinstance(result, Coerce) else None

        if not in_decl.variadic:
            self.edges = [e for e in self.edges if e.dst != (dst_id, dst_port)]
        edge = Edge(src=(src_id, src_port), dst=(dst_id, dst_port), coercion=coercion)
        self.edges.append(edge)
        self._notify_topology()
        return edge

    def disconnect(self, edge: Edge) -> None:
        try:
            self.edges.remove(edge)
        except ValueError:
            raise GraphError("edge not in graph") from None
        self._notify_topology()

    def in_edges(self, node_id: str) -> list[Edge]:
        return [e for e in self.edges if e.dst[0] == node_id]

    def edge_into(self, node_id: str, port: str) -> Edge | None:
        for e in self.edges:
            if e.dst == (node_id, port):
                return e
        return None

    # ---- traversal -------------------------------------------------------
    def _rebuild_adjacency(self) -> None:
        self._out = {nid: set() for nid in self.nodes}
        self._in = {nid: set() for nid in self.nodes}
        for e in self.edges:
            self._out[e.src[0]].add(e.dst[0])
            self._in[e.dst[0]].add(e.src[0])

    def ancestors(self, ids: Iterable[str]) -> set[str]:
        if not self._in and self.nodes:
            self._rebuild_adjacency()
        seen: set[str] = set()
        stack = [nid for nid in ids if nid in self.nodes]
        while stack:
            for parent in self._in.get(stack.pop(), ()):
                if parent not in seen:
                    seen.add(parent)
                    stack.append(parent)
        return seen

    def descendants(self, ids: Iterable[str]) -> set[str]:
        if not self._out and self.nodes:
            self._rebuild_adjacency()
        seen: set[str] = set()
        stack = [nid for nid in ids if nid in self.nodes]
        while stack:
            for child in self._out.get(stack.pop(), ()):
                if child not in seen:
                    seen.add(child)
                    stack.append(child)
        return seen

    def topo_order(self, subset: set[str] | None = None) -> list[str]:
        """Kahn's algorithm over ``subset`` (default: whole graph).
        Deterministic tiebreak by node id so runs and reports are stable."""
        nodes = set(self.nodes) if subset is None else {n for n in subset if n in self.nodes}
        indeg = {n: 0 for n in nodes}
        for e in self.edges:
            if e.src[0] in nodes and e.dst[0] in nodes:
                indeg[e.dst[0]] += 1
        ready = sorted(n for n, d in indeg.items() if d == 0)
        order: list[str] = []
        while ready:
            n = ready.pop(0)
            order.append(n)
            for e in self.edges:
                if e.src[0] == n and e.dst[0] in indeg:
                    indeg[e.dst[0]] -= 1
                    if indeg[e.dst[0]] == 0:
                        # insert keeping 'ready' sorted for determinism
                        ready.append(e.dst[0])
                        ready.sort()
        if len(order) != len(nodes):
            raise CycleError("graph contains a cycle")  # defense in depth
        return order

    # ---- misc ------------------------------------------------------------
    def side_effect_nodes(self) -> list[str]:
        return [nid for nid, inst in self.nodes.items()
                if inst.spec.node_class.side_effect]

    def _require(self, node_id: str) -> NodeInstance:
        inst = self.nodes.get(node_id)
        if inst is None:
            raise GraphError(f"no node with id {node_id!r}")
        return inst
