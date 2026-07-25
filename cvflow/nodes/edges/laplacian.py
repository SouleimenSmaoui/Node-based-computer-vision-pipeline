"""Laplacian — second-derivative operator; isotropic edge response."""

from __future__ import annotations

import cv2
import numpy as np

from cvflow.sdk import (
    BoolParam,
    FloatParam,
    ImageIn,
    ImageOut,
    IntParam,
    Node,
    ValueRange,
    node,
)


@node(
    id="cvflow.edges.laplacian",
    version="1.0",
    category="Edges",
    label="Laplacian",
    doc="Sum of second derivatives — responds to intensity ridges and changes "
        "sign across an edge, with no preferred orientation. Noticeably more "
        "noise-sensitive than Sobel, so blur first; the zero crossings, not "
        "the peaks, mark the edges.",
    keywords=("laplacian", "second derivative", "edge", "zero crossing", "log"),
)
class Laplacian(Node):
    image = ImageIn("Image", space="GRAY")
    out = ImageOut("Response", space="GRAY")

    ksize = IntParam("Kernel size", default=3, min=1, max=31, step=2, odd_only=True,
                     tooltip="Aperture size; 1 uses the compact 3x3 kernel.")
    scale = FloatParam("Scale", default=1.0, min=0.01, max=100.0, decimals=2,
                       tooltip="Multiplier applied to the response.")
    normalize = BoolParam("Normalize to 8-bit", default=True,
                          tooltip="Off keeps the signed float response; viewers "
                                  "auto-normalize it for display.")

    def process(self, ctx) -> None:
        img = ctx.inputs.image
        response = cv2.Laplacian(img.data, cv2.CV_32F,
                                 ksize=ctx.params.ksize, scale=ctx.params.scale)
        if ctx.params.normalize:
            scaled = cv2.normalize(response, None, 0, 255, cv2.NORM_MINMAX)
            ctx.outputs.out = img.derive(scaled.astype(np.uint8),
                                         space="GRAY", range=ValueRange.U8_FULL)
        else:
            # The sign is the informative part here (it flips across an edge),
            # so never clip it away by pretending this is an 8-bit image.
            ctx.outputs.out = img.derive(response, space="GRAY",
                                         range=ValueRange.ARBITRARY)
