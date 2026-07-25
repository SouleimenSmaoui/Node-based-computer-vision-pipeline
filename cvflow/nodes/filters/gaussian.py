"""Gaussian Blur — the reference example from docs/04 §1, kept in sync with it."""

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
    id="cvflow.filters.gaussian_blur",
    version="1.0",
    category="Filtering",
    label="Gaussian Blur",
    doc="Smooths an image with a Gaussian kernel.",
    keywords=("smooth", "denoise", "lowpass"),
)
class GaussianBlur(Node):
    image = ImageIn("Image")
    out = ImageOut("Image", same_space_as="image")

    kernel = IntParam("Kernel size", default=5, min=1, max=99, step=2, odd_only=True,
                      tooltip="Aperture side length; must be odd")
    sigma = FloatParam("Sigma", default=0.0, min=0.0, max=50.0, decimals=2,
                       tooltip="0 = derived from kernel size")

    def process(self, ctx) -> None:
        img = ctx.inputs.image
        k = ctx.params.kernel
        blurred = cv2.GaussianBlur(img.data, (k, k), ctx.params.sigma)
        # Blending neighbours puts values between 0 and 255, so a BINARY input
        # is no longer a valid mask. Emit GRAY instead of mislabelling it —
        # same rule as Resize (CODE_REVIEW §2.8, nodes/README.md).
        space = ColorSpace.GRAY if img.space is ColorSpace.BINARY else None
        ctx.outputs.out = img.derive(blurred, space=space)
