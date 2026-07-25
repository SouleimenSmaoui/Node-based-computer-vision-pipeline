"""Bilateral Filter — edge-preserving smoothing."""

from __future__ import annotations

import cv2

from cvflow.sdk import (
    ColorSpace,
    FloatParam,
    ImageIn,
    ImageOut,
    IntParam,
    Node,
    node,
)


@node(
    id="cvflow.filters.bilateral",
    version="1.0",
    category="Filtering",
    label="Bilateral Filter",
    doc="Smooths only across neighbours that are also similar in intensity, so "
        "noise inside a region disappears while part boundaries stay sharp. "
        "Much slower than a Gaussian — reach for it when a blur must not "
        "soften the edges you are about to measure.",
    keywords=("bilateral", "edge preserving", "denoise", "smooth", "surface"),
)
class Bilateral(Node):
    image = ImageIn("Image")
    out = ImageOut("Image", same_space_as="image")

    diameter = IntParam("Diameter", default=9, min=0, max=51,
                        tooltip="Neighbourhood diameter in pixels. "
                                "0 derives it from Sigma space.")
    sigma_color = FloatParam("Sigma colour", default=75.0, min=1.0, max=300.0,
                             decimals=1,
                             tooltip="How different in intensity a neighbour "
                                     "may be and still be blended in. Larger "
                                     "means more like a plain blur.")
    sigma_space = FloatParam("Sigma space", default=75.0, min=1.0, max=300.0,
                             decimals=1,
                             tooltip="How far away a neighbour may be, in pixels.")

    def process(self, ctx) -> None:
        img = ctx.inputs.image
        ctx.ensure(img.channels in (1, 3),
                   f"bilateral filter needs a 1- or 3-channel image, "
                   f"got {img.channels}")
        result = cv2.bilateralFilter(img.data, ctx.params.diameter,
                                     ctx.params.sigma_color,
                                     ctx.params.sigma_space)
        # Blends neighbours, so a BINARY input is no longer {0, 255}.
        space = ColorSpace.GRAY if img.space is ColorSpace.BINARY else None
        ctx.outputs.out = img.derive(result, space=space)
