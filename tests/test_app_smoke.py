"""Headless (offscreen) smoke tests for the PySide6 GUI (docs/05).

These exercise the real widgets and the full interactive loop — open a workflow,
let the background ExecutionController run it, and confirm the viewer received an
image and a param change reruns incrementally. Skipped entirely when PySide6 is
not installed, so the core suite stays runnable without the ``app`` extra.
"""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6 import QtCore, QtWidgets  # noqa: E402

from cvflow.core.types.image import ColorSpace, ImageBuffer  # noqa: E402

DEMO = Path(__file__).resolve().parents[1] / "examples" / "workflows" / "edges_demo.cvflow.json"


@pytest.fixture(scope="module")
def qapp():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    yield app


def _spin(app, ms: int) -> None:
    end = time.time() + ms / 1000
    while time.time() < end:
        app.processEvents(QtCore.QEventLoop.ProcessEventsFlag.AllEvents, 10)


def _wait_for(app, predicate, timeout_ms: int = 4000) -> bool:
    end = time.time() + timeout_ms / 1000
    while time.time() < end:
        if predicate():
            return True
        _spin(app, 25)
    return predicate()


@pytest.fixture
def window(qapp):
    from cvflow.app.main_window import MainWindow

    win = MainWindow()
    yield win
    # mark_clean() avoids the modal "discard changes?" dialog, which would block
    # forever under the offscreen platform.
    if win.session is not None:
        win.session.mark_clean()
        win.session.shutdown()
    win.close()


# ---- unit-level widget tests ----------------------------------------------


def test_imaging_bgr_roundtrip(qapp):
    from cvflow.app import imaging

    arr = np.zeros((4, 6, 3), np.uint8)
    arr[:] = (10, 20, 30)  # BGR
    img = imaging.to_qimage(ImageBuffer(arr, ColorSpace.BGR))
    assert (img.width(), img.height()) == (6, 4)
    r, g, b, _ = img.pixelColor(0, 0).getRgb()
    assert (r, g, b) == (30, 20, 10)  # displayed as RGB


def test_imaging_normalizes_gradient(qapp):
    from cvflow.app import imaging
    from cvflow.core.types.image import ValueRange

    grad = np.tile(np.linspace(10, 40, 8, dtype=np.uint8), (8, 1))
    img = imaging.to_qimage(ImageBuffer(grad, ColorSpace.GRAY, range=ValueRange.ARBITRARY),
                            normalize="minmax")
    # min-max stretch pushes the darkest pixel to 0 and brightest to 255.
    assert img.pixelColor(0, 0).red() == 0
    assert img.pixelColor(7, 0).red() == 255


def test_inspector_builds_widgets_from_specs(qapp):
    from cvflow.app.inspector import InspectorPanel
    from cvflow.core.graph import Graph
    from cvflow.plugins import builtin_registry

    reg, _ = builtin_registry()
    graph = Graph()
    inst = graph.add_node(reg.get("cvflow.edges.canny"))
    panel = InspectorPanel()
    panel.set_node(inst)
    assert set(panel._widgets) == {p.name for p in inst.spec.params}


def test_unknown_param_spec_falls_back_to_string_editor(qapp):
    """CODE_REVIEW §2.7 — a hint-keyed fallback table routed
    ``widget_hint="slider"`` to the int editor, so any third-party ParamSpec
    declaring that hint without being an IntParam crashed on ``spec.min``."""
    from cvflow.app.inspector.widgets import _StringWidget, build_param_widget
    from cvflow.core.params import ParamSpec

    class ExoticParam(ParamSpec):
        widget_hint = "slider"  # the trap: hint of an int, type of neither

    widget = build_param_widget(ExoticParam("Exotic", default="x"))
    assert isinstance(widget, _StringWidget)


def test_log_handler_does_not_accumulate_across_windows(qapp):
    """CODE_REVIEW §2.6 — one QtLogHandler was added to the process-wide
    "cvflow" logger per MainWindow and never removed, so handlers stacked up
    pointing at consoles that no longer exist."""
    import logging

    from cvflow.app.main_window import MainWindow

    root = logging.getLogger("cvflow")
    before = len(root.handlers)
    for _ in range(3):
        win = MainWindow()
        win.session.mark_clean()  # avoid the modal discard dialog
        win.session.shutdown()
        win.close()
    assert len(root.handlers) == before


def test_category_colour_is_stable_across_processes():
    """CODE_REVIEW §2.4 — the fallback used built-in hash(), which is salted per
    process, so a plugin's category changed colour on every launch."""
    import subprocess
    import sys

    code = ("from cvflow.app.theme import category_color;"
            "print(category_color('Third Party Pack').name())")
    seen = set()
    for seed in ("0", "12345"):
        env = dict(os.environ, PYTHONHASHSEED=seed, QT_QPA_PLATFORM="offscreen")
        proc = subprocess.run([sys.executable, "-c", code], env=env,
                              capture_output=True, text=True, timeout=120)
        assert proc.returncode == 0, proc.stderr
        seen.add(proc.stdout.strip())
    assert len(seen) == 1, f"category colour varied across hash seeds: {seen}"


