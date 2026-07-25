"""InspectorPanel — the auto-generated parameter editor (docs/05 §2.3).

Given a ``NodeInstance`` it builds a form from the node's ``ParamSpec``s, shows
the node's label/id/status/timing, and turns widget edits into two streams:
live ``paramEdited`` (drives the debounced re-run) and once-per-gesture
``paramCommitted`` (the undo granularity).
"""

from __future__ import annotations

from typing import Any

from PySide6 import QtCore, QtWidgets

from cvflow.app.inspector.widgets import ParamWidget, build_param_widget
from cvflow.app.theme import STATUS_COLORS, TEXT_DIM
from cvflow.core.graph import NodeInstance
from cvflow.engine.profiling import NodeMetrics, NodeStatus

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


class InspectorPanel(QtWidgets.QWidget):
    paramEdited = QtCore.Signal(str, str, object)          # node_id, name, value
    paramCommitted = QtCore.Signal(str, str, object, object)  # node_id, name, old, new
    labelEdited = QtCore.Signal(str, str)                  # node_id, new_label

    def __init__(self) -> None:
        super().__init__()
        self._inst: NodeInstance | None = None
        self._widgets: dict[str, ParamWidget] = {}
        self._committed: dict[str, Any] = {}

        self._title = QtWidgets.QLineEdit()
        self._title.setPlaceholderText("node label")
        self._title.editingFinished.connect(self._on_rename)
        self._subtitle = QtWidgets.QLabel("")
        self._subtitle.setStyleSheet(f"color:{TEXT_DIM};")
        self._status = QtWidgets.QLabel("")
        self._doc = QtWidgets.QLabel("")
        self._doc.setWordWrap(True)
        self._doc.setStyleSheet(f"color:{TEXT_DIM}; padding-top:6px;")

        header = QtWidgets.QVBoxLayout()
        header.setSpacing(2)
        header.addWidget(self._title)
        srow = QtWidgets.QHBoxLayout()
        srow.addWidget(self._subtitle, 1)
        srow.addWidget(self._status)
        header.addLayout(srow)

        self._form_host = QtWidgets.QWidget()
        self._form = QtWidgets.QFormLayout(self._form_host)
        self._form.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
        self._form.setFieldGrowthPolicy(
            QtWidgets.QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)

        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self._form_host)

        self._placeholder = QtWidgets.QLabel("Select a node to edit its parameters.")
        self._placeholder.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self._placeholder.setStyleSheet(f"color:{TEXT_DIM};")

        self._stack = QtWidgets.QStackedWidget()
        body = QtWidgets.QWidget()
        blay = QtWidgets.QVBoxLayout(body)
        blay.setContentsMargins(8, 8, 8, 8)
        blay.addLayout(header)
        blay.addWidget(scroll, 1)
        blay.addWidget(self._doc)
        self._stack.addWidget(self._placeholder)
        self._stack.addWidget(body)

        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self._stack)
        self._stack.setCurrentIndex(0)

    # ---- binding ----------------------------------------------------------
    def set_node(self, inst: NodeInstance | None) -> None:
        self._inst = inst
        self._widgets.clear()
        self._committed.clear()
        while self._form.rowCount():
            self._form.removeRow(0)

        if inst is None:
            self._stack.setCurrentIndex(0)
            return
        self._stack.setCurrentIndex(1)
        self._title.setText(inst.label)
        self._subtitle.setText(f"{inst.spec.type_id}  ·  {inst.id}")
        self._status.setText("")
        self._doc.setText(inst.spec.doc)

        for spec in inst.spec.params:
            widget = build_param_widget(spec)
            value = inst.params.get(spec.name, spec.default)
            widget.set_value(value)
            self._committed[spec.name] = value
            widget.edited.connect(lambda v, n=spec.name: self._on_edited(n, v))
            widget.committed.connect(lambda v, n=spec.name: self._on_committed(n, v))
            self._widgets[spec.name] = widget
            self._form.addRow(spec.label, widget)

    def current_node_id(self) -> str | None:
        return self._inst.id if self._inst else None

    def refresh_values(self) -> None:
        """Re-read params into widgets (after an undo/redo or programmatic set)."""
        if self._inst is None:
            return
        for name, widget in self._widgets.items():
            value = self._inst.params.get(name)
            widget.set_value(value)
            self._committed[name] = value
        self._title.setText(self._inst.label)

    def update_status(self, node_id: str, metrics: NodeMetrics) -> None:
        if self._inst is None or node_id != self._inst.id:
            return
        glyph = _STATUS_GLYPH.get(metrics.status, "·")
        color = STATUS_COLORS[_STATUS_KEY.get(metrics.status, "idle")]
        ms = metrics.ms or (metrics.ema_ms or 0.0)
        timing = f"{ms:.1f} ms" if ms else ""
        detail = f"  {metrics.error}" if metrics.error else ""
        self._status.setText(
            f"<span style='color:{color}'>{glyph} {metrics.status.value}</span> {timing}{detail}")

    # ---- events -----------------------------------------------------------
    def _on_edited(self, name: str, value: Any) -> None:
        if self._inst:
            self.paramEdited.emit(self._inst.id, name, value)

    def _on_committed(self, name: str, value: Any) -> None:
        if not self._inst:
            return
        old = self._committed.get(name)
        if value != old:
            self.paramCommitted.emit(self._inst.id, name, old, value)
            self._committed[name] = value

    def _on_rename(self) -> None:
        if self._inst and self._title.text() != self._inst.label:
            self.labelEdited.emit(self._inst.id, self._title.text())
