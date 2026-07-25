"""GraphView — pan/zoom canvas with box-select, delete, context menu, Tab
quick-add, and palette drag-drop (docs/05 §2.2, §4).

Tab quick-add is the headline speed win (docs/05 §2.1): press Tab, fuzzy-search,
Enter — the node is inserted and, if a node was selected, auto-wired output→
first-compatible-input.
"""

from __future__ import annotations

from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets

from cvflow.app.graphview.items import EdgeItem, NodeItem
from cvflow.app.graphview.palette import MIME_NODE
from cvflow.app.graphview.scene import GraphScene
from cvflow.app.theme import GRID, SURFACE
from cvflow.core.registry import NodeRegistry
from cvflow.core.types.base import Reject, check_connection

_ZOOM_STEP = 1.15
_MIN_SCALE = 0.15
_MAX_SCALE = 4.0


class GraphView(QtWidgets.QGraphicsView):
    viewRequested = QtCore.Signal(str, str)   # (node_id, "A" | "B")
    statusMessage = QtCore.Signal(str)

    def __init__(self, scene: GraphScene, registry: NodeRegistry) -> None:
        super().__init__(scene)
        self._graph_scene = scene
        self.registry = registry
        self._last_scene_pos = QtCore.QPointF(0, 0)
        self._panning = False
        self._pan_from = QtCore.QPoint(0, 0)

        self.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        self.setDragMode(QtWidgets.QGraphicsView.DragMode.RubberBandDrag)
        self.setTransformationAnchor(QtWidgets.QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QtWidgets.QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setBackgroundBrush(QtGui.QColor(SURFACE))
        self.setAcceptDrops(True)
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)

    # ---- background grid --------------------------------------------------
    def drawBackground(self, painter: QtGui.QPainter, rect: QtCore.QRectF) -> None:
        super().drawBackground(painter, rect)
        step = 48
        pen = QtGui.QPen(QtGui.QColor(GRID), 1)
        painter.setPen(pen)
        left = int(rect.left()) - (int(rect.left()) % step)
        top = int(rect.top()) - (int(rect.top()) % step)
        x = left
        while x < rect.right():
            painter.drawLine(x, int(rect.top()), x, int(rect.bottom()))
            x += step
        y = top
        while y < rect.bottom():
            painter.drawLine(int(rect.left()), y, int(rect.right()), y)
            y += step

    # ---- navigation -------------------------------------------------------
    def wheelEvent(self, event: QtGui.QWheelEvent) -> None:
        factor = _ZOOM_STEP if event.angleDelta().y() > 0 else 1 / _ZOOM_STEP
        scale = self.transform().m11() * factor
        if _MIN_SCALE <= scale <= _MAX_SCALE:
            self.scale(factor, factor)

    # Middle-button pan scrolls directly rather than synthesizing left-button
    # events into ScrollHandDrag. The old trick used the 5-arg QMouseEvent
    # constructor, deprecated in Qt 6 (a warning per click) and due for removal;
    # it also depended on ScrollHandDrag's internals (CODE_REVIEW §2.5).
    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.button() == QtCore.Qt.MouseButton.MiddleButton:
            self._panning = True
            self._pan_from = event.position().toPoint()
            self.viewport().setCursor(QtCore.Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        if self._panning and event.button() == QtCore.Qt.MouseButton.MiddleButton:
            self._panning = False
            self.viewport().unsetCursor()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        self._last_scene_pos = self.mapToScene(event.position().toPoint())
        if self._panning:
            # Integer viewport coords throughout, so repeated moves can't
            # accumulate sub-pixel drift.
            pos = event.position().toPoint()
            delta = pos - self._pan_from
            self._pan_from = pos
            h, v = self.horizontalScrollBar(), self.verticalScrollBar()
            h.setValue(h.value() - delta.x())
            v.setValue(v.value() - delta.y())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def fit_all(self) -> None:
        rect = self._graph_scene.itemsBoundingRect()
        if not rect.isEmpty():
            self.fitInView(rect.adjusted(-40, -40, 40, 40),
                           QtCore.Qt.AspectRatioMode.KeepAspectRatio)

    # ---- keys -------------------------------------------------------------
    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        key = event.key()
        if key in (QtCore.Qt.Key.Key_Delete, QtCore.Qt.Key.Key_Backspace):
            self._graph_scene.delete_selected()
        elif key == QtCore.Qt.Key.Key_Tab:
            self.open_quick_add()
        elif key == QtCore.Qt.Key.Key_F:
            self.fit_all()
        else:
            super().keyPressEvent(event)

    # ---- quick add --------------------------------------------------------
    def open_quick_add(self) -> None:
        popup = _QuickAdd(self.registry, self)
        popup.chosen.connect(lambda spec: self._insert(spec, self._last_scene_pos))
        popup.move(QtGui.QCursor.pos())
        popup.show()
        popup.focus_search()

    def _insert(self, spec, scene_pos: QtCore.QPointF) -> None:
        selected = [it for it in self._graph_scene.selectedItems() if isinstance(it, NodeItem)]
        src_id = selected[-1].node_id if selected else None
        new_id = self._graph_scene.add_node_type(spec, scene_pos)
        if new_id and src_id:
            self._auto_wire(src_id, new_id)

    def _auto_wire(self, src_id: str, dst_id: str) -> None:
        graph = self._graph_scene.graph
        src = graph.nodes.get(src_id)
        dst = graph.nodes.get(dst_id)
        if not src or not dst or not src.spec.outputs:
            return
        for out in src.spec.outputs:
            for inp in dst.spec.inputs:
                if not isinstance(check_connection(out.dtype, inp.dtype), Reject):
                    try:
                        self._graph_scene.mutate(lambda o=out, i=inp: graph.connect(
                            src_id, o.name, dst_id, i.name))
                        return
                    except Exception:
                        continue

    # ---- drag & drop from the palette -------------------------------------
    def dragEnterEvent(self, event: QtGui.QDragEnterEvent) -> None:
        if event.mimeData().hasFormat(MIME_NODE):
            event.acceptProposedAction()

    def dragMoveEvent(self, event: QtGui.QDragMoveEvent) -> None:
        if event.mimeData().hasFormat(MIME_NODE):
            event.acceptProposedAction()

    def dropEvent(self, event: QtGui.QDropEvent) -> None:
        data = event.mimeData().data(MIME_NODE)
        type_id = bytes(data).decode("utf-8")
        if self.registry.has(type_id):
            pos = self.mapToScene(event.position().toPoint())
            self._graph_scene.add_node_type(self.registry.get(type_id), pos)
            event.acceptProposedAction()

    # ---- context menu -----------------------------------------------------
    def contextMenuEvent(self, event: QtGui.QContextMenuEvent) -> None:
        scene_pos = self.mapToScene(event.pos())
        item = self._node_under(event.pos())
        menu = QtWidgets.QMenu(self)
        if item is not None:
            if not item.isSelected():
                self._graph_scene.select_node(item.node_id)
            menu.addAction("Open in Viewer A", lambda: self.viewRequested.emit(item.node_id, "A"))
            menu.addAction("Open in Viewer B", lambda: self.viewRequested.emit(item.node_id, "B"))
            menu.addSeparator()
            menu.addAction("Delete", self._graph_scene.delete_selected)
        else:
            menu.addAction("Add node…", self.open_quick_add)
            menu.addAction("Fit view", self.fit_all)
        menu.exec(event.globalPos())

    def _node_under(self, viewport_pos: QtCore.QPoint) -> Optional[NodeItem]:
        for it in self.items(viewport_pos):
            if isinstance(it, NodeItem):
                return it
        return None


class _QuickAdd(QtWidgets.QFrame):
    """Floating fuzzy-search inserter (Tab menu)."""

    chosen = QtCore.Signal(object)   # NodeSpec

    def __init__(self, registry: NodeRegistry, parent: QtWidgets.QWidget) -> None:
        super().__init__(parent, QtCore.Qt.WindowType.Popup)
        self.registry = registry
        self.setFixedWidth(280)
        self.setFrameShape(QtWidgets.QFrame.Shape.StyledPanel)

        self.search = QtWidgets.QLineEdit()
        self.search.setPlaceholderText("add node…")
        self.list = QtWidgets.QListWidget()
        self.list.setMaximumHeight(260)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.addWidget(self.search)
        layout.addWidget(self.list)

        self.search.textChanged.connect(self._filter)
        self.search.returnPressed.connect(self._accept_current)
        self.list.itemActivated.connect(lambda _: self._accept_current())
        self.list.itemClicked.connect(lambda _: self._accept_current())
        self.search.installEventFilter(self)
        self._filter("")

    def focus_search(self) -> None:
        self.search.setFocus()

    def _filter(self, text: str) -> None:
        self.list.clear()
        specs = self.registry.search(text) if text.strip() else self.registry.all_specs()
        for spec in specs[:60]:
            item = QtWidgets.QListWidgetItem(f"{spec.label}   ·  {spec.category}")
            item.setData(QtCore.Qt.ItemDataRole.UserRole, spec.type_id)
            self.list.addItem(item)
        if self.list.count():
            self.list.setCurrentRow(0)

    def eventFilter(self, obj, event):
        if obj is self.search and event.type() == QtCore.QEvent.Type.KeyPress:
            key = event.key()
            if key in (QtCore.Qt.Key.Key_Down, QtCore.Qt.Key.Key_Up):
                row = self.list.currentRow()
                row += 1 if key == QtCore.Qt.Key.Key_Down else -1
                self.list.setCurrentRow(max(0, min(row, self.list.count() - 1)))
                return True
        return super().eventFilter(obj, event)

    def _accept_current(self) -> None:
        item = self.list.currentItem()
        if item is None:
            return
        type_id = item.data(QtCore.Qt.ItemDataRole.UserRole)
        if self.registry.has(type_id):
            self.chosen.emit(self.registry.get(type_id))
        self.close()
