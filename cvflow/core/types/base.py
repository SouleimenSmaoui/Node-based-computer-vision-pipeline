"""Port type system: connection checking and coercions (docs/03 §6).

Strict where lossy, automatic where lossless:
  - BINARY satisfies GRAY consumers (identity subtype),
  - GRAY/BINARY -> BGR/RGB coerces automatically (channel replication, lossless),
  - BGR -> GRAY is rejected with the hint to insert "To Gray" (lossy, parametric).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import numpy as np

from cvflow.core.types.image import ColorSpace, ImageBuffer

# Port kinds. A PortType is (kind, optional image space).
KIND_IMAGE = "image"
KIND_CONTOURS = "contours"
KIND_NUMBER = "number"
KIND_TEXT = "text"
KIND_ANY = "any"


@dataclass(frozen=True)
class PortType:
    kind: str
    space: ColorSpace | None = None  # only meaningful for kind == "image"

    def label(self) -> str:
        if self.kind == KIND_IMAGE:
            return f"Image[{self.space.value}]" if self.space else "Image"
        return self.kind.capitalize()


# ---- connection check results -------------------------------------------


@dataclass(frozen=True)
class Ok:
    pass


@dataclass(frozen=True)
class Coerce:
    """Auto-inserted lossless adapter; ``label`` is shown as a wire badge."""

    fn: Callable[[Any], Any]
    label: str


@dataclass(frozen=True)
class Reject:
    reason: str
    hint: str | None = None


CheckResult = Ok | Coerce | Reject


# ---- coercion functions ---------------------------------------------------


def _single_to_3ch(target: ColorSpace) -> Callable[[ImageBuffer], ImageBuffer]:
    def convert(buf: ImageBuffer) -> ImageBuffer:
        arr = buf.data
        if arr.ndim == 2:
            arr = arr[:, :, None]
        out = np.repeat(arr, 3, axis=2)
        return buf.derive(out, space=target)

    return convert


def _binary_as_gray(buf: ImageBuffer) -> ImageBuffer:
    return buf.derive(buf.data, space=ColorSpace.GRAY)


_SINGLE = (ColorSpace.GRAY, ColorSpace.BINARY)
_TRIPLE_DISPLAY = (ColorSpace.BGR, ColorSpace.RGB)


def check_connection(src: PortType, dst: PortType) -> CheckResult:
    """Decide whether an output of type ``src`` may feed an input of type ``dst``."""
    if src.kind == KIND_ANY or dst.kind == KIND_ANY:
        return Ok()  # utility ports — verified at runtime
    if src.kind != dst.kind:
        return Reject(f"cannot connect {src.label()} to {dst.label()}")
    if src.kind != KIND_IMAGE:
        return Ok()

    s, d = src.space, dst.space
    if s is None or d is None or s == d:
        return Ok()  # unconstrained side — runtime check applies
    if s is ColorSpace.BINARY and d is ColorSpace.GRAY:
        return Coerce(_binary_as_gray, "auto: BINARY→GRAY")
    if s in _SINGLE and d in _TRIPLE_DISPLAY:
        return Coerce(_single_to_3ch(d), f"auto: {s.value}→{d.value} replicate")

    hint = None
    if d is ColorSpace.GRAY:
        hint = 'insert "To Gray"'
    return Reject(f"expects {dst.label()}, got {src.label()}", hint)


def runtime_check(value: Any, dst: PortType) -> str | None:
    """Cheap re-validation at execution time. Returns an error string or None."""
    if dst.kind == KIND_ANY:
        return None
    if dst.kind == KIND_IMAGE:
        if not isinstance(value, ImageBuffer):
            return f"expected Image, got {type(value).__name__}"
        if dst.space is not None and value.space is not dst.space:
            if dst.space is ColorSpace.GRAY and value.space is ColorSpace.BINARY:
                return None
            return f"expected Image[{dst.space.value}], got Image[{value.space.value}]"
        return None
    if dst.kind == KIND_NUMBER and not isinstance(value, (int, float)):
        return f"expected Number, got {type(value).__name__}"
    if dst.kind == KIND_TEXT and not isinstance(value, str):
        return f"expected Text, got {type(value).__name__}"
    return None


# ---- generic value introspection (cache accounting, tooltips) -------------


def nbytes_of(value: Any) -> int:
    if value is None:
        return 0
    nb = getattr(value, "nbytes", None)
    if nb is not None:
        return int(nb)
    if isinstance(value, str):
        return len(value.encode("utf-8", errors="ignore"))
    if isinstance(value, (list, tuple)):
        return sum(nbytes_of(v) for v in value)
    if isinstance(value, dict):
        return sum(nbytes_of(v) for v in value.values())
    return 64  # scalars and small objects: flat estimate


def summary_of(value: Any) -> str:
    if value is None:
        return "None"
    fn = getattr(value, "summary", None)
    if callable(fn):
        return fn()
    text = repr(value)
    return text if len(text) <= 80 else text[:77] + "..."
