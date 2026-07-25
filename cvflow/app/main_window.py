"""MainWindow — docking layout, menus/toolbar, and the signal wiring that turns
the panels into the interactive loop of docs/05.

Everything reacts to the engine through the ExecutionController's Qt signals; the
GUI thread never blocks on a run. Selecting a node opens it in Viewer A and marks
it observed, so a param drag reruns only the affected suffix and the viewer
updates — Flow 1 of docs/05 §3, end to end.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

from PySide6 import QtCore, QtGui, QtWidgets

from cvflow.app.graphview import GraphScene, GraphView, NodePalette
from cvflow.app.inspector import InspectorPanel
from cvflow.app.panels import ConsolePanel, ErrorsPanel, ProfilerPanel, QtLogHandler
from cvflow.app.session import WorkflowSession
from cvflow.app.viewer import ImageView
from cvflow.core.graph import Graph
from cvflow.core.types.image import ImageBuffer
from cvflow.engine.profiling import NodeMetrics, RunReport
from cvflow.io.workflow_json import load_workflow
from cvflow.plugins import builtin_registry

log = logging.getLogger("cvflow.app")

_WF_FILTER = "CVFlow workflow (*.cvflow.json *.json);;All files (*)"


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("CVFlow")
        self.resize(1500, 950)

        self.registry, failures = builtin_registry()
        self.session: Optional[WorkflowSession] = None
        self.scene: Optional[GraphScene] = None
        self.view: Optional[GraphView] = None

        self._build_panels()
        self._build_central()
        self._build_actions()
        self._install_logging()

        for f in failures:
            log.warning("plugin failed to load: %s: %s", f.source, f.error)

        self.new_workflow()

    # ---- construction -----------------------------------------------------
    def _build_central(self) -> None:
        self._view_host = QtWidgets.QWidget()
        self._view_layout = QtWidgets.QVBoxLayout(self._view_host)
        self._view_layout.setContentsMargins(0, 0, 0, 0)
        self.setCentralWidget(self._view_host)

    def _build_panels(self) -> None:
        self.setDockOptions(QtWidgets.QMainWindow.DockOption.AllowNestedDocks
                            | QtWidgets.QMainWindow.DockOption.AllowTabbedDocks
                            | QtWidgets.QMainWindow.DockOption.AnimatedDocks)

        self.palette = NodePalette(self.registry)
        self.palette.addRequested.connect(self._insert_from_palette)
        self._add_dock("Nodes", self.palette, QtCore.Qt.DockWidgetArea.LeftDockWidgetArea)

        self.inspector = InspectorPanel()
        self.inspector.paramEdited.connect(self._on_param_edited)
        self.inspector.paramCommitted.connect(self._on_param_committed)
        self.inspector.labelEdited.connect(self._on_label_edited)
        self._add_dock("Inspector", self.inspector, QtCore.Qt.DockWidgetArea.RightDockWidgetArea)

        self.viewer_a = ImageView("Viewer A")
        self.viewer_b = ImageView("Viewer B")
        viewers = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        viewers.addWidget(self.viewer_a)
        viewers.addWidget(self.viewer_b)
        viewers.setSizes([1, 1])
        self._viewers_dock = self._add_dock(
            "Viewers", viewers, QtCore.Qt.DockWidgetArea.BottomDockWidgetArea)

        self.console = ConsolePanel()
        self.errors = ErrorsPanel()
        self.errors.nodeActivated.connect(self._focus_node)
        self.profiler = ProfilerPanel()
        self.profiler.nodeActivated.connect(self._focus_node)
        tabs = QtWidgets.QTabWidget()
        tabs.addTab(self.console, "Console")
        tabs.addTab(self.errors, "Errors")
        tabs.addTab(self.profiler, "Profiler")
        self._bottom_dock = self._add_dock(
            "Log", tabs, QtCore.Qt.DockWidgetArea.BottomDockWidgetArea)
        self.splitDockWidget(self._viewers_dock, self._bottom_dock,
                             QtCore.Qt.Orientation.Vertical)

        self._status = self.statusBar()
        self._status_totals = QtWidgets.QLabel("ready")
        self._status.addPermanentWidget(self._status_totals)

    def _add_dock(self, title: str, widget: QtWidgets.QWidget,
                  area: QtCore.Qt.DockWidgetArea) -> QtWidgets.QDockWidget:
        dock = QtWidgets.QDockWidget(title, self)
        dock.setWidget(widget)
        dock.setObjectName(f"dock_{title}")
        self.addDockWidget(area, dock)
        return dock

    def _build_actions(self) -> None:
        bar = self.menuBar()
        style = self.style()

        def act(text: str, slot, shortcut: str | None = None,
                icon: QtWidgets.QStyle.StandardPixmap | None = None) -> QtGui.QAction:
            a = QtGui.QAction(text, self)
            if shortcut:
                a.setShortcut(shortcut)
            if icon is not None:
                a.setIcon(style.standardIcon(icon))
            a.triggered.connect(slot)
            return a

        file_menu = bar.addMenu("&File")
        self._act_new = act("&New", self.new_workflow, "Ctrl+N")
        self._act_open = act("&Open…", self._open_dialog, "Ctrl+O",
                             QtWidgets.QStyle.StandardPixmap.SP_DialogOpenButton)
        self._act_save = act("&Save", self._save, "Ctrl+S",
                             QtWidgets.QStyle.StandardPixmap.SP_DialogSaveButton)
        self._act_save_as = act("Save &As…", self._save_as, "Ctrl+Shift+S")
        file_menu.addActions([self._act_new, self._act_open, self._act_save, self._act_save_as])
        file_menu.addSeparator()
        file_menu.addAction(act("&Quit", self.close, "Ctrl+Q"))

        edit_menu = bar.addMenu("&Edit")
        self._act_undo = act("&Undo", self._undo, "Ctrl+Z")
        self._act_redo = act("&Redo", self._redo, "Ctrl+Y")
        self._act_delete = act("&Delete", self._delete_selected, "Del")
        edit_menu.addActions([self._act_undo, self._act_redo, self._act_delete])

        graph_menu = bar.addMenu("&Graph")
        graph_menu.addAction(act("Add node…  (Tab)", self._quick_add))
        graph_menu.addAction(act("Fit view", self._fit_view, "Home"))

        run_menu = bar.addMenu("&Run")
        self._act_run = act("&Run sinks", self._run_sinks, "Ctrl+Return",
                            QtWidgets.QStyle.StandardPixmap.SP_MediaPlay)
        run_menu.addAction(self._act_run)

        help_menu = bar.addMenu("&Help")
        help_menu.addAction(act("About CVFlow", self._about))

        toolbar = self.addToolBar("Main")
        toolbar.setObjectName("main_toolbar")
        toolbar.setMovable(False)
        toolbar.addAction(self._act_open)
        toolbar.addAction(self._act_save)
        toolbar.addSeparator()
        toolbar.addAction(self._act_run)
        toolbar.addAction(act("Fit", self._fit_view))

    def _install_logging(self) -> None:
        handler = QtLogHandler()
        handler.setFormatter(logging.Formatter("%(name)s: %(message)s"))
        handler.setLevel(logging.INFO)
        handler.emitted.connect(self.console.append_line)
        root = logging.getLogger("cvflow")
        root.setLevel(logging.INFO)
        root.addHandler(handler)

    # ---- session lifecycle ------------------------------------------------
    def new_workflow(self) -> None:
        self._set_session(WorkflowSession(Graph(), self.registry))
        self.console.append_line("INFO", "cvflow.app: new workflow")

    def open_workflow(self, path: str) -> None:
        try:
            result = load_workflow(path, self.registry)
        except Exception as exc:  # WorkflowFormatError, UnknownNodeType, …
            QtWidgets.QMessageBox.critical(self, "Open failed", str(exc))
            log.error("open failed: %s", exc)
            return
        for issue in result.issues:
            self.console.append_line("WARNING", f"cvflow.io: {issue}")
        session = WorkflowSession(
            result.graph, self.registry, path=path, base_dir=result.base_dir,
            metadata=result.metadata, ui=result.ui)
        self._set_session(session)
        self.console.append_line(
            "INFO", f"cvflow.app: opened {Path(path).name} "
                    f"({len(result.graph.nodes)} nodes)")
        self._auto_view_primary()

    def _set_session(self, session: WorkflowSession) -> None:
        old = self.session
        if old is not None:
            old.shutdown()
            old.deleteLater()

        self.session = session
        self.scene = GraphScene(session.graph, session.controller.mutate)
        self.view = GraphView(self.scene, self.registry)

        # Replace the central graph view.
        while self._view_layout.count():
            w = self._view_layout.takeAt(0).widget()
            if w:
                w.deleteLater()
        self._view_layout.addWidget(self.view)

        # scene / view signals
        self.scene.nodeSelected.connect(self._on_node_selected)
        self.scene.connectionRejected.connect(self._on_connection_rejected)
        self.view.viewRequested.connect(self._observe_in)
        self.view.statusMessage.connect(lambda m: self._status.showMessage(m, 4000))

        # engine signals (queued from the worker thread)
        c = session.controller
        c.runStarted.connect(lambda: self._status.showMessage("running…", 800))
        c.nodeStatus.connect(self._on_node_status)
        c.outputsReady.connect(self._on_outputs)
        c.reportReady.connect(self._on_report)

        # session signals
        session.dirtyChanged.connect(lambda _d: self._update_title())
        session.paramReverted.connect(self._on_param_reverted)
        session.labelReverted.connect(self._on_label_reverted)
        session.undo.canUndoChanged.connect(self._act_undo.setEnabled)
        session.undo.canRedoChanged.connect(self._act_redo.setEnabled)
        self._act_undo.setEnabled(False)
        self._act_redo.setEnabled(False)

        self.inspector.set_node(None)
        self.viewer_a.clear()
        self.viewer_b.clear()
        self._update_title()
        self.view.setFocus()

    # ---- observation & viewers -------------------------------------------
    def _observe_in(self, slot: str, node_id: str) -> None:
        inst = self.session.graph.nodes.get(node_id)
        if inst is None:
            return
        viewer = self.viewer_a if slot == "A" else self.viewer_b
        viewer.observe(node_id, inst.label)
        self._refresh_observed()
        # Show an already-cached output immediately if we have one.
        outputs = self.session.controller.get_output(node_id)
        if outputs:
            self._show_primary(viewer, node_id, outputs)

    def _refresh_observed(self) -> None:
        observed = {v.node_id for v in (self.viewer_a, self.viewer_b) if v.node_id}
        self.session.controller.set_observed(observed)

    def _show_primary(self, viewer: ImageView, node_id: str, outputs: dict[str, Any]) -> None:
        inst = self.session.graph.nodes.get(node_id)
        if inst is None or not outputs:
            return
        port = self._primary_port(inst, outputs)
        if port is None:
            return
        label = f"{inst.label}·{port}"
        viewer.show_output(node_id, label, outputs[port])

    @staticmethod
    def _primary_port(inst, outputs: dict[str, Any]) -> Optional[str]:
        # Prefer an image output, in declared order; else the first output.
        for decl in inst.spec.outputs:
            if decl.name in outputs and isinstance(outputs[decl.name], ImageBuffer):
                return decl.name
        for decl in inst.spec.outputs:
            if decl.name in outputs:
                return decl.name
        return next(iter(outputs), None)

    def _auto_view_primary(self) -> None:
        """After opening, show the terminal image-producing node in Viewer A."""
        graph = self.session.graph
        try:
            order = graph.topo_order()
        except Exception:
            return
        chosen = None
        for nid in order:
            inst = graph.nodes[nid]
            if any(d.dtype.kind == "image" for d in inst.spec.outputs):
                chosen = nid
        if chosen:
            self.scene.select_node(chosen)
            self.view.fit_all()

    # ---- engine callbacks -------------------------------------------------
    def _on_node_status(self, node_id: str, metrics: NodeMetrics) -> None:
        if self.scene:
            self.scene.apply_status(node_id, metrics)
        self.inspector.update_status(node_id, metrics)

    def _on_outputs(self, node_id: str, outputs: dict[str, Any]) -> None:
        for viewer in (self.viewer_a, self.viewer_b):
            if viewer.node_id == node_id:
                self._show_primary(viewer, node_id, outputs)

    def _on_report(self, report: RunReport) -> None:
        hits = report.cache.hits
        total = hits + report.cache.misses
        state = "ok" if report.ok else "FAILED"
        self._status_totals.setText(
            f"pipeline {report.wall_ms:.1f} ms · cache {hits}/{total} · {state}")
        self.profiler.update_report(report)
        self.errors.set_errors(report.errors)
        if report.errors:
            for err in report.errors:
                self.console.append_line("ERROR", f"{err.node_id}: {err.message}")

    # ---- inspector callbacks ----------------------------------------------
    def _on_param_edited(self, node_id: str, name: str, value: Any) -> None:
        self.session.set_param_live(node_id, name, value)

    def _on_param_committed(self, node_id: str, name: str, old: Any, new: Any) -> None:
        self.session.commit_param(node_id, name, old, new)
        # Reflect any spec snapping (e.g. even kernel → odd) back into widgets.
        if self.inspector.current_node_id() == node_id:
            self.inspector.refresh_values()

    def _on_label_edited(self, node_id: str, new_label: str) -> None:
        self.session.commit_label(node_id, new_label)

    def _on_param_reverted(self, node_id: str) -> None:
        if self.inspector.current_node_id() == node_id:
            self.inspector.refresh_values()

    def _on_label_reverted(self, node_id: str) -> None:
        item = self.scene.node_item(node_id) if self.scene else None
        if item:
            item.update()
        if self.inspector.current_node_id() == node_id:
            self.inspector.refresh_values()

    # ---- scene callbacks --------------------------------------------------
    def _on_node_selected(self, node_id: Optional[str]) -> None:
        inst = self.session.graph.nodes.get(node_id) if node_id else None
        self.inspector.set_node(inst)
        if node_id:
            self._observe_in("A", node_id)

    def _on_connection_rejected(self, reason: str) -> None:
        self._status.showMessage(reason, 5000)
        self.console.append_line("WARNING", f"connection rejected: {reason}")

    # ---- menu actions -----------------------------------------------------
    def _insert_from_palette(self, spec) -> None:
        if self.scene and self.view:
            center = self.view.mapToScene(self.view.viewport().rect().center())
            self.scene.add_node_type(spec, center)

    def _quick_add(self) -> None:
        if self.view:
            self.view.open_quick_add()

    def _fit_view(self) -> None:
        if self.view:
            self.view.fit_all()

    def _delete_selected(self) -> None:
        if self.scene:
            self.scene.delete_selected()

    def _undo(self) -> None:
        if self.session:
            self.session.undo.undo()

    def _redo(self) -> None:
        if self.session:
            self.session.undo.redo()

    def _run_sinks(self) -> None:
        if not self.session:
            return
        sinks = self.session.graph.side_effect_nodes()
        if not sinks:
            self._status.showMessage("no sink (side-effect) nodes to run", 4000)
            return
        self.session.controller.arm_and_run(sinks)
        self.console.append_line("INFO", f"cvflow.app: armed sinks {sinks}")

    def _open_dialog(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Open workflow", "", _WF_FILTER)
        if path:
            if not self._confirm_discard():
                return
            self.open_workflow(path)

    def _save(self) -> None:
        if not self.session:
            return
        if not self.session.path:
            self._save_as()
            return
        self._do_save(self.session.path)

    def _save_as(self) -> None:
        if not self.session:
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save workflow", self.session.path or "untitled.cvflow.json", _WF_FILTER)
        if path:
            self._do_save(path)

    def _do_save(self, path: str) -> None:
        try:
            self.session.save(path, ui=self._collect_ui())
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, "Save failed", str(exc))
            return
        self._update_title()
        self._status.showMessage(f"saved {Path(path).name}", 3000)

    def _collect_ui(self) -> dict:
        ui = dict(self.session.ui)
        ui["viewers"] = {"A": self.viewer_a.node_id, "B": self.viewer_b.node_id}
        return ui

    def _about(self) -> None:
        QtWidgets.QMessageBox.about(
            self, "CVFlow",
            "<b>CVFlow</b> — visual computer-vision workflow builder.<br>"
            "Phase 1 GUI over the headless core + DAG engine.<br>"
            f"{len(self.registry.all_specs())} node types registered.")

    # ---- helpers ----------------------------------------------------------
    def _focus_node(self, node_id: str) -> None:
        if not self.scene or not self.view:
            return
        self.scene.select_node(node_id)
        item = self.scene.node_item(node_id)
        if item:
            self.view.centerOn(item)

    def _update_title(self) -> None:
        title = self.session.title if self.session else "untitled"
        self.setWindowTitle(f"CVFlow — {title}")

    def _confirm_discard(self) -> bool:
        if not self.session or not self.session.dirty:
            return True
        reply = QtWidgets.QMessageBox.question(
            self, "Discard changes?",
            "The current workflow has unsaved changes. Discard them?",
            QtWidgets.QMessageBox.StandardButton.Discard
            | QtWidgets.QMessageBox.StandardButton.Cancel)
        return reply == QtWidgets.QMessageBox.StandardButton.Discard

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        if not self._confirm_discard():
            event.ignore()
            return
        if self.session:
            self.session.shutdown()
        super().closeEvent(event)
