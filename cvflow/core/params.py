"""Declarative parameter descriptors (docs/04 §1.1).

A node declares parameters as class attributes; the framework derives UI,
validation, serialization, and fingerprinting from these specs. Validation
policy: *snap to valid* (clamp range, snap step/odd) rather than raise — the
friendlier behavior for sliders and programmatic sweeps. Type mismatches and
unknown enum values still raise ``ParamError``.
"""

from __future__ import annotations

import enum
import math
from typing import Any, Callable, Sequence

from cvflow.core.errors import ParamError


class ParamSpec:
    """Base descriptor. Subclasses implement ``validate`` and ``parse``."""

    widget_hint = "input"

    def __init__(
        self,
        label: str,
        *,
        default: Any = None,
        tooltip: str = "",
        promotable: bool = False,
        live: bool = True,
    ):
        self.label = label
        self.default = default
        self.tooltip = tooltip
        self.promotable = promotable
        self.live = live
        self.name: str = ""  # filled by __set_name__

    def __set_name__(self, owner: type, name: str) -> None:
        self.name = name

    # Values live in NodeInstance.params, not on Node classes; reading the
    # class attribute returns the spec itself (used by spec collection).
    def __get__(self, obj: Any, objtype: type | None = None) -> "ParamSpec":
        return self

    def validate(self, value: Any) -> Any:
        return value

    def parse(self, text: str) -> Any:
        """Parse a CLI string (``--set node.param=value``) into a value."""
        return self.validate(text)

    def to_json(self, value: Any) -> Any:
        return value

    def from_json(self, raw: Any) -> Any:
        return self.validate(raw)


class IntParam(ParamSpec):
    widget_hint = "slider"

    def __init__(
        self,
        label: str,
        *,
        default: int = 0,
        min: int | None = None,
        max: int | None = None,
        step: int = 1,
        odd_only: bool = False,
        **kw: Any,
    ):
        super().__init__(label, default=default, **kw)
        self.min, self.max, self.step, self.odd_only = min, max, step, odd_only

    def validate(self, value: Any) -> int:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ParamError(f"{self.name}: expected int, got {type(value).__name__}")
        v = int(round(value))
        if self.min is not None:
            v = max(v, self.min)
        if self.max is not None:
            v = min(v, self.max)
        if self.odd_only and v % 2 == 0:
            v += 1 if (self.max is None or v + 1 <= self.max) else -1
        return v

    def parse(self, text: str) -> int:
        try:
            return self.validate(int(text))
        except ValueError as e:
            raise ParamError(f"{self.name}: not an integer: {text!r}") from e


class FloatParam(ParamSpec):
    widget_hint = "slider"

    def __init__(
        self,
        label: str,
        *,
        default: float = 0.0,
        min: float | None = None,
        max: float | None = None,
        decimals: int = 3,
        **kw: Any,
    ):
        super().__init__(label, default=default, **kw)
        self.min, self.max, self.decimals = min, max, decimals

    def validate(self, value: Any) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ParamError(f"{self.name}: expected float, got {type(value).__name__}")
        v = float(value)
        if not math.isfinite(v):
            raise ParamError(f"{self.name}: must be finite, got {v}")
        if self.min is not None:
            v = max(v, self.min)
        if self.max is not None:
            v = min(v, self.max)
        return v

    def parse(self, text: str) -> float:
        try:
            return self.validate(float(text))
        except ValueError as e:
            raise ParamError(f"{self.name}: not a number: {text!r}") from e


class BoolParam(ParamSpec):
    widget_hint = "checkbox"

    def __init__(self, label: str, *, default: bool = False, **kw: Any):
        super().__init__(label, default=default, **kw)

    def validate(self, value: Any) -> bool:
        if not isinstance(value, bool):
            raise ParamError(f"{self.name}: expected bool, got {type(value).__name__}")
        return value

    def parse(self, text: str) -> bool:
        lowered = text.strip().lower()
        if lowered in ("1", "true", "yes", "on"):
            return True
        if lowered in ("0", "false", "no", "off"):
            return False
        raise ParamError(f"{self.name}: not a boolean: {text!r}")


class EnumParam(ParamSpec):
    """Dropdown. ``choices`` is a sequence of string values (or an Enum class)."""

    widget_hint = "dropdown"

    def __init__(self, label: str, *, choices: Sequence[str] | type[enum.Enum],
                 default: str | None = None, **kw: Any):
        if isinstance(choices, type) and issubclass(choices, enum.Enum):
            values = [c.value for c in choices]
        else:
            values = list(choices)
        if not values:
            raise ValueError("EnumParam needs at least one choice")
        super().__init__(label, default=default if default is not None else values[0], **kw)
        self.choices = values

    def validate(self, value: Any) -> str:
        if isinstance(value, enum.Enum):
            value = value.value
        if value not in self.choices:
            raise ParamError(
                f"{self.name}: {value!r} not one of {self.choices}"
            )
        return value


