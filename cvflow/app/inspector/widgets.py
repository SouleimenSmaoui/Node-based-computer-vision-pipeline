"""Parameter editor widgets, one per ``ParamSpec.widget_hint`` (docs/04 §1.1).

Each widget emits two signals:

* ``edited(value)``  — live, on every tick of a gesture → drives the debounced
  re-run (the interactive loop, docs/05 §2.3).
* ``committed(value)`` — once per *gesture* (slider release, editing finished,
  a discrete toggle) → the granularity of one undo step (docs/05 §5).

``set_value`` reflects an externally-validated value (e.g. after the spec snaps
an even kernel size to odd) without re-emitting.
"""

from __future__ import annotations

import os
from typing import Any

from PySide6 import QtCore, QtGui, QtWidgets

from cvflow.app.theme import TEXT_DIM
from cvflow.core.params import (
    BoolParam,
    CodeParam,
    ColorParam,
    EnumParam,
    FloatParam,
    IntParam,
    ParamSpec,
    PathParam,
    PointParam,
    RangeParam,
    RectParam,
    StringParam,
)

_FLOAT_STEPS = 1000  # slider resolution for bounded float params


class ParamWidget(QtWidgets.QWidget):
    edited = QtCore.Signal(object)
    committed = QtCore.Signal(object)

    def __init__(self, spec: ParamSpec) -> None:
        super().__init__()
        self.spec = spec
        self._muted = False
        if spec.tooltip:
            self.setToolTip(spec.tooltip)

    def set_value(self, value: Any) -> None:  # pragma: no cover - overridden
        raise NotImplementedError

    def _emit_edited(self, value: Any) -> None:
        if not self._muted:
            self.edited.emit(value)

    def _emit_committed(self, value: Any) -> None:
        if not self._muted:
            self.committed.emit(value)


class _IntWidget(ParamWidget):
    def __init__(self, spec: IntParam) -> None:
        super().__init__(spec)
        self.spin = QtWidgets.QSpinBox()
        lo = spec.min if spec.min is not None else -1_000_000
        hi = spec.max if spec.max is not None else 1_000_000
        self.spin.setRange(lo, hi)
        self.spin.setSingleStep(max(1, spec.step))
        self.slider = None
        row = QtWidgets.QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        if spec.min is not None and spec.max is not None:
            self.slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
            self.slider.setRange(lo, hi)
            self.slider.setSingleStep(max(1, spec.step))
            self.slider.valueChanged.connect(self._on_slider)
            self.slider.sliderReleased.connect(lambda: self._emit_committed(self.spin.value()))
            row.addWidget(self.slider, 1)
        row.addWidget(self.spin)
        self.spin.valueChanged.connect(self._on_spin)
        self.spin.editingFinished.connect(lambda: self._emit_committed(self.spin.value()))

    def _on_slider(self, v: int) -> None:
        if self._muted:
            return
        self._muted = True
        self.spin.setValue(v)
        self._muted = False
        self._emit_edited(v)

    def _on_spin(self, v: int) -> None:
        if self._muted:
            return
        if self.slider is not None:
            self._muted = True
            self.slider.setValue(v)
            self._muted = False
        self._emit_edited(v)

    def set_value(self, value: Any) -> None:
        self._muted = True
        self.spin.setValue(int(value))
        if self.slider is not None:
            self.slider.setValue(int(value))
        self._muted = False


class _FloatWidget(ParamWidget):
    def __init__(self, spec: FloatParam) -> None:
        super().__init__(spec)
        self.spin = QtWidgets.QDoubleSpinBox()
        self.spin.setDecimals(spec.decimals)
        lo = spec.min if spec.min is not None else -1e9
        hi = spec.max if spec.max is not None else 1e9
        self.spin.setRange(lo, hi)
        self.spin.setSingleStep(10 ** -spec.decimals * 10)
        self._lo, self._hi = lo, hi
        self.slider = None
        row = QtWidgets.QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        if spec.min is not None and spec.max is not None and hi > lo:
            self.slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
            self.slider.setRange(0, _FLOAT_STEPS)
            self.slider.valueChanged.connect(self._on_slider)
            self.slider.sliderReleased.connect(lambda: self._emit_committed(self.spin.value()))
            row.addWidget(self.slider, 1)
        row.addWidget(self.spin)
        self.spin.valueChanged.connect(self._on_spin)
        self.spin.editingFinished.connect(lambda: self._emit_committed(self.spin.value()))

    def _to_slider(self, v: float) -> int:
        return int(round((v - self._lo) / (self._hi - self._lo) * _FLOAT_STEPS))

    def _from_slider(self, s: int) -> float:
        return self._lo + (s / _FLOAT_STEPS) * (self._hi - self._lo)

    def _on_slider(self, s: int) -> None:
        if self._muted:
            return
        v = self._from_slider(s)
        self._muted = True
        self.spin.setValue(v)
        self._muted = False
        self._emit_edited(v)

    def _on_spin(self, v: float) -> None:
        if self._muted:
            return
        if self.slider is not None:
            self._muted = True
            self.slider.setValue(self._to_slider(v))
            self._muted = False
        self._emit_edited(v)

    def set_value(self, value: Any) -> None:
        self._muted = True
        self.spin.setValue(float(value))
        if self.slider is not None:
            self.slider.setValue(self._to_slider(float(value)))
        self._muted = False


