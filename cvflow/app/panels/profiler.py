"""Profiler table — per-node timing, cache, and share of the run (docs/05 §2.5).

Reads the ``RunReport`` the engine already produces; one click on a row jumps
to that node. Sorted by last-ms descending so the slowest node is on top — the
"where is my pipeline slow" answer at a glance.
"""

from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from cvflow.engine.profiling import NodeStatus, RunReport

_HEADERS = ["Node", "Status", "Last ms", "EMA ms", "% run", "Cache", "Bytes"]


class ProfilerPanel(QtWidgets.QTableWidget):
    nodeActivated = QtCore.Signal(str)

    def __init__(self) -> None:
        super().__init__(0, len(_HEADERS))
        self.setHorizontalHeaderLabels(_HEADERS)
        self.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.verticalHeader().setVisible(False)
        self.horizontalHeader().setSectionResizeMode(
            0, QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.setSortingEnabled(True)
        self.cellClicked.connect(self._on_click)

    def update_report(self, report: RunReport) -> None:
        self.setSortingEnabled(False)
        rows = list(report.nodes.items())
        total = sum(m.ms for _, m in rows) or 1.0
        self.setRowCount(len(rows))
        for r, (nid, m) in enumerate(rows):
            pct = 100.0 * m.ms / total
            cache = "hit" if m.cache_hit else ("—" if m.status is NodeStatus.OK else "")
            values = [
                nid, m.status.value, f"{m.ms:.2f}",
                f"{m.ema_ms:.2f}" if m.ema_ms else "",
                f"{pct:.0f}%", cache, _fmt_bytes(m.out_bytes),
            ]
            for c, text in enumerate(values):
                item = QtWidgets.QTableWidgetItem()
                # Numeric columns sort by value, not lexically.
                if c in (2, 3, 4, 6):
                    item.setData(QtCore.Qt.ItemDataRole.DisplayRole, text)
                    item.setData(QtCore.Qt.ItemDataRole.UserRole + 1,
                                 _num(m, c, pct))
                else:
                    item.setText(text)
                if c == 0:
                    item.setData(QtCore.Qt.ItemDataRole.UserRole, nid)
                self.setItem(r, c, item)
        self.setSortingEnabled(True)
        self.sortItems(2, QtCore.Qt.SortOrder.DescendingOrder)

    def _on_click(self, row: int, _col: int) -> None:
        item = self.item(row, 0)
        if item:
            nid = item.data(QtCore.Qt.ItemDataRole.UserRole)
            if nid:
                self.nodeActivated.emit(nid)


def _num(metrics, col: int, pct: float) -> float:
    if col == 2:
        return metrics.ms
    if col == 3:
        return metrics.ema_ms or 0.0
    if col == 4:
        return pct
    return float(metrics.out_bytes)


def _fmt_bytes(n: int) -> str:
    if n <= 0:
        return ""
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"
