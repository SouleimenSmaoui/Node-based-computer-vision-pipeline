"""Geometry payloads (docs/03 §2). Phase 0 ships ContourSet; the rest of the
catalog (Detections, Keypoints, BBoxes, Tensor) arrives with the nodes that
produce them — see STATUS.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np


@dataclass(frozen=True)
class ContourSet:
    """Exactly what ``cv2.findContours`` yields, in image pixel coordinates."""

    contours: tuple[np.ndarray, ...]
    hierarchy: np.ndarray | None = None
    ref_size: tuple[int, int] | None = None  # (width, height) of source image

    def __post_init__(self) -> None:
        object.__setattr__(self, "contours", tuple(self.contours))
        for c in self.contours:
            c.setflags(write=False)
        if self.hierarchy is not None:
            self.hierarchy.setflags(write=False)

    def __len__(self) -> int:
        return len(self.contours)

    @property
    def nbytes(self) -> int:
        n = sum(int(c.nbytes) for c in self.contours)
        if self.hierarchy is not None:
            n += int(self.hierarchy.nbytes)
        return n

    def areas(self) -> list[float]:
        import cv2

        return [float(cv2.contourArea(c)) for c in self.contours]

    def summary(self) -> str:
        return f"Contours: {len(self.contours)} contour(s)"


def as_contour_tuple(contours: Sequence[np.ndarray]) -> tuple[np.ndarray, ...]:
    return tuple(np.asarray(c) for c in contours)
