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

from PySide6 import QtCore, QtWidgets

from cvflow.core.params import (
    BoolParam,
    EnumParam,
    FloatParam,
    IntParam,
    ParamSpec,
    PathParam,
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


def build_param_widget(spec: ParamSpec) -> ParamWidget:
    """Instantiate the right editor for a parameter spec.

    Dispatch is by spec *type*, never by ``widget_hint``. A hint-keyed table
    used to back this up, mapping "slider" to the int editor — so a third-party
    ParamSpec subclass declaring ``widget_hint="slider"`` without being an
    ``IntParam`` crashed on ``spec.min``/``spec.step``. An unknown spec now
    always gets the string editor: degraded, but it renders and edits
    (CODE_REVIEW §2.7).
    """
    if isinstance(spec, PathParam):
        return _PathWidget(spec)
    if isinstance(spec, IntParam):
        return _IntWidget(spec)
    if isinstance(spec, FloatParam):
        return _FloatWidget(spec)
    if isinstance(spec, BoolParam):
        return _BoolWidget(spec)
    if isinstance(spec, EnumParam):
        return _EnumWidget(spec)
    return _StringWidget(spec)
