"""Sobel — first-derivative gradient, per axis or as a magnitude."""

from __future__ import annotations

import cv2
import numpy as np

from cvflow.sdk import (
    BoolParam,
    EnumParam,
    FloatParam,
    ImageIn,
    ImageOut,
    IntParam,
    Node,
    ValueRange,
    node,
)


@node(
    id="cvflow.edges.sobel",
    version="1.0",
    category="Edges",
    label="Sobel",
    doc="First-derivative gradient. 'x' and 'y' give the signed derivative "
        "along one axis; 'magnitude' gives sqrt(gx^2 + gy^2), which is "
        "orientation-independent. Blur first — derivatives amplify noise.",
    keywords=("sobel", "gradient", "derivative", "edge", "magnitude"),
)
class Sobel(Node):
    image = ImageIn("Image", space="GRAY")
    out = ImageOut("Gradient", space="GRAY")

    direction = EnumParam("Direction", choices=("x", "y", "magnitude"),
                          default="magnitude")
    ksize = IntParam("Kernel size", default=3, min=1, max=7, step=2, odd_only=True,
                     tooltip="Sobel aperture: 1, 3, 5 or 7.")
    scale = FloatParam("Scale", default=1.0, min=0.01, max=100.0, decimals=2,
                       tooltip="Multiplier applied to the derivative.")
    normalize = BoolParam("Normalize to 8-bit", default=True,
                          tooltip="Off keeps the raw float gradient (signed for "
                                  "x/y); viewers auto-normalize it for display.")

    def process(self, ctx) -> None:
        img = ctx.inputs.image
        k, s = ctx.params.ksize, ctx.params.scale
        src = img.data
        direction = ctx.params.direction

        if direction == "x":
            grad = cv2.Sobel(src, cv2.CV_32F, 1, 0, ksize=k, scale=s)
        elif direction == "y":
            grad = cv2.Sobel(src, cv2.CV_32F, 0, 1, ksize=k, scale=s)
        else:
            gx = cv2.Sobel(src, cv2.CV_32F, 1, 0, ksize=k, scale=s)
            gy = cv2.Sobel(src, cv2.CV_32F, 0, 1, ksize=k, scale=s)
            grad = cv2.magnitude(gx, gy)

        if ctx.params.normalize:
            scaled = cv2.normalize(grad, None, 0, 255, cv2.NORM_MINMAX)
            ctx.outputs.out = img.derive(scaled.astype(np.uint8),
                                         space="GRAY", range=ValueRange.U8_FULL)
        else:
            # Signed and unbounded: label it ARBITRARY so the viewer normalizes
            # for display instead of clipping everything below zero to black.
            ctx.outputs.out = img.derive(grad, space="GRAY",
                                         range=ValueRange.ARBITRARY)