def test_profiler_sorts_slowest_node_first(qapp):
    """CODE_REVIEW §1.3 — the table stored formatted strings, so Qt sorted them
    lexicographically ("102.35" < "9.50") and the slowest node landed last."""
    from cvflow.app.panels.profiler import ProfilerPanel
    from cvflow.engine.profiling import NodeMetrics, NodeStatus, RunReport

    report = RunReport(generation=1)
    for nid, ms in (("fast", 9.5), ("slowest", 102.35), ("middle", 23.1)):
        report.nodes[nid] = NodeMetrics(NodeStatus.OK, ms=ms)

    panel = ProfilerPanel()
    panel.update_report(report)

    ordered = [panel.item(r, 0).text() for r in range(panel.rowCount())]
    assert ordered == ["slowest", "middle", "fast"]


# ---- armed ("Run") request handling — CODE_REVIEW §1.2 ---------------------


@pytest.fixture
def sink_controller(qapp, tmp_path):
    """A controller over ``load -> save``, with the save sink left unarmed."""
    from cvflow.app.controllers.execution_controller import ExecutionController
    from cvflow.core.graph import Graph
    from cvflow.engine import EngineSettings
    from cvflow.plugins import builtin_registry

    reg, _ = builtin_registry()
    asset = Path(__file__).resolve().parents[1] / "examples" / "assets" / "sample.png"
    out = tmp_path / "saved.png"

    graph = Graph()
    graph.add_node(reg.get("cvflow.io.load_image"), node_id="load",
                   params={"path": str(asset)})
    graph.add_node(reg.get("cvflow.io.save_image"), node_id="save",
                   params={"path": str(out)})
    graph.connect("load", "image", "save", "image")

    ctl = ExecutionController(graph, settings=EngineSettings(workers=0))
    yield ctl, out
    ctl.shutdown()


def test_arm_and_run_publishes_armed_under_the_condition(sink_controller):
    """Defect A: ``_armed`` written outside ``_cond`` can be wiped by the
    worker's read-and-clear — the user clicks Run and no sink ever executes."""
    ctl, out = sink_controller
    published = threading.Event()

    with ctl._cond:
        t = threading.Thread(
            target=lambda: (ctl.arm_and_run(["save"]), published.set()))
        t.start()
        # We hold _cond. A correct arm_and_run is blocked on it and cannot have
        # published anything yet; the buggy version assigned before locking.
        assert not published.wait(0.25)
        assert ctl._armed == set()

    assert published.wait(2.0)
    t.join(timeout=2.0)

    end = time.time() + 4.0
    while not out.exists() and time.time() < end:
        time.sleep(0.02)
    assert out.exists(), "armed Run never executed the sink"


def test_incomplete_sinks_keeps_only_unfinished_sinks_armed(qapp):
    """Defect B: the re-arm set after a superseded run."""
    from cvflow.app.controllers.execution_controller import ExecutionController
    from cvflow.engine.profiling import NodeMetrics, NodeStatus, RunReport

    report = RunReport(generation=1)
    report.nodes["done"] = NodeMetrics(NodeStatus.OK)
    report.nodes["skipped"] = NodeMetrics(NodeStatus.SKIPPED)
    report.nodes["cancelled"] = NodeMetrics(NodeStatus.CANCELLED)

    stay_armed = ExecutionController._incomplete_sinks(
        {"done", "skipped", "cancelled", "never_dispatched"}, report)
    assert stay_armed == {"skipped", "cancelled", "never_dispatched"}


def test_arm_and_run_does_not_drop_a_carried_forward_arm(sink_controller):
    """Defect B follow-on: a Run click must not clobber the arm a superseded
    run carried forward, or that export is lost after all."""
    ctl, _ = sink_controller
    ctl.shutdown()  # stop the worker so nothing consumes _armed underneath us

    with ctl._cond:
        ctl._armed = {"save"}  # as _incomplete_sinks would have carried it
    ctl.arm_and_run([])        # Run clicked; arms nothing new
    assert ctl._armed == {"save"}


# ---- full interactive loop -------------------------------------------------


def test_open_demo_runs_and_displays(window, qapp):
    reports = []
    window.open_workflow(str(DEMO))
    window.session.controller.reportReady.connect(reports.append)
    assert _wait_for(qapp, lambda: bool(reports)), "no run report arrived"
    assert reports[-1].ok
    assert not window.viewer_a.canvas._pixmap.pixmap().isNull()
    assert window.viewer_a.node_id == "canny"


def test_param_change_reruns_incrementally(window, qapp):
    reports = []
    window.open_workflow(str(DEMO))
    window.session.controller.reportReady.connect(reports.append)
    assert _wait_for(qapp, lambda: bool(reports))

    n_before = len(reports)
    window.session.set_param_live("canny", "low", 25)
    assert _wait_for(qapp, lambda: len(reports) > n_before), "param change did not rerun"
    latest = reports[-1]
    # Only the affected suffix re-executes; upstream is served from cache.
    assert "canny" in latest.executed()
    assert "blur" in latest.cached()


def test_add_and_connect_via_scene(window, qapp):
    graph = window.session.graph
    reg = window.registry
    load_id = window.scene.add_node_type(reg.get("cvflow.io.load_image"), QtCore.QPointF(0, 0))
    gray_id = window.scene.add_node_type(reg.get("cvflow.color.to_gray"), QtCore.QPointF(240, 0))
    assert load_id and gray_id
    window.session.controller.mutate(
        lambda: graph.connect(load_id, "image", gray_id, "image"))
    assert len(graph.edges) == 1
    assert len(window.scene._edges) == 1  # edge item materialized