class _BoolWidget(ParamWidget):
    def __init__(self, spec: BoolParam) -> None:
        super().__init__(spec)
        self.check = QtWidgets.QCheckBox()
        row = QtWidgets.QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.check)
        row.addStretch(1)
        self.check.toggled.connect(self._on_toggle)

    def _on_toggle(self, v: bool) -> None:
        self._emit_edited(v)
        self._emit_committed(v)

    def set_value(self, value: Any) -> None:
        self._muted = True
        self.check.setChecked(bool(value))
        self._muted = False


class _EnumWidget(ParamWidget):
    def __init__(self, spec: EnumParam) -> None:
        super().__init__(spec)
        self.combo = QtWidgets.QComboBox()
        self.combo.addItems([str(c) for c in spec.choices])
        row = QtWidgets.QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.combo, 1)
        self.combo.currentTextChanged.connect(self._on_change)

    def _on_change(self, text: str) -> None:
        self._emit_edited(text)
        self._emit_committed(text)

    def set_value(self, value: Any) -> None:
        self._muted = True
        self.combo.setCurrentText(str(value))
        self._muted = False


class _StringWidget(ParamWidget):
    def __init__(self, spec: StringParam) -> None:
        super().__init__(spec)
        self.edit = QtWidgets.QLineEdit()
        row = QtWidgets.QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.edit, 1)
        self.edit.textEdited.connect(self._emit_edited)
        self.edit.editingFinished.connect(lambda: self._emit_committed(self.edit.text()))

    def set_value(self, value: Any) -> None:
        self._muted = True
        self.edit.setText(str(value))
        self._muted = False


class _PathWidget(ParamWidget):
    def __init__(self, spec: PathParam) -> None:
        super().__init__(spec)
        self.edit = QtWidgets.QLineEdit()
        browse = QtWidgets.QToolButton()
        browse.setText("…")
        browse.clicked.connect(self._browse)
        row = QtWidgets.QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.edit, 1)
        row.addWidget(browse)
        self.edit.textEdited.connect(self._emit_edited)
        self.edit.editingFinished.connect(lambda: self._emit_committed(self.edit.text()))

    def _browse(self) -> None:
        spec: PathParam = self.spec  # type: ignore[assignment]
        start = self.edit.text() or os.getcwd()
        flt = spec.filter or "All files (*)"
        if spec.mode == "dir":
            path = QtWidgets.QFileDialog.getExistingDirectory(self, spec.label, start)
        elif spec.mode == "save":
            path, _ = QtWidgets.QFileDialog.getSaveFileName(self, spec.label, start, flt)
        else:
            path, _ = QtWidgets.QFileDialog.getOpenFileName(self, spec.label, start, flt)
        if path:
            self.edit.setText(path)
            self._emit_edited(path)
            self._emit_committed(path)

    def set_value(self, value: Any) -> None:
        self._muted = True
        self.edit.setText(str(value))
        self._muted = False


class _TupleWidget(ParamWidget):
    """Shared base for the fixed-length numeric specs (range/point/rect).

    One spin box per component, each labelled. A two-handle slider would suit
    RangeParam better, but Qt has no native one and the GUI is PySide6-only by
    decision (STATUS.md deviation #7) — so: honest spin boxes.
    """

    captions: tuple[str, ...] = ()

    def __init__(self, spec: ParamSpec, integer: bool, decimals: int,
                 lo: float | None, hi: float | None) -> None:
        super().__init__(spec)
        self._integer = integer
        self._boxes: list[QtWidgets.QAbstractSpinBox] = []
        row = QtWidgets.QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)
        for caption in self.captions:
            if caption:
                tag = QtWidgets.QLabel(caption)
                tag.setStyleSheet(f"color:{TEXT_DIM};")
                row.addWidget(tag)
            box: QtWidgets.QAbstractSpinBox
            if integer:
                box = QtWidgets.QSpinBox()
                box.setRange(int(lo) if lo is not None else -1_000_000,
                             int(hi) if hi is not None else 1_000_000)
            else:
                box = QtWidgets.QDoubleSpinBox()
                box.setDecimals(decimals)
                box.setRange(lo if lo is not None else -1e9,
                             hi if hi is not None else 1e9)
            box.valueChanged.connect(self._on_changed)
            box.editingFinished.connect(
                lambda: self._emit_committed(self._value()))
            self._boxes.append(box)
            row.addWidget(box, 1)

    def _value(self) -> tuple:
        return tuple(b.value() for b in self._boxes)

    def _on_changed(self, _v) -> None:
        self._emit_edited(self._value())

    def set_value(self, value: Any) -> None:
        self._muted = True
        for box, component in zip(self._boxes, value):
            box.setValue(int(component) if self._integer else float(component))
        self._muted = False


