"""Canny edge detection. Input is typed Image[GRAY], so wiring a BGR image
is rejected at connect time with the hint to insert "To Gray" (docs/03 §6).
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


@node(
    id="cvflow.edges.canny",
    version="1.0",
    category="Edges",
    label="Canny",
    doc="Canny edge detector; outputs a binary edge map.",
    keywords=("edge", "gradient", "hysteresis"),
)
class Canny(Node):
    image = ImageIn("Image", space="GRAY")
    edges = ImageOut("Edges", space="BINARY")

    low = IntParam("Low threshold", default=50, min=0, max=500)
    high = IntParam("High threshold", default=150, min=0, max=500)
    aperture = EnumParam("Aperture", choices=("3", "5", "7"), default="3")
    l2 = BoolParam("L2 gradient", default=False,
                   tooltip="More accurate magnitude, slightly slower")

    def validate(self, params) -> list[Issue]:
        if params["low"] > params["high"]:
            return [Issue("low threshold must be ≤ high threshold", level="error")]
        return []

    def process(self, ctx) -> None:
        img = ctx.inputs.image
        out = cv2.Canny(
            img.data,
            ctx.params.low,
            ctx.params.high,
            apertureSize=int(ctx.params.aperture),
            L2gradient=ctx.params.l2,
        )
        ctx.outputs.edges = img.derive(out, space="BINARY")
