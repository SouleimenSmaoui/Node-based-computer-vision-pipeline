"""Median Blur — rank filter; the standard answer to salt-and-pepper noise."""

from __future__ import annotations

import cv2
import numpy as np

from cvflow.sdk import ImageIn, ImageOut, IntParam, Node, node


@node(
    id="cvflow.filters.median_blur",
    version="1.0",
    category="Filtering",
    label="Median Blur",
    doc="Replaces each pixel with the median of its neighbourhood. Unlike a "
        "Gaussian it removes salt-and-pepper noise outright and keeps edges "
        "sharp, at the cost of fine texture and thin lines.",
    keywords=("median", "noise", "salt", "pepper", "denoise", "rank", "speckle"),
)
class MedianBlur(Node):
    image = ImageIn("Image")
    out = ImageOut("Image", same_space_as="image")

    kernel = IntParam("Kernel size", default=5, min=3, max=99, step=2, odd_only=True,
                      tooltip="Neighbourhood side length in pixels; must be odd.")

    def process(self, ctx) -> None:
        img = ctx.inputs.image
        k = ctx.params.kernel
        # OpenCV only supports the fast uint8 path beyond 5; anything else
        # raises deep inside cv2, so say why here instead.
        ctx.ensure(k <= 5 or img.data.dtype == np.uint8,
                   f"median blur needs an 8-bit image for kernel > 5, "
                   f"got {img.data.dtype}")
        # A rank filter only ever outputs values that were already present, so
        # a BINARY mask survives as a valid BINARY mask — no space change here,
        # unlike the averaging filters.
        ctx.outputs.out = img.derive(cv2.medianBlur(img.data, k))
