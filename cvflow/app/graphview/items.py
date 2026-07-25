"""QGraphicsItems for the node editor: NodeItem, PortItem, EdgeItem (docs/05 §2.2).

Node visuals follow the design doc: header tinted by category, a status LED
(glyph + colour, never colour alone), a right-aligned last-timing label, and a
side-effect 💾 badge. Wires are bezier, coloured by data kind, with a coercion
badge dot when the engine auto-inserts an adapter (docs/03 §6).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6 import QtCore, QtGui, QtWidgets

from cvflow.app.theme import (
    NODE_BODY,
    STATUS_COLORS,
    TEXT,
    TEXT_DIM,
    category_color,
    kind_color,
)
from cvflow.core.graph import Edge, NodeInstance
from cvflow.core.ports import PortDecl
from cvflow.engine.profiling import NodeStatus

if TYPE_CHECKING:  # pragma: no cover
    from cvflow.app.graphview.scene import GraphScene

NODE_WIDTH = 172.0
HEADER_H = 24.0
PORT_ROW_H = 20.0
PORT_R = 5.0
BODY_PAD = 10.0

_STATUS_GLYPH = {
    NodeStatus.OK: "●", NodeStatus.CACHED: "◐", NodeStatus.ERROR: "✕",
    NodeStatus.CONFIG_ERROR: "⚠", NodeStatus.BLOCKED: "▲",
    NodeStatus.SKIPPED: "·", NodeStatus.CANCELLED: "·",
}
_STATUS_KEY = {
    NodeStatus.OK: "ok", NodeStatus.CACHED: "cached", NodeStatus.ERROR: "error",
    NodeStatus.CONFIG_ERROR: "warning", NodeStatus.BLOCKED: "blocked",
    NodeStatus.SKIPPED: "skipped", NodeStatus.CANCELLED: "idle",
}


class PortItem(QtWidgets.QGraphicsEllipseItem):
    """A connection anchor on a node edge."""

    def __init__(self, node: "NodeItem", decl: PortDecl, direction: str) -> None:
        super().__init__(-PORT_R, -PORT_R, 2 * PORT_R, 2 * PORT_R, node)
        self.node_item = node
        self.decl = decl
        self.direction = direction  # 'in' | 'out'
        self.setBrush(QtGui.QBrush(kind_color(decl.dtype.kind)))
        self.setPen(QtGui.QPen(QtGui.QColor("#1e1e1e"), 1))
        self.setZValue(2)
        self.setAcceptHoverEvents(True)
        self.setToolTip(f"{decl.label}  ({decl.dtype.label()})")

    @property
    def anchor(self) -> QtCore.QPointF:
        return self.scenePos()

    def hoverEnterEvent(self, event: QtGui.QHoverEvent) -> None:
        self.setPen(QtGui.QPen(QtGui.QColor("#ffffff"), 1.5))
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event: QtGui.QHoverEvent) -> None:
        self.setPen(QtGui.QPen(QtGui.QColor("#1e1e1e"), 1))
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            scene: GraphScene = self.scene()  # type: ignore[assignment]
            scene.begin_wire(self, event.scenePos())
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        scene: GraphScene = self.scene()  # type: ignore[assignment]
        if scene is not None and scene.is_wiring():
            scene.update_wire(event.scenePos())
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        scene: GraphScene = self.scene()  # type: ignore[assignment]
        if scene is not None and scene.is_wiring():
            scene.finish_wire(event.scenePos())
            event.accept()
        else:
            super().mouseReleaseEvent(event)


class NodeItem(QtWidgets.QGraphicsObject):
    """One node: movable, selectable, self-laying-out its ports."""

    def __init__(self, inst: NodeInstance) -> None:
        super().__init__()
        self.inst = inst
        self.node_id = inst.id
        self._status: NodeStatus | None = None
        self._timing = ""
        self.in_ports: dict[str, PortItem] = {}
        self.out_ports: dict[str, PortItem] = {}

        self.setFlags(
            QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.setZValue(1)
        self.setPos(inst.pos[0], inst.pos[1])
        self._build_ports()

    # ---- geometry ---------------------------------------------------------
    def _rows(self) -> int:
        return max(len(self.inst.spec.inputs), len(self.inst.spec.outputs), 1)

    def _height(self) -> float:
        return HEADER_H + self._rows() * PORT_ROW_H + BODY_PAD

    def boundingRect(self) -> QtCore.QRectF:
        return QtCore.QRectF(0, 0, NODE_WIDTH, self._height()).adjusted(-2, -2, 2, 2)

    def _build_ports(self) -> None:
        y0 = HEADER_H + PORT_ROW_H / 2 + 2
        for i, decl in enumerate(self.inst.spec.inputs):
            port = PortItem(self, decl, "in")
            port.setPos(0, y0 + i * PORT_ROW_H)
            self.in_ports[decl.name] = port
        for i, decl in enumerate(self.inst.spec.outputs):
            port = PortItem(self, decl, "out")
            port.setPos(NODE_WIDTH, y0 + i * PORT_ROW_H)
            self.out_ports[decl.name] = port

    # ---- status -----------------------------------------------------------
    def set_status(self, status: NodeStatus, timing: str) -> None:
        self._status = status
        self._timing = timing
        self.update()

    # ---- painting ---------------------------------------------------------
    def paint(self, painter: QtGui.QPainter, option, widget=None) -> None:
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        h = self._height()
        body = QtCore.QRectF(0, 0, NODE_WIDTH, h)

        # Body.
        painter.setBrush(QtGui.QColor(NODE_BODY))
        border = QtGui.QColor("#e0e0e0") if self.isSelected() else QtGui.QColor("#1c1c1c")
        painter.setPen(QtGui.QPen(border, 2 if self.isSelected() else 1))
        painter.drawRoundedRect(body, 6, 6)

        # Header band.
        header = QtCore.QRectF(0, 0, NODE_WIDTH, HEADER_H)
        path = QtGui.QPainterPath()
        path.addRoundedRect(header, 6, 6)
        path.addRect(0, HEADER_H - 8, NODE_WIDTH, 8)
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        tint = category_color(self.inst.spec.category)
        painter.fillPath(path, tint.darker(140))

        # Title + side-effect badge.
        painter.setPen(QtGui.QColor(TEXT))
        font = painter.font(); font.setBold(True); painter.setFont(font)
        badge = " 💾" if self.inst.spec.node_class.side_effect else ""
        title = QtGui.QFontMetrics(font).elidedText(
            self.inst.label + badge, QtCore.Qt.TextElideMode.ElideRight, int(NODE_WIDTH - 34))
        painter.drawText(QtCore.QRectF(8, 0, NODE_WIDTH - 34, HEADER_H),
                         QtCore.Qt.AlignmentFlag.AlignVCenter, title)

        # Status LED.
        if self._status is not None:
            key = _STATUS_KEY.get(self._status, "idle")
            painter.setPen(QtGui.QColor(STATUS_COLORS[key]))
            painter.drawText(QtCore.QRectF(NODE_WIDTH - 24, 0, 20, HEADER_H),
                             QtCore.Qt.AlignmentFlag.AlignCenter,
                             _STATUS_GLYPH.get(self._status, "·"))

        # Port labels + timing.
        painter.setFont(QtGui.QFont(painter.font().family(), 8, QtGui.QFont.Weight.Normal))
        painter.setPen(QtGui.QColor(TEXT_DIM))
        for name, port in self.in_ports.items():
            y = port.pos().y()
            painter.drawText(QtCore.QRectF(10, y - PORT_ROW_H / 2, NODE_WIDTH / 2, PORT_ROW_H),
                             QtCore.Qt.AlignmentFlag.AlignVCenter, port.decl.label)
        for name, port in self.out_ports.items():
            y = port.pos().y()
            painter.drawText(QtCore.QRectF(NODE_WIDTH / 2 - 10, y - PORT_ROW_H / 2,
                                           NODE_WIDTH / 2, PORT_ROW_H),
                             QtCore.Qt.AlignmentFlag.AlignVCenter
                             | QtCore.Qt.AlignmentFlag.AlignRight, port.decl.label)
        if self._timing:
            painter.setPen(QtGui.QColor(TEXT_DIM))
            painter.drawText(QtCore.QRectF(0, h - 14, NODE_WIDTH - 8, 12),
                             QtCore.Qt.AlignmentFlag.AlignRight, self._timing)

    def itemChange(self, change, value):
        if change == QtWidgets.QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            self.inst.pos = (self.pos().x(), self.pos().y())
            scene = self.scene()
            if scene is not None:
                scene.on_node_moved(self.node_id)  # type: ignore[attr-defined]
        return super().itemChange(change, value)


class EdgeItem(QtWidgets.QGraphicsPathItem):
    """A bezier wire between an output port and an input port."""

    def __init__(self, edge: Edge, src_port: PortItem, dst_port: PortItem) -> None:
        super().__init__()
        self.edge = edge
        self.src_port = src_port
        self.dst_port = dst_port
        self.setZValue(0)
        self.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        color = kind_color(src_port.decl.dtype.kind)
        self._pen = QtGui.QPen(color, 2)
        self._pen.setCosmetic(False)
        self.setPen(self._pen)
        self.update_path()

    def update_path(self) -> None:
        a = self.src_port.anchor
        b = self.dst_port.anchor
        dx = max(40.0, abs(b.x() - a.x()) * 0.5)
        path = QtGui.QPainterPath(a)
        path.cubicTo(a.x() + dx, a.y(), b.x() - dx, b.y(), b.x(), b.y())
        self.setPath(path)

    def paint(self, painter: QtGui.QPainter, option, widget=None) -> None:
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        pen = QtGui.QPen(self._pen)
        if self.isSelected():
            pen.setColor(QtGui.QColor("#ffffff"))
            pen.setWidthF(2.5)
        painter.setPen(pen)
        painter.drawPath(self.path())
        # Coercion badge dot at the midpoint (docs/03 §6).
        if self.edge.coercion is not None:
            mid = self.path().pointAtPercent(0.5)
            painter.setBrush(QtGui.QColor("#f0e442"))
            painter.setPen(QtGui.QPen(QtGui.QColor("#1e1e1e"), 1))
            painter.drawEllipse(mid, 4, 4)