class StringParam(ParamSpec):
    widget_hint = "line_edit"

    def __init__(self, label: str, *, default: str = "", **kw: Any):
        super().__init__(label, default=default, **kw)

    def validate(self, value: Any) -> str:
        if not isinstance(value, str):
            raise ParamError(f"{self.name}: expected str, got {type(value).__name__}")
        return value


class PathParam(StringParam):
    """File/dir path stored as a string; resolved against the workflow base
    directory at execution time (docs/06 §1 — workflow-relative assets)."""

    widget_hint = "path_picker"

    def __init__(self, label: str, *, default: str = "", mode: str = "open",
                 filter: str = "", **kw: Any):
        super().__init__(label, default=default, **kw)
        if mode not in ("open", "save", "dir"):
            raise ValueError(f"PathParam mode must be open/save/dir, got {mode!r}")
        self.mode = mode
        self.filter = filter


def _numbers(name: str, value: Any, count: int, integer: bool) -> list:
    """Coerce a sequence to exactly ``count`` numbers, or raise ParamError.

    Shared by the tuple-valued specs below. Tuples and lists are both accepted
    because JSON round-trips tuples into lists — persistence must not change a
    value's identity, or reloading a workflow would re-fingerprint every node.
    """
    if not isinstance(value, (list, tuple)):
        raise ParamError(
            f"{name}: expected a list/tuple of {count} numbers, "
            f"got {type(value).__name__}")
    items = list(value)
    if len(items) != count:
        raise ParamError(f"{name}: expected {count} values, got {len(items)}")
    out = []
    for item in items:
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise ParamError(
                f"{name}: expected numbers, got {type(item).__name__}")
        if not math.isfinite(float(item)):
            raise ParamError(f"{name}: values must be finite, got {item}")
        out.append(int(round(item)) if integer else float(item))
    return out


def _clamp(v, lo, hi):
    if lo is not None:
        v = max(v, lo)
    if hi is not None:
        v = min(v, hi)
    return v


def _split(text: str) -> list[str]:
    return [p for p in text.replace(":", ",").split(",") if p.strip() != ""]


class RangeParam(ParamSpec):
    """A ``(low, high)`` band — contour area limits, intensity windows, HSV
    bands. One spec instead of two loose params, so the two halves cannot drift
    apart or be validated independently."""

    widget_hint = "range"

    def __init__(self, label: str, *, default: Sequence[float] = (0.0, 1.0),
                 min: float | None = None, max: float | None = None,
                 integer: bool = False, decimals: int = 3, **kw: Any):
        self.min, self.max, self.integer, self.decimals = min, max, integer, decimals
        super().__init__(label, default=tuple(default), **kw)

    def validate(self, value: Any) -> tuple:
        lo, hi = _numbers(self.name, value, 2, self.integer)
        lo = _clamp(lo, self.min, self.max)
        hi = _clamp(hi, self.min, self.max)
        # Snap-to-valid, per this module's policy: swap rather than raise, so a
        # slider dragged past its partner keeps both values the user chose.
        if lo > hi:
            lo, hi = hi, lo
        return (lo, hi)

    def parse(self, text: str) -> tuple:
        parts = _split(text)
        if len(parts) != 2:
            raise ParamError(f"{self.name}: expected 'low,high', got {text!r}")
        try:
            return self.validate([float(p) for p in parts])
        except ValueError as e:
            raise ParamError(f"{self.name}: not two numbers: {text!r}") from e

    def to_json(self, value: Any) -> Any:
        return list(value) if value is not None else None

    def from_json(self, raw: Any) -> tuple:
        return self.validate(raw)


class PointParam(ParamSpec):
    """An ``(x, y)`` location in image pixels — seed points, centres, offsets."""

    widget_hint = "point"

    def __init__(self, label: str, *, default: Sequence[float] = (0.0, 0.0),
                 min: float | None = None, max: float | None = None,
                 integer: bool = True, decimals: int = 2, **kw: Any):
        self.min, self.max, self.integer, self.decimals = min, max, integer, decimals
        super().__init__(label, default=tuple(default), **kw)

    def validate(self, value: Any) -> tuple:
        x, y = _numbers(self.name, value, 2, self.integer)
        return (_clamp(x, self.min, self.max), _clamp(y, self.min, self.max))

    def parse(self, text: str) -> tuple:
        parts = _split(text)
        if len(parts) != 2:
            raise ParamError(f"{self.name}: expected 'x,y', got {text!r}")
        try:
            return self.validate([float(p) for p in parts])
        except ValueError as e:
            raise ParamError(f"{self.name}: not two numbers: {text!r}") from e

    def to_json(self, value: Any) -> Any:
        return list(value) if value is not None else None

    def from_json(self, raw: Any) -> tuple:
        return self.validate(raw)


