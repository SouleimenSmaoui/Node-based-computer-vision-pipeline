"""WorkflowSession — one open document's state (docs/05 §5, docs/06).

Bundles the graph, its ExecutionController, file path / base dir, and the undo
stack. Parameter and label edits are undoable and coalesce to one step per
gesture (the interactive-tuning core of docs/05 §5). Structural undo
(add/remove/connect) is a documented gap for this MVP — STATUS.md.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6 import QtCore, QtGui

from cvflow.app.controllers import ExecutionController
from cvflow.core.graph import Graph
from cvflow.core.registry import NodeRegistry
from cvflow.io.workflow_json import save_workflow


class _ParamCommand(QtGui.QUndoCommand):
    """A single parameter change, already applied live when pushed."""

    def __init__(self, session: "WorkflowSession", node_id: str, name: str,
                 old: Any, new: Any) -> None:
        super().__init__(f"set {node_id}.{name}")
        self._s = session
        self._node_id, self._name = node_id, name
        self._old, self._new = old, new
        self._skip = True  # value is already applied; don't re-run on push

    def redo(self) -> None:
        if self._skip:
            self._skip = False
            return
        self._s._apply_param(self._node_id, self._name, self._new)

    def undo(self) -> None:
        self._s._apply_param(self._node_id, self._name, self._old)


class _RenameCommand(QtGui.QUndoCommand):
    def __init__(self, session: "WorkflowSession", node_id: str,
                 old: str, new: str) -> None:
        super().__init__(f"rename {node_id}")
        self._s, self._node_id, self._old, self._new = session, node_id, old, new

    def redo(self) -> None:
        self._s._apply_label(self._node_id, self._new)

    def undo(self) -> None:
        self._s._apply_label(self._node_id, self._old)


class WorkflowSession(QtCore.QObject):
    dirtyChanged = QtCore.Signal(bool)
    paramReverted = QtCore.Signal(str)   # node_id → inspector should refresh
    labelReverted = QtCore.Signal(str)

    def __init__(self, graph: Graph, registry: NodeRegistry, *,
                 path: str | None = None, base_dir: str | None = None,
                 metadata: dict | None = None, ui: dict | None = None) -> None:
        super().__init__()
        self.graph = graph
        self.registry = registry
        self.path = path
        self.base_dir = base_dir
        self.metadata = dict(metadata or {})
        self.ui = dict(ui or {})
        self._dirty = False

        self.controller = ExecutionController(graph, base_dir=base_dir, parent=self)
        self.undo = QtGui.QUndoStack(self)

    # ---- live param editing (from the inspector) --------------------------
    def set_param_live(self, node_id: str, name: str, value: Any) -> Any:
        validated = self.graph.set_param(node_id, name, value)
        self.controller.schedule()
        self.mark_dirty()
        return validated

    def commit_param(self, node_id: str, name: str, old: Any, new: Any) -> None:
        self.undo.push(_ParamCommand(self, node_id, name, old, new))

    def commit_label(self, node_id: str, new_label: str) -> None:
        inst = self.graph.nodes.get(node_id)
        if inst is None or inst.label == new_label:
            return
        self.undo.push(_RenameCommand(self, node_id, inst.label, new_label))

    # ---- applied by undo commands -----------------------------------------
    def _apply_param(self, node_id: str, name: str, value: Any) -> None:
        if node_id in self.graph.nodes:
            self.graph.set_param(node_id, name, value)
            self.controller.schedule()
            self.mark_dirty()
            self.paramReverted.emit(node_id)

    def _apply_label(self, node_id: str, label: str) -> None:
        inst = self.graph.nodes.get(node_id)
        if inst is not None:
            inst.label = label
            self.mark_dirty()
            self.labelReverted.emit(node_id)

    # ---- persistence ------------------------------------------------------
    def save(self, path: str | None = None, ui: dict | None = None) -> None:
        target = path or self.path
        if not target:
            raise ValueError("no path to save to")
        save_workflow(self.graph, target, metadata=self.metadata, ui=ui or self.ui)
        self.path = target
        self.base_dir = str(Path(target).parent)
        self.controller.service.resources.base_dir = self.base_dir
        self.mark_clean()

    # ---- dirty tracking ---------------------------------------------------
    def mark_dirty(self) -> None:
        if not self._dirty:
            self._dirty = True
            self.dirtyChanged.emit(True)

    def mark_clean(self) -> None:
        if self._dirty:
            self._dirty = False
            self.dirtyChanged.emit(False)

    @property
    def dirty(self) -> bool:
        return self._dirty

    @property
    def title(self) -> str:
        base = Path(self.path).name if self.path else "untitled"
        return f"{'*' if self._dirty else ''}{base}"

    def shutdown(self) -> None:
        self.controller.shutdown()
