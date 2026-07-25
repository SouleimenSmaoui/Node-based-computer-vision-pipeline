"""GraphScene — the bridge between the framework-free ``core.Graph`` and the
QGraphicsItems that render it (docs/05 §2.2).

The graph is authoritative. The scene listens for topology changes (via a
``GraphListener``) and reconciles items to match; it never holds state the graph
doesn't. Structural edits are routed through ``mutator`` (the ExecutionController's
serialized :meth:`mutate`) so the engine never sees a half-edited graph.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from PySide6 import QtCore, QtGui, QtWidgets

from cvflow.app.graphview.items import EdgeItem, NodeItem, PortItem
from cvflow.app.theme import kind_color
from cvflow.core.errors import ConnectionTypeError, CycleError, GraphError
from cvflow.core.graph import Graph, GraphListener, NodeInstance
from cvflow.core.node import NodeSpec
from cvflow.engine.profiling import NodeMetrics

Mutator = Callable[[Callable[[], Any]], Any]


class GraphScene(QtWidgets.QGraphicsScene):
    nodeSelected = QtCore.Signal(object)        # node_id or None
    connectionRejected = QtCore.Signal(str)     # reason for the status bar

    def __init__(self, graph: Graph, mutator: Mutator) -> None:
        super().__init__()
        self.graph = graph
        self.mutate = mutator
        self.setSceneRect(-5000, -5000, 10000, 10000)
        self._nodes: dict[str, NodeItem] = {}
        self._edges: list[EdgeItem] = []

        self._wire_src: Optional[PortItem] = None
        self._temp_wire: Optional[QtWidgets.QGraphicsPathItem] = None

        graph.add_listener(GraphListener(on_topology=self._on_topology))
        self.selectionChanged.connect(self._on_selection)
        self.rebuild()

    # ---- building ---------------------------------------------------------
    def rebuild(self) -> None:
        for item in list(self._nodes.values()):
            self.removeItem(item)
        self._nodes.clear()
        for nid in self.graph.nodes:
            self._add_node_item(self.graph.nodes[nid])
        self._rebuild_edges()

    def _add_node_item(self, inst: NodeInstance) -> NodeItem:
        item = NodeItem(inst)
        self.addItem(item)
        self._nodes[inst.id] = item
        return item

    def _on_topology(self) -> None:
        # Reconcile: keep existing NodeItems (preserves drag positions/selection),
        # add new ones, drop removed ones. Edges are cheap → rebuilt wholesale.
        current = set(self.graph.nodes)
        for nid in list(self._nodes):
            if nid not in current:
                self.removeItem(self._nodes.pop(nid))
        for nid in current:
            if nid not in self._nodes:
                self._add_node_item(self.graph.nodes[nid])
        self._rebuild_edges()

    def _rebuild_edges(self) -> None:
        for e in self._edges:
            self.removeItem(e)
        self._edges.clear()
        for edge in self.graph.edges:
            src_item = self._nodes.get(edge.src[0])
            dst_item = self._nodes.get(edge.dst[0])
            if not src_item or not dst_item:
                continue
            src_port = src_item.out_ports.get(edge.src[1])
            dst_port = dst_item.in_ports.get(edge.dst[1])
            if not src_port or not dst_port:
                continue
            item = EdgeItem(edge, src_port, dst_port)
            self.addItem(item)
            self._edges.append(item)

    def on_node_moved(self, node_id: str) -> None:
        for e in self._edges:
            if e.edge.src[0] == node_id or e.edge.dst[0] == node_id:
                e.update_path()

    # ---- node creation / deletion -----------------------------------------
    def add_node_type(self, spec: NodeSpec, pos: QtCore.QPointF) -> Optional[str]:
        inst = self.mutate(lambda: self.graph.add_node(spec, pos=(pos.x(), pos.y())))
        if inst is None:
            return None
        self.clearSelection()
        item = self._nodes.get(inst.id)
        if item:
            item.setSelected(True)
        return inst.id

    def delete_selected(self) -> None:
        node_ids = [it.node_id for it in self.selectedItems() if isinstance(it, NodeItem)]
        edges = [it.edge for it in self.selectedItems() if isinstance(it, EdgeItem)]
        if not node_ids and not edges:
            return

        def apply() -> None:
            for edge in edges:
                try:
                    self.graph.disconnect(edge)
                except GraphError:
                    pass
            for nid in node_ids:
                if nid in self.graph.nodes:
                    self.graph.remove_node(nid)

        self.mutate(apply)

    # ---- wiring -----------------------------------------------------------
    def is_wiring(self) -> bool:
        return self._wire_src is not None

    def begin_wire(self, port: PortItem, pos: QtCore.QPointF) -> None:
        self._wire_src = port
        self._temp_wire = QtWidgets.QGraphicsPathItem()
        pen = QtGui.QPen(kind_color(port.decl.dtype.kind), 2, QtCore.Qt.PenStyle.DashLine)
        self._temp_wire.setPen(pen)
        self._temp_wire.setZValue(3)
        self.addItem(self._temp_wire)
        self.update_wire(pos)

    def update_wire(self, pos: QtCore.QPointF) -> None:
        if self._wire_src is None or self._temp_wire is None:
            return
        a = self._wire_src.anchor
        dx = max(40.0, abs(pos.x() - a.x()) * 0.5)
        path = QtGui.QPainterPath(a)
        path.cubicTo(a.x() + dx, a.y(), pos.x() - dx, pos.y(), pos.x(), pos.y())
        self._temp_wire.setPath(path)

    def finish_wire(self, pos: QtCore.QPointF) -> None:
        src = self._wire_src
        self._cancel_wire()
        if src is None:
            return
        target = self._port_at(pos)
        if target is None or target is src:
            return
        if target.direction == src.direction:
            self.connectionRejected.emit(
                "connect an output to an input (not two of the same kind)")
            return
        out_port, in_port = (src, target) if src.direction == "out" else (target, src)
        self._try_connect(out_port, in_port)

    def _try_connect(self, out_port: PortItem, in_port: PortItem) -> None:
        s_node = out_port.node_item.node_id
        d_node = in_port.node_item.node_id
        try:
            self.mutate(lambda: self.graph.connect(
                s_node, out_port.decl.name, d_node, in_port.decl.name))
        except (ConnectionTypeError, CycleError, GraphError) as exc:
            # ConnectionTypeError.__str__ already folds in the fix hint.
            self.connectionRejected.emit(str(exc))

    def _cancel_wire(self) -> None:
        if self._temp_wire is not None:
            self.removeItem(self._temp_wire)
        self._temp_wire = None
        self._wire_src = None

    def _port_at(self, pos: QtCore.QPointF) -> Optional[PortItem]:
        for item in self.items(pos):
            if isinstance(item, PortItem):
                return item
        return None

    # ---- status from run reports ------------------------------------------
    def apply_status(self, node_id: str, metrics: NodeMetrics) -> None:
        item = self._nodes.get(node_id)
        if item is None:
            return
        ms = metrics.ms or (metrics.ema_ms or 0.0)
        timing = f"{ms:.1f} ms" if ms else ""
        item.set_status(metrics.status, timing)

    def select_node(self, node_id: str) -> None:
        self.clearSelection()
        item = self._nodes.get(node_id)
        if item:
            item.setSelected(True)
            self.nodeSelected.emit(node_id)

    def node_item(self, node_id: str) -> Optional[NodeItem]:
        return self._nodes.get(node_id)

    # ---- selection --------------------------------------------------------
    def _on_selection(self) -> None:
        nodes = [it for it in self.selectedItems() if isinstance(it, NodeItem)]
        self.nodeSelected.emit(nodes[-1].node_id if nodes else None)
