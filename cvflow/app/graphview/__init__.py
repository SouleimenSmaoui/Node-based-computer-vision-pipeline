"""Bespoke QGraphicsView node editor behind the GraphViewPort seam (docs/01 §7.3).

Design note / deliberate deviation (STATUS.md): docs/08 named NodeGraphQt as the
Phase-1 editor with a bespoke QGraphicsView as the Phase-3 fallback. NodeGraphQt
(+ Qt.py, superqt, qtawesome) has no verified Python-3.14 support, so we pulled
the documented fallback forward. The public seam is the same, and this keeps the
GUI dependency set to PySide6 alone.
"""

from cvflow.app.graphview.scene import GraphScene
from cvflow.app.graphview.view import GraphView
from cvflow.app.graphview.palette import NodePalette

__all__ = ["GraphScene", "GraphView", "NodePalette"]
