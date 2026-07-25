"""Threshold — global, Otsu, and adaptive binarization.

Input is typed Image[GRAY]; a BINARY source satisfies it (subtype), a colour
source is rejected at connect time with the hint to insert "To Gray".
"""

from __future__ import annotations

import cv2

from cvflow.sdk import (
    BoolParam,
    EnumParam,
    ImageIn,
    ImageOut,
    IntParam,
    Issue,
    Node,
    node,
)

_ADAPTIVE = {"adaptive mean": cv2.ADAPTIVE_THRESH_MEAN_C,
             "adaptive gaussian": cv2.ADAPTIVE_THRESH_GAUSSIAN_C}


@node(
    id="cvflow.threshold.threshold",
    version="1.0",
    category="Threshold",
    label="Threshold",
    doc="Binarize a grayscale image (global, Otsu, or adaptive).",
    keywords=("binary", "otsu", "adaptive", "segment", "mask"),
)
class Threshold(Node):
    image = ImageIn("Image", space="GRAY")
    out = ImageOut("Mask", space="BINARY")

    method = EnumParam("Method",
                       choices=("global", "otsu", "adaptive mean", "adaptive gaussian"),
                       default="global")
    thresh = IntParam("Threshold", default=127, min=0, max=255,
                      tooltip="Cut value for the 'global' method")
    invert = BoolParam("Invert", default=False,
                       tooltip="Foreground below the threshold instead of above")
    block_size = IntParam("Block size", default=11, min=3, max=255, step=2, odd_only=True,
                          tooltip="Neighborhood side for adaptive methods (odd)")
    c = IntParam("Adaptive C", default=2, min=-50, max=50,
                 tooltip="Constant subtracted from the local mean (adaptive)")

    def validate(self, params) -> list[Issue]:
        if params["method"].startswith("adaptive") and params["block_size"] < 3:
            return [Issue("adaptive block size must be ≥ 3", level="error")]
        return []

    def process(self, ctx) -> None:
        img = ctx.inputs.image
        style = cv2.THRESH_BINARY_INV if ctx.params.invert else cv2.THRESH_BINARY
        method = ctx.params.method
        if method in _ADAPTIVE:
            out = cv2.adaptiveThreshold(
                img.data, 255, _ADAPTIVE[method], style,
                ctx.params.block_size, ctx.params.c)
        elif method == "otsu":
            _, out = cv2.threshold(img.data, 0, 255, style | cv2.THRESH_OTSU)
        else:
            _, out = cv2.threshold(img.data, ctx.params.thresh, 255, style)
        ctx.outputs.out = img.derive(out, space="BINARY")