class RectParam(ParamSpec):
    """An ``(x, y, w, h)`` region of interest, in image pixels.

    Intended to be pickable by dragging in the viewer (docs/08 Phase 1); the
    inspector currently edits it numerically.
    """

    widget_hint = "rect"

    def __init__(self, label: str, *, default: Sequence[float] = (0, 0, 0, 0),
                 integer: bool = True, decimals: int = 2, **kw: Any):
        self.integer, self.decimals = integer, decimals
        super().__init__(label, default=tuple(default), **kw)

    def validate(self, value: Any) -> tuple:
        x, y, w, h = _numbers(self.name, value, 4, self.integer)
        # Dragging up-and-left yields a negative extent; normalize instead of
        # rejecting, so the obvious gesture just works.
        if w < 0:
            x, w = x + w, -w
        if h < 0:
            y, h = y + h, -h
        return (x, y, w, h)

    def parse(self, text: str) -> tuple:
        parts = _split(text)
        if len(parts) != 4:
            raise ParamError(f"{self.name}: expected 'x,y,w,h', got {text!r}")
        try:
            return self.validate([float(p) for p in parts])
        except ValueError as e:
            raise ParamError(f"{self.name}: not four numbers: {text!r}") from e

    def to_json(self, value: Any) -> Any:
        return list(value) if value is not None else None

    def from_json(self, raw: Any) -> tuple:
        return self.validate(raw)

    # ---- convenience for nodes -------------------------------------------
    @staticmethod
    def clip_to(value: Sequence[float], width: int, height: int) -> tuple:
        """Clip a rect to an image, returning ``(x, y, w, h)`` with w,h >= 0.

        Nodes should use this rather than trusting the stored rect: the ROI was
        picked against whatever image was displayed then, which may not be the
        one flowing through now.
        """
        x, y, w, h = (int(round(v)) for v in value)
        # Clamp the origin into the image too, so the result is always a rect
        # inside it — a rect fully off-image comes back empty *and* in bounds,
        # which is what a caller checking `w and h` expects.
        x0 = min(max(0, x), width)
        y0 = min(max(0, y), height)
        x1, y1 = min(width, x + w), min(height, y + h)
        return (x0, y0, max(0, x1 - x0), max(0, y1 - y0))


class ColorParam(ParamSpec):
    """A colour in **BGR** order, matching OpenCV — so a node can pass the
    value straight to ``cv2.rectangle``/``putText`` with no conversion. The
    inspector's picker handles the RGB translation for the human."""

    widget_hint = "color"

    def __init__(self, label: str, *, default: Sequence[int] = (0, 255, 0),
                 with_alpha: bool = False, **kw: Any):
        self.with_alpha = with_alpha
        self.channels = 4 if with_alpha else 3
        super().__init__(label, default=tuple(default), **kw)

    def validate(self, value: Any) -> tuple:
        items = _numbers(self.name, value, self.channels, integer=True)
        return tuple(_clamp(v, 0, 255) for v in items)

    def parse(self, text: str) -> tuple:
        parts = _split(text)
        try:
            return self.validate([int(p) for p in parts])
        except ValueError as e:
            raise ParamError(
                f"{self.name}: expected {self.channels} ints 0-255 (B,G,R"
                f"{',A' if self.with_alpha else ''}), got {text!r}") from e

    def to_json(self, value: Any) -> Any:
        return list(value) if value is not None else None

    def from_json(self, raw: Any) -> tuple:
        return self.validate(raw)


class CodeParam(StringParam):
    """Source text edited in a multi-line editor — the custom Script node.

    A node using this is almost certainly **not** pure with respect to its
    params in the usual sense: arbitrary code can read the clock or the
    network. Such a node must set ``cacheable = False`` (docs/04) or the
    fingerprint cache will happily serve a stale result.
    """

    widget_hint = "code"

    def __init__(self, label: str, *, default: str = "",
                 language: str = "python", **kw: Any):
        super().__init__(label, default=default, **kw)
        self.language = language


def default_params(specs: Sequence[ParamSpec]) -> dict[str, Any]:
    return {s.name: s.default for s in specs}


def validate_params(
    specs: Sequence[ParamSpec], values: dict[str, Any]
) -> dict[str, Any]:
    """Validate a full value dict against specs; unknown names raise."""
    by_name: dict[str, ParamSpec] = {s.name: s for s in specs}
    out: dict[str, Any] = default_params(specs)
    for key, value in values.items():
        spec = by_name.get(key)
        if spec is None:
            raise ParamError(f"unknown parameter {key!r} (known: {sorted(by_name)})")
        out[key] = spec.validate(value)
    return out


ParamFactory = Callable[..., ParamSpec]
