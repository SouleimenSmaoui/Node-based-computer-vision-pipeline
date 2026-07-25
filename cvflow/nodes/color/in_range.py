"""In Range — per-channel band threshold into a binary mask."""

from __future__ import annotations

import cv2
import numpy as np

from cvflow.sdk import ImageIn, ImageOut, IntParam, Issue, Node, node

_CHANNELS = ("low1", "high1", "low2", "high2", "low3", "high3")


@node(
    id="cvflow.color.in_range",
    version="1.0",
    category="Color",
    label="In Range",
    doc="Marks pixels whose channels all fall inside [low, high] as 255 and "
        "the rest as 0. The usual way to isolate a colour: convert to HSV "
        "first and band channel 1 (hue) for lighting-robust selection, since "
        "in BGR a change in brightness moves all three channels at once.",
    keywords=("mask", "colour", "color", "threshold", "hsv", "segment", "select"),
)
class InRange(Node):
    image = ImageIn("Image")
    mask = ImageOut("Mask", space="BINARY")

    low1 = IntParam("Ch1 low", default=0, min=0, max=255,
                    tooltip="Hue is 0-179 in OpenCV's HSV, not 0-255.")
    high1 = IntParam("Ch1 high", default=255, min=0, max=255)
    low2 = IntParam("Ch2 low", default=0, min=0, max=255,
                    tooltip="Ignored for single-channel input.")
    high2 = IntParam("Ch2 high", default=255, min=0, max=255)
    low3 = IntParam("Ch3 low", default=0, min=0, max=255,
                    tooltip="Ignored for single-channel input.")
    high3 = IntParam("Ch3 high", default=255, min=0, max=255)

    def validate(self, params) -> list[Issue]:
        issues = []
        for i in (1, 2, 3):
            if params[f"low{i}"] > params[f"high{i}"]:
                issues.append(Issue(f"channel {i}: low must be <= high",
                                    level="error"))
        return issues

    def process(self, ctx) -> None:
        img = ctx.inputs.image
        n = img.channels
        ctx.ensure(n in (1, 3),
                   f"In Range handles 1- or 3-channel images, got {n}")
        p = ctx.params
        lows = [p.low1, p.low2, p.low3][:n]
        highs = [p.high1, p.high2, p.high3][:n]
        mask = cv2.inRange(img.data,
                           np.array(lows, dtype=np.uint8),
                           np.array(highs, dtype=np.uint8))
        # inRange emits exactly {0, 255}, so BINARY is an honest label here.
        ctx.outputs.mask = img.derive(mask, space="BINARY")
