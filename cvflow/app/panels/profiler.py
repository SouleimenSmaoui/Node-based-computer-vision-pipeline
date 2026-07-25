"""Profiler table — per-node timing, cache, and share of the run (docs/05 §2.5).

Reads the ``RunReport`` the engine already produces; one click on a row jumps
to that node. Sorted by last-ms descending so the slowest node is on top — the
"where is my pipeline slow" answer at a glance.
"""

from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from cvflow.engine.profiling import NodeStatus, RunReport

_HEADERS = ["Node", "Status", "Last ms", "EMA ms", "% run", "Cache", "Bytes"]


class _NumericItem(QtWidgets.QTableWidgetItem):
    """Shows formatted text but sorts by the underlying number.

    ``QTableWidgetItem.__lt__`` compares the DisplayRole *string*, so storing
    the formatted value made "102.35" sort before "9.50" and put the slowest
    node at the bottom of a descending sort — the exact opposite of what this
    panel is for (CODE_REVIEW §1.3).
    """

    def __init__(self, text: str, value: float) -> None:
        super().__init__(text)
        self._value = value

    def __lt__(self, other: QtWidgets.QTableWidgetItem) -> bool:
        if isinstance(other, _NumericItem):
            return self._value < other._value
        return super().__lt__(other)


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
            # Numeric columns sort by value, not lexically.
            numeric = {2: m.ms, 3: m.ema_ms or 0.0, 4: pct, 6: float(m.out_bytes)}
            for c, text in enumerate(values):
                if c in numeric:
                    item = _NumericItem(text, numeric[c])
                else:
                    item = QtWidgets.QTableWidgetItem(text)
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


def _fmt_bytes(n: int) -> str:
    if n <= 0:
        return ""
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"
