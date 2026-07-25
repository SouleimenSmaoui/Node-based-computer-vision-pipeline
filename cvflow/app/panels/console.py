"""Console log stream and Errors panel (docs/05 §2.5).

Errors render one card per ``NodeError``; clicking a card jumps to the node
(the Flow-3 error-recovery loop). The log bridges Python ``logging`` — which the
engine emits from worker threads — onto the GUI thread via a queued Qt signal.
"""

from __future__ import annotations

import logging

from PySide6 import QtCore, QtGui, QtWidgets

from cvflow.app.theme import STATUS_COLORS, TEXT_DIM
from cvflow.engine.profiling import NodeError


class QtLogHandler(QtCore.QObject, logging.Handler):
    """A logging handler that re-emits records as a thread-safe Qt signal."""

    emitted = QtCore.Signal(str, str)   # (levelname, message)

    def __init__(self) -> None:
        QtCore.QObject.__init__(self)
        logging.Handler.__init__(self)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.emitted.emit(record.levelname, self.format(record))
        except Exception:
            pass


class ConsolePanel(QtWidgets.QPlainTextEdit):
    _COLORS = {"ERROR": "#f85149", "WARNING": "#e3b341", "INFO": TEXT_DIM, "DEBUG": "#6a6a6a"}

    def __init__(self) -> None:
        super().__init__()
        self.setReadOnly(True)
        self.setMaximumBlockCount(2000)
        self.setFont(QtGui.QFont("Consolas", 9))

    def append_line(self, level: str, message: str) -> None:
        color = self._COLORS.get(level, TEXT_DIM)
        self.appendHtml(f"<span style='color:{color}'>{message}</span>")


class ErrorsPanel(QtWidgets.QListWidget):
    nodeActivated = QtCore.Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.setWordWrap(True)
        self.itemClicked.connect(self._on_click)
        self._empty()

    def _empty(self) -> None:
        self.clear()
        item = QtWidgets.QListWidgetItem("No errors.")
        item.setForeground(QtGui.QBrush(QtGui.QColor(STATUS_COLORS["ok"])))
        item.setFlags(QtCore.Qt.ItemFlag.NoItemFlags)
        self.addItem(item)

    def set_errors(self, errors: list[NodeError]) -> None:
        self.clear()
        if not errors:
            self._empty()
            return
        for err in errors:
            text = f"✕  {err.node_id}: {err.message}"
            item = QtWidgets.QListWidgetItem(text)
            item.setForeground(QtGui.QBrush(QtGui.QColor(STATUS_COLORS["error"])))
            item.setData(QtCore.Qt.ItemDataRole.UserRole, err.node_id)
            if err.traceback:
                item.setToolTip(err.traceback)
            self.addItem(item)

    def _on_click(self, item: QtWidgets.QListWidgetItem) -> None:
        nid = item.data(QtCore.Qt.ItemDataRole.UserRole)
        if nid:
            self.nodeActivated.emit(nid)
