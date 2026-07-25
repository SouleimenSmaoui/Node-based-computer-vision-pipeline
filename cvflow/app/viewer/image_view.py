"""ImageView — a QGraphicsView image canvas (docs/05 §2.4).

Zoom-to-cursor, drag-pan, fit / 100 %, live pixel probe, channel isolation and
range-aware normalization, plus crisp vector overlays for geometry outputs
(contours) that never bake into the pixels — so re-zoom costs nothing.

MVP note: pixmaps are CPU QImages, not GL textures. The GL viewport + zero-copy
texture upload is the Phase-2 upgrade (docs/05 §2.4); the interface here is
already the one that path will slot behind.
"""

from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from cvflow.app import imaging
from cvflow.app.theme import VIEWER_BG
from cvflow.core.types.geometry import ContourSet
from cvflow.core.types.image import ImageBuffer

_ZOOM_STEP = 1.25
_MIN_SCALE = 0.02
_MAX_SCALE = 64.0


class _Canvas(QtWidgets.QGraphicsView):
    probed = QtCore.Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._scene = QtWidgets.QGraphicsScene(self)
        self.setScene(self._scene)
        self._pixmap = self._scene.addPixmap(QtGui.QPixmap())
        self._overlay: list[QtWidgets.QGraphicsItem] = []
        self._buf: ImageBuffer | None = None

        self.setBackgroundBrush(QtGui.QColor(VIEWER_BG))
        self.setDragMode(QtWidgets.QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QtWidgets.QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setRenderHints(QtGui.QPainter.RenderHint.SmoothPixmapTransform)
        self.setMouseTracking(True)
        self.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)

    # ---- content ----------------------------------------------------------
    def show_pixmap(self, pixmap: QtGui.QPixmap, buf: ImageBuffer | None,
                    fit_if_first: bool) -> None:
        first = self._pixmap.pixmap().isNull()
        self._pixmap.setPixmap(pixmap)
        self._buf = buf
        if not pixmap.isNull():
            self._scene.setSceneRect(QtCore.QRectF(pixmap.rect()))
            if first and fit_if_first:
                self.fit()

    def set_overlay(self, items: list[QtWidgets.QGraphicsItem]) -> None:
        for it in self._overlay:
            self._scene.removeItem(it)
        self._overlay = items
        for it in items:
            self._scene.addItem(it)

    # ---- navigation -------------------------------------------------------
    def fit(self) -> None:
        if not self._pixmap.pixmap().isNull():
            self.fitInView(self._pixmap, QtCore.Qt.AspectRatioMode.KeepAspectRatio)

    def actual_size(self) -> None:
        self.resetTransform()

    def current_scale(self) -> float:
        return self.transform().m11()

    def wheelEvent(self, event: QtGui.QWheelEvent) -> None:
        factor = _ZOOM_STEP if event.angleDelta().y() > 0 else 1 / _ZOOM_STEP
        scale = self.current_scale() * factor
        if _MIN_SCALE <= scale <= _MAX_SCALE:
            self.scale(factor, factor)

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        super().mouseMoveEvent(event)
        if self._buf is not None:
            sp = self.mapToScene(event.position().toPoint())
            self.probed.emit(imaging.pixel_readout(self._buf, int(sp.x()), int(sp.y())))

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        if event.key() == QtCore.Qt.Key.Key_F:
            self.fit()
        elif event.key() == QtCore.Qt.Key.Key_1:
            self.actual_size()
        else:
            super().keyPressEvent(event)


class ImageView(QtWidgets.QWidget):
    """Viewer widget: display controls on top, canvas below."""

    def __init__(self, title: str = "Viewer") -> None:
        super().__init__()
        self._buf: ImageBuffer | None = None
        self._contours: ContourSet | None = None
        self._title = title
        self._node_id: str | None = None

        self.canvas = _Canvas()
        self.canvas.probed.connect(self._on_probe)

        self._channel = QtWidgets.QComboBox()
        self._channel.addItems(imaging.CHANNELS)
        self._channel.currentTextChanged.connect(lambda _: self._refresh())
        self._normalize = QtWidgets.QComboBox()
        self._normalize.addItems(["auto", "off", "minmax"])
        self._normalize.currentTextChanged.connect(lambda _: self._refresh())

        self._header = QtWidgets.QLabel(f"{title}: —")
        self._header.setStyleSheet("color:#9a9a9a;")
        self._readout = QtWidgets.QLabel("")
        self._readout.setStyleSheet("color:#9a9a9a;")
        fit_btn = QtWidgets.QToolButton(); fit_btn.setText("Fit"); fit_btn.clicked.connect(self.canvas.fit)
        one_btn = QtWidgets.QToolButton(); one_btn.setText("100%"); one_btn.clicked.connect(self.canvas.actual_size)

        top = QtWidgets.QHBoxLayout()
        top.setContentsMargins(4, 2, 4, 2)
        top.addWidget(self._header, 1)
        top.addWidget(QtWidgets.QLabel("ch")); top.addWidget(self._channel)
        top.addWidget(QtWidgets.QLabel("norm")); top.addWidget(self._normalize)
        top.addWidget(fit_btn); top.addWidget(one_btn)

        bottom = QtWidgets.QHBoxLayout()
        bottom.setContentsMargins(4, 1, 4, 2)
        bottom.addWidget(self._readout, 1)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(1)
        layout.addLayout(top)
        layout.addWidget(self.canvas, 1)
        layout.addLayout(bottom)

    @property
    def node_id(self) -> str | None:
        return self._node_id

    def clear(self) -> None:
        self._buf = None
        self._contours = None
        self._node_id = None
        self.canvas.show_pixmap(QtGui.QPixmap(), None, False)
        self.canvas.set_overlay([])
        self._header.setText(f"{self._title}: —")

    def observe(self, node_id: str, label: str) -> None:
        """Start watching a node before its output has arrived."""
        self._node_id = node_id
        self._header.setText(f"{self._title}: {label} (waiting…)")

    def show_output(self, node_id: str, label: str, value) -> None:
        """Display whatever a node produced: image, contours, or scalar."""
        self._node_id = node_id
        self._buf = value if isinstance(value, ImageBuffer) else self._buf
        self._contours = value if isinstance(value, ContourSet) else None
        self._header.setText(f"{self._title}: {label}")
        self._refresh()

    # ---- rendering --------------------------------------------------------
    def _refresh(self) -> None:
        if self._buf is not None:
            qimg = imaging.to_qimage(
                self._buf, normalize=self._normalize.currentText(),
                channel=self._channel.currentText())
            self.canvas.show_pixmap(QtGui.QPixmap.fromImage(qimg), self._buf, fit_if_first=True)
        self.canvas.set_overlay(self._build_overlay())

    def _build_overlay(self) -> list[QtWidgets.QGraphicsItem]:
        if self._contours is None:
            return []
        pen = QtGui.QPen(QtGui.QColor("#ff8c1a"))
        pen.setCosmetic(True)   # stays 1px crisp at every zoom (docs/05 §2.4)
        pen.setWidthF(1.5)
        items: list[QtWidgets.QGraphicsItem] = []
        for contour in self._contours.contours:
            pts = contour.reshape(-1, 2)
            if len(pts) < 2:
                continue
            path = QtGui.QPainterPath()
            path.moveTo(float(pts[0][0]), float(pts[0][1]))
            for x, y in pts[1:]:
                path.lineTo(float(x), float(y))
            path.closeSubpath()
            item = QtWidgets.QGraphicsPathItem(path)
            item.setPen(pen)
            items.append(item)
        return items

    def _on_probe(self, text: str) -> None:
        self._readout.setText(text)