class _RangeWidget(_TupleWidget):
    captions = ("low", "high")

    def __init__(self, spec: RangeParam) -> None:
        super().__init__(spec, spec.integer, spec.decimals, spec.min, spec.max)


class _PointWidget(_TupleWidget):
    captions = ("x", "y")

    def __init__(self, spec: PointParam) -> None:
        super().__init__(spec, spec.integer, spec.decimals, spec.min, spec.max)


class _RectWidget(_TupleWidget):
    captions = ("x", "y", "w", "h")

    def __init__(self, spec: RectParam) -> None:
        # No bounds: a rect is in image pixels and the image size is not known
        # to the spec. Nodes clip with RectParam.clip_to() at execution time.
        super().__init__(spec, spec.integer, spec.decimals, None, None)


class _ColorWidget(ParamWidget):
    """Swatch button opening a colour dialog. Values are stored **BGR** to
    match OpenCV; Qt speaks RGB, so the two are swapped at this boundary and
    nowhere else."""

    def __init__(self, spec: ColorParam) -> None:
        super().__init__(spec)
        self._spec_color: ColorParam = spec
        self._value: tuple = tuple(spec.default)
        self.button = QtWidgets.QPushButton()
        self.button.setFixedHeight(22)
        self.button.clicked.connect(self._pick)
        row = QtWidgets.QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.button, 1)
        self._paint()

    def _qcolor(self) -> QtGui.QColor:
        b, g, r = self._value[:3]
        alpha = self._value[3] if len(self._value) > 3 else 255
        return QtGui.QColor(int(r), int(g), int(b), int(alpha))

    def _paint(self) -> None:
        c = self._qcolor()
        # Contrasting text so the hex stays readable on any swatch.
        fg = "#000000" if c.lightness() > 127 else "#ffffff"
        self.button.setStyleSheet(
            f"background:{c.name()}; color:{fg}; border:1px solid #555;")
        self.button.setText(c.name().upper())

    def _pick(self) -> None:
        options = QtWidgets.QColorDialog.ColorDialogOption.ShowAlphaChannel \
            if self._spec_color.with_alpha \
            else QtWidgets.QColorDialog.ColorDialogOption(0)
        chosen = QtWidgets.QColorDialog.getColor(
            self._qcolor(), self, self.spec.label, options)
        if not chosen.isValid():
            return
        value = (chosen.blue(), chosen.green(), chosen.red())
        if self._spec_color.with_alpha:
            value = value + (chosen.alpha(),)
        self._value = value
        self._paint()
        self._emit_edited(value)
        self._emit_committed(value)

    def set_value(self, value: Any) -> None:
        self._muted = True
        self._value = tuple(value)
        self._paint()
        self._muted = False


class _CodeWidget(ParamWidget):
    """Multi-line source editor. Commits on focus-out rather than per keystroke:
    running half-typed code on every character would be noise at best."""

    def __init__(self, spec: CodeParam) -> None:
        super().__init__(spec)
        self.edit = QtWidgets.QPlainTextEdit()
        self.edit.setTabChangesFocus(False)
        self.edit.setMinimumHeight(120)
        font = QtGui.QFontDatabase.systemFont(
            QtGui.QFontDatabase.SystemFont.FixedFont)
        self.edit.setFont(font)
        row = QtWidgets.QVBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.edit)
        self.edit.textChanged.connect(
            lambda: self._emit_edited(self.edit.toPlainText()))

    def focusOutEvent(self, event: QtGui.QFocusEvent) -> None:
        self._emit_committed(self.edit.toPlainText())
        super().focusOutEvent(event)

    def set_value(self, value: Any) -> None:
        self._muted = True
        if self.edit.toPlainText() != str(value):
            self.edit.setPlainText(str(value))
        self._muted = False


def build_param_widget(spec: ParamSpec) -> ParamWidget:
    """Instantiate the right editor for a parameter spec.

    Dispatch is by spec *type*, never by ``widget_hint``. A hint-keyed table
    used to back this up, mapping "slider" to the int editor — so a third-party
    ParamSpec subclass declaring ``widget_hint="slider"`` without being an
    ``IntParam`` crashed on ``spec.min``/``spec.step``. An unknown spec now
    always gets the string editor: degraded, but it renders and edits
    (CODE_REVIEW §2.7).
    """
    # Subclasses before their bases: PathParam and CodeParam are StringParams.
    if isinstance(spec, PathParam):
        return _PathWidget(spec)
    if isinstance(spec, CodeParam):
        return _CodeWidget(spec)
    if isinstance(spec, RangeParam):
        return _RangeWidget(spec)
    if isinstance(spec, PointParam):
        return _PointWidget(spec)
    if isinstance(spec, RectParam):
        return _RectWidget(spec)
    if isinstance(spec, ColorParam):
        return _ColorWidget(spec)
    if isinstance(spec, IntParam):
        return _IntWidget(spec)
    if isinstance(spec, FloatParam):
        return _FloatWidget(spec)
    if isinstance(spec, BoolParam):
        return _BoolWidget(spec)
    if isinstance(spec, EnumParam):
        return _EnumWidget(spec)
    return _StringWidget(spec)
