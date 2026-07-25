"""ImageBuffer: a numpy array with semantics (docs/03 §3).

Canonical channel order is BGR (OpenCV-native) so the common path is copy-free.
Outputs are frozen (read-only numpy arrays) to enforce the engine's
immutability contract mechanically (docs/01 §6.1).
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field, replace
from types import MappingProxyType
from typing import Any, Mapping

import numpy as np


class ColorSpace(enum.Enum):
    BGR = "BGR"
    RGB = "RGB"
    GRAY = "GRAY"
    BINARY = "BINARY"  # single channel, uint8, values {0, 255} by convention
    HSV = "HSV"
    LAB = "LAB"
    BGRA = "BGRA"

    @property
    def channels(self) -> int:
        return _CHANNELS[self]


_CHANNELS = {
    ColorSpace.BGR: 3,
    ColorSpace.RGB: 3,
    ColorSpace.GRAY: 1,
    ColorSpace.BINARY: 1,
    ColorSpace.HSV: 3,
    ColorSpace.LAB: 3,
    ColorSpace.BGRA: 4,
}


class ValueRange(enum.Enum):
    """Semantic value range — viewers use it for display normalization."""

    U8_FULL = "u8"      # 0..255
    UNIT = "unit"       # 0.0..1.0
    ARBITRARY = "arb"   # e.g. gradients; display must auto-normalize


_EMPTY: Mapping[str, Any] = MappingProxyType({})


@dataclass(frozen=True)
class FrameInfo:
    index: int
    timestamp: float | None = None
    source_id: str | None = None


@dataclass(frozen=True)
class ImageBuffer:
    data: np.ndarray
    space: ColorSpace  # the string form ("GRAY", "BGR", ...) is accepted too
    range: ValueRange = ValueRange.U8_FULL
    frame: FrameInfo | None = None
    meta: Mapping[str, Any] = field(default=_EMPTY)

    def __post_init__(self) -> None:
        if isinstance(self.space, str):
            object.__setattr__(self, "space", ColorSpace(self.space))
        arr = self.data
        if not isinstance(arr, np.ndarray):
            raise TypeError(f"ImageBuffer.data must be ndarray, got {type(arr).__name__}")
        ch = arr.shape[2] if arr.ndim == 3 else 1
        if arr.ndim not in (2, 3) or ch != self.space.channels:
            raise ValueError(
                f"{self.space.value} expects {self.space.channels} channel(s); "
                f"got array with shape {arr.shape}"
            )
        if self.space is ColorSpace.BINARY and arr.dtype != np.uint8:
            raise ValueError(f"BINARY images must be uint8, got {arr.dtype}")
        # Freeze: violations of the no-mutation contract become immediate errors.
        arr.setflags(write=False)

    # ---- derivation ----------------------------------------------------
    def derive(
        self,
        new_data: np.ndarray,
        *,
        space: ColorSpace | str | None = None,
        range: ValueRange | None = None,
    ) -> "ImageBuffer":
        """Blessed way to produce an output: inherits metadata, freezes data."""
        if isinstance(space, str):
            space = ColorSpace(space)
        return replace(
            self,
            data=new_data,
            space=space if space is not None else self.space,
            range=range if range is not None else self.range,
        )

    def writable_copy(self) -> np.ndarray:
        out = self.data.copy()
        out.setflags(write=True)
        return out

    def bgr_canvas(self) -> np.ndarray:
        """A writable 3-channel BGR array to draw on.

        Annotation nodes all need the same thing: colour strokes need three
        channels, drawing mutates, and outputs are frozen — so this always
        returns a copy, never a view. Single-channel input is promoted rather
        than refused, so a mask or an edge map can be annotated directly.
        """
        import cv2

        if self.space in (ColorSpace.GRAY, ColorSpace.BINARY):
            return cv2.cvtColor(self.data, cv2.COLOR_GRAY2BGR)
        if self.space is ColorSpace.BGR:
            return self.writable_copy()
        # HSV/LAB/RGB/BGRA all have a COLOR_<space>2BGR conversion.
        return cv2.cvtColor(self.data, getattr(cv2, f"COLOR_{self.space.value}2BGR"))

    # ---- introspection -------------------------------------------------
    @property
    def nbytes(self) -> int:
        return int(self.data.nbytes)

    @property
    def height(self) -> int:
        return int(self.data.shape[0])

    @property
    def width(self) -> int:
        return int(self.data.shape[1])

    @property
    def channels(self) -> int:
        return self.data.shape[2] if self.data.ndim == 3 else 1

    def summary(self) -> str:
        mb = self.nbytes / 1e6
        frame = f", frame {self.frame.index}" if self.frame else ""
        return (
            f"{self.space.value} {self.data.dtype} {self.width}×{self.height}"
            f", {mb:.1f} MB{frame}"
        )
