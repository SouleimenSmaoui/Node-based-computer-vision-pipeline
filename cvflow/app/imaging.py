"""ImageBuffer → QImage conversion for the viewers (docs/05 §2.4).

The engine speaks numpy/BGR (docs/03); Qt speaks QImage. This module is the one
place that translation happens. Display normalization is range-aware
(``ValueRange``): unit floats scale by 255, gradient/arbitrary data is min-max
stretched so a Sobel output is actually visible instead of near-black.

Returned QImages own their pixel memory (``.copy()``), so callers need not keep
the source array alive — worth the copy at MVP scale; a zero-copy texture path
is the Phase-2 GL upgrade (docs/05 §2.4).
"""

from __future__ import annotations

import numpy as np
from PySide6 import QtGui

from cvflow.core.types.image import ColorSpace, ImageBuffer, ValueRange

# Display channel isolation options offered by the viewer.
CHANNELS = ("All", "R", "G", "B", "Gray")


def _to_display_uint8(arr: np.ndarray, rng: ValueRange, normalize: str) -> np.ndarray:
    """Return a contiguous uint8 view suitable for a QImage."""
    if arr.dtype == np.uint8 and (normalize == "off" or rng is ValueRange.U8_FULL):
        return np.ascontiguousarray(arr)

    a = arr.astype(np.float32)
    if normalize == "off":
        out = a
    elif rng is ValueRange.UNIT and normalize == "auto":
        out = a * 255.0
    else:  # ARBITRARY, non-uint8, or normalize == "minmax": stretch to full range
        lo, hi = float(np.min(a)), float(np.max(a))
        out = (a - lo) * (255.0 / (hi - lo)) if hi > lo else np.zeros_like(a)
    return np.ascontiguousarray(np.clip(out, 0, 255).astype(np.uint8))


def _as_bgr(buf: ImageBuffer) -> np.ndarray:
    """Collapse any colour space to a 3-channel BGR uint8 for display."""
    import cv2

    space = buf.space
    if space in (ColorSpace.BGR, ColorSpace.RGB):
        return buf.data
    if space is ColorSpace.HSV:
        return cv2.cvtColor(buf.writable_copy(), cv2.COLOR_HSV2BGR)
    if space is ColorSpace.LAB:
        return cv2.cvtColor(buf.writable_copy(), cv2.COLOR_Lab2BGR)
    return buf.data


def to_qimage(buf: ImageBuffer, *, normalize: str = "auto", channel: str = "All") -> QtGui.QImage:
    """Convert an ImageBuffer to an owned QImage.

    ``normalize``: ``auto`` (range-aware), ``off`` (raw uint8), ``minmax``.
    ``channel``: one of :data:`CHANNELS` for isolation.
    """
    space = buf.space

    # Single-channel spaces (and explicit "Gray" isolation) → grayscale.
    if space in (ColorSpace.GRAY, ColorSpace.BINARY) or channel == "Gray":
        if buf.data.ndim == 3:
            import cv2
            mono = cv2.cvtColor(_as_bgr(buf), cv2.COLOR_BGR2GRAY)
        else:
            mono = buf.data
        g = _to_display_uint8(mono, buf.range, normalize)
        h, w = g.shape[:2]
        img = QtGui.QImage(g.data, w, h, g.strides[0], QtGui.QImage.Format.Format_Grayscale8)
        return img.copy()

    if space is ColorSpace.BGRA:
        rgba = _to_display_uint8(buf.data, buf.range, normalize)
        h, w = rgba.shape[:2]
        # BGRA byte order matches Qt's little-endian ARGB32 (B,G,R,A).
        img = QtGui.QImage(rgba.data, w, h, rgba.strides[0], QtGui.QImage.Format.Format_ARGB32)
        return img.copy()

    bgr = _to_display_uint8(_as_bgr(buf), buf.range, normalize)

    if channel in ("R", "G", "B"):
        idx = {"B": 0, "G": 1, "R": 2}[channel]  # array is BGR-ordered
        mono = np.ascontiguousarray(bgr[:, :, idx])
        h, w = mono.shape[:2]
        img = QtGui.QImage(mono.data, w, h, mono.strides[0], QtGui.QImage.Format.Format_Grayscale8)
        return img.copy()

    h, w = bgr.shape[:2]
    fmt = (QtGui.QImage.Format.Format_RGB888 if space is ColorSpace.RGB
           else QtGui.QImage.Format.Format_BGR888)
    img = QtGui.QImage(bgr.data, w, h, bgr.strides[0], fmt)
    return img.copy()


def pixel_readout(buf: ImageBuffer, x: int, y: int) -> str:
    """Human-readable ``x,y → value`` string for the hover probe."""
    if not (0 <= y < buf.height and 0 <= x < buf.width):
        return ""
    px = buf.data[y, x]
    space = buf.space.value
    if buf.data.ndim == 2:
        val = px.item()
        text = f"{val:.4g}" if buf.data.dtype.kind == "f" else str(val)
        return f"({x},{y})  {space}({text})"
    vals = ", ".join(f"{v:.4g}" if buf.data.dtype.kind == "f" else str(int(v)) for v in px)
    return f"({x},{y})  {space}({vals})"
