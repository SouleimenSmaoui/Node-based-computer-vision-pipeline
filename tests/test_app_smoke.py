"""Headless (offscreen) smoke tests for the PySide6 GUI (docs/05).

These exercise the real widgets and the full interactive loop — open a workflow,
let the background ExecutionController run it, and confirm the viewer received an
image and a param change reruns incrementally. Skipped entirely when PySide6 is
not installed, so the core suite stays runnable without the ``app`` extra.
"""

from __future__ import annotations

import os
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
