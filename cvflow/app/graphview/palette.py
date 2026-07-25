"""NodePalette — searchable, drag-to-canvas node list (docs/05 §2.1)."""

from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from cvflow.app.theme import TEXT_DIM, category_color
from cvflow.core.registry import NodeRegistry

MIME_NODE = "application/x-cvflow-node"


class _Tree(QtWidgets.QTreeWidget):
    """Tree that starts a drag carrying a node type id."""

    def startDrag(self, actions: QtCore.Qt.DropAction) -> None:
        item = self.currentItem()
        if item is None:
            return
        type_id = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
        if not type_id:
            return
        mime = QtCore.QMimeData()
        mime.setData(MIME_NODE, type_id.encode("utf-8"))
        drag = QtGui.QDrag(self)
        drag.setMimeData(mime)
        drag.exec(QtCore.Qt.DropAction.CopyAction)


class NodePalette(QtWidgets.QWidget):
    addRequested = QtCore.Signal(object)   # NodeSpec (double-click insert)

    def __init__(self, registry: NodeRegistry) -> None:
        super().__init__()
        self.registry = registry

        self.search = QtWidgets.QLineEdit()
        self.search.setPlaceholderText("search nodes…  🔍")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._repopulate)

        self.tree = _Tree()
        self.tree.setHeaderHidden(True)
        self.tree.setDragEnabled(True)
        self.tree.setRootIsDecorated(True)
        self.tree.itemDoubleClicked.connect(self._on_double_click)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(self.search)
        layout.addWidget(self.tree, 1)
        self._repopulate("")

    def _repopulate(self, text: str) -> None:
        self.tree.clear()
        text = text.strip().lower()
        categories = self.registry.categories()
        for category in sorted(categories):
            specs = [s for s in categories[category]
                     if not text or text in _haystack(s)]
            if not specs:
                continue
            head = QtWidgets.QTreeWidgetItem([category])
            head.setForeground(0, QtGui.QBrush(category_color(category)))
            head.setFlags(QtCore.Qt.ItemFlag.ItemIsEnabled)
            self.tree.addTopLevelItem(head)
            for spec in sorted(specs, key=lambda s: s.label):
                child = QtWidgets.QTreeWidgetItem([spec.label])
                child.setData(0, QtCore.Qt.ItemDataRole.UserRole, spec.type_id)
                child.setToolTip(0, f"{spec.type_id}\n{spec.doc}")
                head.addChild(child)
            head.setExpanded(True)
        if text:
            self.tree.expandAll()

    def _on_double_click(self, item: QtWidgets.QTreeWidgetItem, _col: int) -> None:
        type_id = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
        if type_id and self.registry.has(type_id):
            self.addRequested.emit(self.registry.get(type_id))


def _haystack(spec) -> str:
    return " ".join((spec.label, spec.type_id, spec.category, *spec.keywords)).lower()
